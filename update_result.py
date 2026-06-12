#!/usr/bin/env python3
"""
Record the actual result of a match in its run JSON and print accuracy.
Usage: python update_result.py runs/wc_brazil-croatia_20260611.json 2 1
"""
import json
import sys
import traceback
from pathlib import Path


def update_result(run_path: Path, home_goals: int, away_goals: int) -> dict:
    """
    Add actual result to run JSON. Returns the actual result dict.
    Mutates the file at run_path in place.
    """
    run_path = Path(run_path)
    with open(run_path) as f:
        run = json.load(f)

    predicted = run.get("decision", {})
    pred_home = predicted.get("home_goals", -1)
    pred_away = predicted.get("away_goals", -1)
    pred_result = predicted.get("result", "")

    if home_goals > away_goals:
        actual_result = "home_win"
    elif home_goals == away_goals:
        actual_result = "draw"
    else:
        actual_result = "away_win"

    correct_scoreline = (pred_home == home_goals and pred_away == away_goals)
    correct_result = (pred_result == actual_result)

    actual = {
        "home_goals": home_goals,
        "away_goals": away_goals,
        "result": actual_result,
        "correct_scoreline": correct_scoreline,
        "correct_result": correct_result,
    }
    run["actual"] = actual

    with open(run_path, "w") as f:
        json.dump(run, f, indent=2)

    # Emit paste-ready receipts reply (act two of the prediction tweet).
    # Never let receipts formatting break result recording.
    try:
        from post_pack import format_receipts
        receipts_path = run_path.parent / f"{run_path.stem}_receipts.md"
        receipts_path.write_text(format_receipts(run), encoding="utf-8")
        print(f"   Receipts reply: {receipts_path}")
    except Exception as e:
        print(f"   ⚠️  Receipts emission failed (result still recorded): {type(e).__name__}: {e}")
        traceback.print_exc()

    match_str = run.get("match_string", run_path.stem)
    score_emoji = "✅" if correct_scoreline else ("🟡" if correct_result else "❌")
    print(f"\n{score_emoji} {match_str}: predicted {pred_home}-{pred_away}, actual {home_goals}-{away_goals}")
    print(f"   Scoreline correct: {correct_scoreline} | Result correct: {correct_result}")

    return actual


def compute_tournament_accuracy(runs_dir: Path = Path("runs")) -> dict:
    """Scan all wc_*.json files with 'actual' field and return aggregate accuracy."""
    results = {"total": 0, "correct_scoreline": 0, "correct_result": 0}
    for path in sorted(runs_dir.glob("wc_*.json")):
        if path.name.endswith(("_context.json", "_thread.json", "_reasoning.json")):
            continue
        try:
            run = json.loads(path.read_text())
            if "actual" in run:
                results["total"] += 1
                if run["actual"]["correct_scoreline"]:
                    results["correct_scoreline"] += 1
                if run["actual"]["correct_result"]:
                    results["correct_result"] += 1
        except Exception:
            pass
    return results


def main():
    if len(sys.argv) != 4:
        print("Usage: python update_result.py <run_file> <home_goals> <away_goals>")
        print("Example: python update_result.py runs/wc_brazil-croatia_20260611.json 2 1")
        sys.exit(1)

    run_path = Path(sys.argv[1])
    home_goals = int(sys.argv[2])
    away_goals = int(sys.argv[3])

    if not run_path.exists():
        print(f"Error: {run_path} not found")
        sys.exit(1)

    update_result(run_path, home_goals, away_goals)

    # Print tournament totals
    stats = compute_tournament_accuracy(run_path.parent)
    if stats["total"] > 0:
        result_pct = int(stats["correct_result"] / stats["total"] * 100)
        score_pct = int(stats["correct_scoreline"] / stats["total"] * 100)
        print(f"\n📊 Tournament accuracy ({stats['total']} matches):")
        print(f"   Results (W/D/L): {stats['correct_result']}/{stats['total']} ({result_pct}%)")
        print(f"   Scorelines:      {stats['correct_scoreline']}/{stats['total']} ({score_pct}%)")


if __name__ == "__main__":
    main()
