#!/usr/bin/env python3
"""
Daily match day orchestrator.

Usage:
  python daily_runner.py                       # run today's matches
  python daily_runner.py --date 2026-06-13     # run specific date
  python daily_runner.py --distribute-only     # post threads from today's summary
"""
import argparse
import json
import os
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import teams

RUNS_DIR = Path("runs")
GROUP_LETTERS = set("ABCDEFGHIJKL")
KNOCKOUT_GROUPS = {"R32", "R16", "QF", "SF", "FINAL", "3RD"}

try:
    from distribute import post_twitter_thread
except ImportError:
    post_twitter_thread = None  # type: ignore[assignment]

try:
    from update_result import update_result as update_result_fn
except ImportError:
    update_result_fn = None  # type: ignore[assignment]


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("'", "").replace(".", "")


def get_today_matches(date_str: str, schedule_path: Path = Path("schedule.json")) -> list:
    schedule = json.loads(schedule_path.read_text())
    return [m for m in schedule if m["date"] == date_str]


def detect_stage(matches: list) -> str:
    if any(m["group"] in KNOCKOUT_GROUPS for m in matches):
        return "knockout"
    return "group"


def run_match(match_string: str, persona: str | None = None,
              match_date: str | None = None, force: bool = False) -> tuple:
    """Run a single match without tweeting. Returns (success, run_file, thread_file)."""
    home, away = [t.strip() for t in match_string.split(" vs ")]
    slug = f"{slugify(home)}-{slugify(away)}"
    match_date = match_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_file = str(RUNS_DIR / match_date / f"wc_{slug}.json")
    thread_file = str(RUNS_DIR / match_date / f"wc_{slug}_thread.json")
    cmd = [sys.executable, "run_matchday.py", match_string, "--no-tweet", "--date", match_date]
    if force:
        cmd.append("--force")
    if persona:
        cmd += ["--persona", persona]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0, run_file, thread_file


def write_daily_summary(date_str: str, stage: str, results: list) -> Path:
    RUNS_DIR.mkdir(exist_ok=True)
    date_dir = RUNS_DIR / date_str
    date_dir.mkdir(exist_ok=True)
    summary = {"date": date_str, "stage": stage, "matches": results}
    path = date_dir / "daily_summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


def _write_github_output(key: str, value: str) -> None:
    if github_output := os.getenv("GITHUB_OUTPUT"):
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")


# ESPN's keyless public scoreboard feed — the same JSON that powers their score
# widgets. A final score is structured data, so we read it deterministically here
# instead of web-searching and asking an LLM to guess it from snippets.
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


def _espn_events(date_compact: str) -> list:
    """Fetch the raw ESPN scoreboard events for a YYYYMMDD date. Network boundary
    (mocked in tests). Raises on HTTP/transport errors so the caller can degrade."""
    resp = requests.get(ESPN_SCOREBOARD_URL, params={"dates": date_compact}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("events", [])


def _match_key(name: str) -> set:
    """Identity token-set for a team name, tolerant of media spelling variants.
    Routes through teams.canonical (alias map) then strips accents/punctuation and
    connector words so 'Bosnia-Herzegovina' == 'Bosnia and Herzegovina'."""
    canon = teams.canonical(name)
    ascii_name = unicodedata.normalize("NFKD", canon).encode("ascii", "ignore").decode("ascii")
    for ch in "-.'&/":
        ascii_name = ascii_name.replace(ch, " ")
    return {t for t in ascii_name.lower().split() if t not in ("and", "the")}


def _teams_match(name_a: str, name_b: str) -> bool:
    """True if two team names refer to the same side. Exact token-set match, or one
    being a subset of the other (handles 'Iran' vs FIFA 'IR Iran')."""
    a, b = _match_key(name_a), _match_key(name_b)
    if not a or not b:
        return False
    return a == b or a <= b or b <= a


def fetch_match_result(match_string: str, date_compact: str) -> tuple | None:
    """
    Look up the final score for a played match from ESPN's keyless scoreboard feed.
    `date_compact` is YYYYMMDD (the fixture's match day). Returns
    (home_goals, away_goals) oriented to `match_string`'s home/away by team identity,
    or None if the match isn't found or hasn't reached full time. Never raises.
    """
    home, away = [t.strip() for t in match_string.split(" vs ")]

    # Try the match day plus ±1 to absorb UTC-vs-local date skew on late kickoffs.
    try:
        base = datetime.strptime(date_compact, "%Y%m%d")
        candidate_dates = [date_compact,
                           (base - timedelta(days=1)).strftime("%Y%m%d"),
                           (base + timedelta(days=1)).strftime("%Y%m%d")]
    except ValueError:
        candidate_dates = [date_compact]

    for d in candidate_dates:
        try:
            events = _espn_events(d)
        except Exception as e:
            print(f"  [result] ESPN scoreboard fetch failed for {d}: {type(e).__name__}: {e}")
            continue

        for ev in events:
            comp = (ev.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue

            our_home_goals = our_away_goals = None
            for c in competitors:
                espn_name = c.get("team", {}).get("displayName", "")
                if _teams_match(espn_name, home):
                    our_home_goals = c.get("score")
                elif _teams_match(espn_name, away):
                    our_away_goals = c.get("score")

            if our_home_goals is None or our_away_goals is None:
                continue  # not our fixture

            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status != "STATUS_FULL_TIME":
                print(f"  [result] {match_string} found but not final (status={status})")
                return None
            try:
                return int(our_home_goals), int(our_away_goals)
            except (TypeError, ValueError):
                print(f"  [result] {match_string} final but score unparseable "
                      f"({our_home_goals!r}-{our_away_goals!r})")
                return None

    print(f"  [result] No final result for {match_string} around {date_compact}")
    return None


def distribute_today(date_str: str) -> int:
    """Post Twitter threads from today's daily summary. Returns count posted."""
    if post_twitter_thread is None:
        print("distribute module not available")
        return 0

    summary_path = RUNS_DIR / date_str / "daily_summary.json"
    if not summary_path.exists():
        print(f"No summary found for {date_str}: {summary_path}")
        return 0

    summary = json.loads(summary_path.read_text())
    posted = 0
    for match in summary["matches"]:
        if not match.get("success"):
            print(f"Skipping failed match: {match['match_string']}")
            continue
        thread_path = Path(match["thread_file"])
        if not thread_path.exists():
            print(f"Thread file not found: {thread_path}")
            continue
        threads = json.loads(thread_path.read_text())
        print(f"Posting thread: {match['match_string']}...")
        try:
            post_twitter_thread(threads)
            posted += 1
        except Exception as e:
            print(f"  Failed to post thread for {match['match_string']}: {e}")
    return posted


def update_yesterday_results(date_str: str) -> int:
    """
    Backfill the actual score for EVERY past match still missing an 'actual' field,
    not just the most recent match day. A score the feed missed on an earlier day
    self-heals on a later run instead of needing a manual patch. Already-recorded
    matches are skipped, so the daily cost is one free ESPN lookup per open result.
    Returns count of results recorded this run.
    """
    # Find all dated run files (????-??-??/wc_*.json, not context/thread/summary/base)
    all_run_files = [
        f for f in RUNS_DIR.glob("????-??-??/wc_*.json")
        if not any(f.name.endswith(s) for s in ("_context.json", "_thread.json", "_reasoning.json"))
        and not f.name.endswith("_base.json")
    ]

    today_compact = date_str.replace("-", "")
    # Every past run file, paired with its own match day (YYYYMMDD), oldest first.
    pending = sorted(
        (f.parent.name.replace("-", ""), f)
        for f in all_run_files
        if f.parent.name.replace("-", "") < today_compact
    )

    if not pending:
        print(f"No previous match days found before {date_str}")
        return 0

    if update_result_fn is None:
        print("  update_result not available — skipping result update")
        return 0

    print(f"Checking {len(pending)} past match(es) for results")
    updated = 0
    for file_date, run_file in pending:
        try:
            run = json.loads(run_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠️  Skipping unreadable run file {run_file.name}: {e}")
            continue
        if "actual" in run:
            continue  # already recorded — skip quietly to keep the log readable
        match_string = run.get("match_string", "")
        if not match_string:
            continue
        print(f"  Fetching result: {match_string} ({file_date})...")
        result = fetch_match_result(match_string, file_date)
        if result is None:
            print(f"  Could not determine result for {match_string}")
            continue
        home_goals, away_goals = result
        update_result_fn(run_file, home_goals, away_goals)
        updated += 1
        print(f"  Recorded: {match_string} {home_goals}-{away_goals}")

    return updated


def main():
    parser = argparse.ArgumentParser(description="Daily World Cup match runner")
    parser.add_argument("--date", help="Date to run (YYYY-MM-DD, default: today UTC)")
    parser.add_argument("--distribute-only", action="store_true",
                        help="Post threads from today's summary without re-running matches")
    parser.add_argument("--persona", default=None,
                        help="Persona set from personas.json (e.g. ollama_test; default: world_cup)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run matches even if already completed")
    args = parser.parse_args()

    date_str = args.date or os.getenv("MATCH_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if args.distribute_only:
        n = distribute_today(date_str)
        print(f"Posted {n} thread(s)")
        return

    # Step 1: Record results from previous match day
    print(f"=== Checking previous results ===")
    n_updated = update_yesterday_results(date_str)
    print(f"Updated {n_updated} previous result(s)")

    # Step 2: Find today's matches
    matches = get_today_matches(date_str)
    if not matches:
        print(f"No matches scheduled for {date_str}")
        _write_github_output("stage", "none")
        sys.exit(0)

    stage = detect_stage(matches)
    print(f"\n=== Date: {date_str} | Stage: {stage} | Matches: {len(matches)} ===")
    _write_github_output("stage", stage)

    results = []
    failed = []
    for match in matches:
        match_string = match["match_string"]
        print(f"\nRunning: {match_string}")
        success, run_file, thread_file = run_match(
            match_string, persona=args.persona, match_date=date_str, force=args.force)
        results.append({
            "match_string": match_string,
            "run_file": run_file,
            "thread_file": thread_file,
            "success": success,
        })
        if not success:
            failed.append(match_string)
            print(f"  FAILED: {match_string}")
        else:
            print(f"  OK: {run_file}")
            # Patch context file with group/date from schedule (research.py doesn't have this)
            ctx_file = Path(run_file.replace(".json", "_context.json"))
            if ctx_file.exists():
                ctx = json.loads(ctx_file.read_text())
                ctx["group"] = match.get("group")
                ctx["match_date"] = match.get("date")
                ctx["venue"] = match.get("venue")
                ctx_file.write_text(json.dumps(ctx, indent=2), encoding="utf-8")

    summary_path = write_daily_summary(date_str, stage, results)
    print(f"\nSummary: {summary_path}")

    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
