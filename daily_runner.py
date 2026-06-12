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
from datetime import datetime, timezone
from pathlib import Path

RUNS_DIR = Path("runs")
GROUP_LETTERS = set("ABCDEFGHIJKL")
KNOCKOUT_GROUPS = {"R32", "R16", "QF", "SF", "FINAL", "3RD"}

try:
    from openai import OpenAI
    from dotenv import load_dotenv
    from tavily import TavilyClient
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]
    load_dotenv = None  # type: ignore[assignment]
    TavilyClient = None  # type: ignore[assignment,misc]

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


# FIFA official names that sports media writes differently
_SEARCH_NAME = {
    "Korea Republic": "South Korea",
    "Türkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Czechia": "Czech Republic",
}


def _search_team(name: str) -> str:
    return _SEARCH_NAME.get(name, name)


def fetch_match_result(match_string: str) -> tuple | None:
    """
    Search for the actual result of a played match using Tavily + LLM parsing.
    Returns (home_goals, away_goals) as ints, or None if result not found/confident.
    """
    if load_dotenv is not None:
        load_dotenv()

    if TavilyClient is None or OpenAI is None:
        print(f"  [result] tavily/openai not installed — skipping result fetch for {match_string}")
        return None

    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        print(f"  [result] No TAVILY_API_KEY — skipping result fetch for {match_string}")
        return None

    home, away = [t.strip() for t in match_string.split(" vs ")]
    query = f"{_search_team(home)} vs {_search_team(away)} World Cup 2026 final score result"

    try:
        tavily = TavilyClient(api_key=tavily_key)
        search = tavily.search(query, max_results=5, search_depth="basic")
        snippets = "\n".join(
            f"- {r['title']}: {r['content'][:300]}"
            for r in search.get("results", [])
        )
    except Exception as e:
        print(f"  [result] Tavily search failed for {match_string}: {e}")
        return None

    if not snippets:
        return None

    prompt = f"""Extract the final score from these search results for the World Cup 2026 match: {home} vs {away}

Search results:
{snippets}

If the match has been played and you can determine the score with high confidence, respond ONLY with JSON like:
{{"home_goals": 2, "away_goals": 1, "confidence": "high"}}

If the match has NOT been played yet, or you cannot determine the score confidently, respond ONLY with:
{{"home_goals": null, "away_goals": null, "confidence": "low"}}

Return ONLY the JSON, no other text."""

    try:
        client = OpenAI(
            base_url=os.getenv("COUNCIL_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("COUNCIL_API_KEY", "ollama"),
        )
        response = client.chat.completions.create(
            model=os.getenv("RESEARCH_MODEL", "mistral:7b"),
            max_tokens=64,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        if parsed.get("confidence") == "high" and parsed.get("home_goals") is not None:
            return int(parsed["home_goals"]), int(parsed["away_goals"])
    except Exception as e:
        print(f"  [result] LLM parse failed for {match_string}: {e}")

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
    For each run file from the most recent previous match day that lacks an 'actual'
    field, fetch the result via Tavily+LLM and record it.
    Returns count of results successfully recorded.
    """
    # Find all dated run files (????-??-??/wc_*.json, not context/thread/summary/base)
    all_run_files = [
        f for f in RUNS_DIR.glob("????-??-??/wc_*.json")
        if not any(f.name.endswith(s) for s in ("_context.json", "_thread.json"))
        and not f.name.endswith("_base.json")
    ]

    # Group by date (folder name YYYY-MM-DD), find most recent date before today
    today_compact = date_str.replace("-", "")
    dates_before_today = set()
    for f in all_run_files:
        file_date = f.parent.name.replace("-", "")  # YYYY-MM-DD folder → YYYYMMDD
        if file_date < today_compact:
            dates_before_today.add(file_date)

    if not dates_before_today:
        print(f"No previous match days found before {date_str}")
        return 0

    prev_date_compact = max(dates_before_today)
    prev_files = [f for f in all_run_files if f.parent.name.replace("-", "") == prev_date_compact]

    if update_result_fn is None:
        print("  update_result not available — skipping result update")
        return 0

    print(f"Checking results for {prev_date_compact}: {len(prev_files)} match(es)")
    updated = 0
    for run_file in prev_files:
        try:
            run = json.loads(run_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠️  Skipping unreadable run file {run_file.name}: {e}")
            continue
        if "actual" in run:
            print(f"  Already recorded: {run_file.name}")
            continue
        match_string = run.get("match_string", "")
        if not match_string:
            continue
        print(f"  Fetching result: {match_string}...")
        result = fetch_match_result(match_string)
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
