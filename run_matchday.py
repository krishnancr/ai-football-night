#!/usr/bin/env python3
"""
World Cup match day orchestrator.
Runs all stages: research → debate → format → distribute.

Usage:
  python run_matchday.py "Brazil vs Croatia"
  python run_matchday.py 2026-06-11              # run all matches that day
  python run_matchday.py "Brazil vs Croatia" --dry-run
  python run_matchday.py "Brazil vs Croatia" --research-only
  python run_matchday.py "Brazil vs Croatia" --no-tweet
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

from dotenv import load_dotenv

load_dotenv()


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("'", "").replace(".", "")


def should_skip_run(run_path: Path, force: bool = False) -> bool:
    """True if this match already has a complete run (valid decision, no parse error).
    Skipping a complete run costs nothing; --force regenerates after prompt changes."""
    if force or not Path(run_path).exists():
        return False
    try:
        run = json.loads(Path(run_path).read_text())
    except Exception:
        return False
    decision = run.get("decision") or {}
    return bool(decision) and not decision.get("parse_error")


def main():
    parser = argparse.ArgumentParser(description="Run a World Cup match day prediction")
    parser.add_argument("match", help='Match string e.g. "Brazil vs Croatia", or date YYYY-MM-DD to run all matches that day')
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip all distribution — print output paths only")
    parser.add_argument("--research-only", action="store_true",
                        help="Run only the research step and stop")
    parser.add_argument("--no-tweet", action="store_true",
                        help="Skip Twitter posting (Substack draft still generated)")
    parser.add_argument("--skip-research", action="store_true",
                        help="Skip research (use existing context file if present)")
    parser.add_argument("--persona", default="world_cup",
                        help="Persona set from personas.json (default: world_cup, use smoke_test for local Ollama)")
    parser.add_argument("--date", dest="match_date",
                        help="Match date YYYY-MM-DD — stamps run files (default: today UTC)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if this match's run is already complete")
    args = parser.parse_args()

    # ── Date mode: run all matches for a given date ──────────────────
    if _DATE_RE.match(args.match):
        schedule_path = Path("schedule.json")
        if not schedule_path.exists():
            print(f"Error: schedule.json not found in {Path.cwd()}")
            sys.exit(1)
        schedule = json.loads(schedule_path.read_text())
        day_matches = [m for m in schedule if m["date"] == args.match]
        if not day_matches:
            print(f"No matches scheduled for {args.match}")
            sys.exit(0)
        print(f"\nDate mode: {len(day_matches)} match(es) on {args.match}")
        extra = []
        if args.dry_run:
            extra.append("--dry-run")
        if args.research_only:
            extra.append("--research-only")
        if args.skip_research:
            extra.append("--skip-research")
        if args.no_tweet:
            extra.append("--no-tweet")
        if args.persona != "world_cup":
            extra += ["--persona", args.persona]
        if args.force:
            extra.append("--force")
        extra += ["--date", args.match]
        failed = []
        for m in day_matches:
            cmd = [sys.executable, __file__, m["match_string"]] + extra
            ret = subprocess.run(cmd).returncode
            if ret != 0:
                failed.append(m["match_string"])
        if failed:
            print(f"\nFailed: {len(failed)}/{len(day_matches)}: {', '.join(failed)}")
            sys.exit(1)
        return

    if " vs " not in args.match:
        print('Error: match must be "Team A vs Team B" or a date YYYY-MM-DD')
        sys.exit(1)

    home, away = [t.strip() for t in args.match.split(" vs ")]
    slug = f"{slugify(home)}-{slugify(away)}"
    match_date_dashed = args.match_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_str = match_date_dashed.replace("-", "")

    runs_dir = Path("runs")
    runs_dir.mkdir(exist_ok=True)
    date_dir = runs_dir / match_date_dashed
    date_dir.mkdir(exist_ok=True)

    # The run JSON is the one debuggable artifact kept top-level (site, cards, and
    # result self-heal all read it). Everything else is a sidecar demoted into
    # _debug/ so the daily folder surfaces only what gets posted: the run JSON,
    # the picks cards, sack_race.png, and THREAD.md.
    debug_dir = date_dir / "_debug"
    debug_dir.mkdir(exist_ok=True)

    run_path = date_dir / f"wc_{slug}.json"
    context_path = debug_dir / f"wc_{slug}_context.json"
    thread_path = debug_dir / f"wc_{slug}_thread.json"

    if should_skip_run(run_path, args.force):
        print(f"\n✓ Already complete: {run_path}")
        print("  Skipping — no API spend. Use --force to regenerate after prompt changes.")
        return

    print(f"\n{'='*60}")
    print(f"AI FOOTBALL NIGHT — {args.match}")
    print(f"{'='*60}")

    # ── Stage 1: Research ───────────────────────────────────────────
    print(f"\n[1/4] Research...")
    if args.skip_research and context_path.exists():
        print(f"  Skipping — using existing {context_path}")
        context = json.loads(context_path.read_text())
    else:
        from research import research_match
        context = research_match(args.match)
        context_path.write_text(json.dumps(context, indent=2))
        print(f"  Saved: {context_path}")

    if args.research_only:
        print(f"\nResearch complete. Review {context_path} before continuing.")
        print("Re-run without --research-only to continue to debate.")
        return

    # ── Stage 2: Debate ─────────────────────────────────────────────
    print(f"\n[2/4] Debate council...")
    import council_cli
    from council_cli import load_personas, run_council
    from track_record import build_track_records, extract_pundit_predictions, extract_pre_debate_predictions, inject_track_records
    personas = load_personas()

    if args.persona not in personas:
        print(f"Error: '{args.persona}' persona set not found in personas.json")
        sys.exit(1)

    records = build_track_records(runs_dir)
    if records:
        print(f"  Injecting track records for: {', '.join(records)}")
    persona_set = inject_track_records(personas[args.persona], records)

    constraints = json.dumps(context, indent=2)
    idea = f"Predict the scoreline for: {args.match}"
    result = run_council(idea, constraints, persona_set)
    result["match_slug"] = slug
    result["match_string"] = args.match
    result["pundit_predictions"] = extract_pundit_predictions(result.get("full_debate", {}))
    # Pre-debate (proposal-round) calls, kept separate as the control for measuring debate lift.
    result["pre_debate_predictions"] = extract_pre_debate_predictions(result.get("full_debate", {}))
    result["cost"] = {
        "prompt_tokens": council_cli.LAST_USAGE.get("prompt_tokens", 0),
        "completion_tokens": council_cli.LAST_USAGE.get("completion_tokens", 0),
        "calls": council_cli.LAST_USAGE.get("calls", 0),
    }
    print(f"  💸 tokens in={result['cost']['prompt_tokens']} out={result['cost']['completion_tokens']} calls={result['cost']['calls']}")

    run_path.write_text(json.dumps(result, indent=2))
    print(f"  Saved: {run_path}")

    reasoning_entries = [
        {k: e.get(k) for k in ("round", "role", "model", "reasoning")}
        for e in result.get("debate_transcript", [])
        if e.get("reasoning")
    ]
    if reasoning_entries:
        reasoning_path = debug_dir / f"wc_{slug}_reasoning.json"
        reasoning_path.write_text(json.dumps(reasoning_entries, indent=2, ensure_ascii=False))
        print(f"  🧠 saved {len(reasoning_entries)} reasoning traces → {reasoning_path.name}")

    if result["pundit_predictions"]:
        preds = ", ".join(f"{r} {p['home_goals']}-{p['away_goals']}" for r, p in result["pundit_predictions"].items())
        print(f"  Pundit calls: {preds}")
    else:
        print("  ⚠️  No PREDICTION lines parsed from any pundit")

    decision = result.get("decision", {})
    home_g = decision.get("home_goals", "?")
    away_g = decision.get("away_goals", "?")
    confidence = int(decision.get("confidence", 0) * 100)
    print(f"\n  Prediction: {home} {home_g}–{away_g} {away} ({confidence}% confidence)")

    if decision.get("parse_error"):
        print(f"\n  ⚠️  Judge output could not be parsed as JSON.")
        print(f"  Raw output saved in: {run_path}")
        print(f"  Check the 'decision.raw' field for the Judge's actual response.")
        print(f"  Re-run with --skip-research and fix the Judge prompt, or try again.")
        sys.exit(1)

    # ── Stage 2.5: Group-chat highlight reel ────────────────────────
    print(f"\n[2.5/4] Group chat highlights...")
    from group_chat import generate_group_chat
    chat = generate_group_chat(result)
    if chat:
        result["group_chat"] = chat
        run_path.write_text(json.dumps(result, indent=2))
        print(f"  {len(chat)} messages")
    else:
        print("  Skipped (generation failed) — site falls back to full-debate layout")

    # ── Stage 3: Format ─────────────────────────────────────────────
    # Substack is retired — the project posts to X only. The per-match thread.json
    # and postpack are kept for debugging but demoted to _debug/; the postable
    # artifact is the day-level THREAD.md, built by daily_runner after the slate.
    print(f"\n[3/4] Formatting content...")
    from format_content import format_twitter_thread
    thread = format_twitter_thread(result, context)

    thread_path.write_text(json.dumps(thread, indent=2))
    print(f"  Twitter thread: {thread_path} ({len(thread)} tweets)")

    # Artifacts never block the run — post pack failure is a warning, not an exit.
    try:
        from post_pack import format_post_pack
        result["date_compact"] = date_str
        pack_path = debug_dir / f"wc_{slug}_postpack.md"
        pack_path.write_text(format_post_pack(result, context, thread), encoding="utf-8")
        print(f"  Post pack: {pack_path}")
    except Exception as e:
        print(f"  ⚠️  Post pack generation failed (run continues): {type(e).__name__}: {e}")

    # ── Stage 4: Distribute ─────────────────────────────────────────
    print(f"\n[4/4] Distribution...")
    if args.dry_run:
        print("  Skipped (--dry-run)")
    elif args.no_tweet:
        print("  Twitter skipped (--no-tweet)")
    else:
        from distribute import post_twitter_thread
        tweet_ids = post_twitter_thread(thread)
        print(f"  Thread posted: {len(tweet_ids)} tweets")

    print(f"\n{'='*60}")
    print(f"DONE")
    if not args.dry_run and not args.no_tweet:
        print(f"  Twitter thread live")
    print(f"  After the match: python update_result.py {run_path} <home_goals> <away_goals>")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
