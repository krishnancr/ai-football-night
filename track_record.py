#!/usr/bin/env python3
"""
Per-pundit prediction tracking.

Each debater ends their proposal/rebuttal with a "PREDICTION: X-Y" line
(instruction lives in personas.json). This module extracts those, scores them
against recorded actual results, and builds a track-record block that
run_matchday.py injects into each pundit's system prompt — so every pundit
knows their own record and the panel standings before the next debate.
"""
import json
import re
from pathlib import Path

PREDICTION_RE = re.compile(r"PREDICTION:\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})")
# Fallback: tolerate team names / stray words between the token and the score,
# e.g. "PREDICTION: Netherlands 2-1 Japan". Stays on the PREDICTION line (. excludes \n).
PREDICTION_LOOSE_RE = re.compile(r"PREDICTION:[^\n]*?(\d{1,2})\s*[-–:]\s*(\d{1,2})", re.IGNORECASE)

# Knockout-only: the team a pundit backs to reach the next round (after ET/pens if
# the 90-min scoreline is level). Captures the rest of the line so multi-word team
# names ("Côte d'Ivoire", "South Africa") survive intact.
ADVANCES_RE = re.compile(r"ADVANCES:\s*([^\n]+)", re.IGNORECASE)
_ADV_STRIP = " \t.*_`\"'•-–"


def parse_pundit_prediction(text):
    """Last 'PREDICTION: X-Y' in text → {'home_goals': X, 'away_goals': Y}, or None.

    Tries the strict format first; falls back to a looser match that survives a
    model writing the line with team names ('PREDICTION: Netherlands 2-1 Japan').
    """
    text = text or ""
    matches = PREDICTION_RE.findall(text) or PREDICTION_LOOSE_RE.findall(text)
    if not matches:
        return None
    home, away = matches[-1]
    return {"home_goals": int(home), "away_goals": int(away)}


def parse_pundit_advances(text):
    """Last 'ADVANCES: <team>' in text → the team name string, or None.

    Robust like parse_pundit_prediction: takes the last occurrence and trims
    surrounding markdown/punctuation while preserving internal spaces and
    apostrophes so multi-word names stay intact.
    """
    text = text or ""
    matches = ADVANCES_RE.findall(text)
    if not matches:
        return None
    team = matches[-1].strip().strip(_ADV_STRIP).strip()
    return team or None


def extract_pundit_predictions(full_debate: dict) -> dict:
    """Per-role final (POST-debate) prediction: rebuttal wins over proposal."""
    proposals = full_debate.get("proposals", {})
    rebuttals = full_debate.get("rebuttals", {})
    predictions = {}
    for role in proposals:
        pred = parse_pundit_prediction(rebuttals.get(role)) or parse_pundit_prediction(proposals.get(role))
        if pred:
            predictions[role] = pred
    return predictions


def extract_pre_debate_predictions(full_debate: dict) -> dict:
    """Per-role PRE-debate prediction: proposal round only, before anyone argues.

    Paired with extract_pundit_predictions (post-debate) this is the control for
    'does the debate change — and improve — each model's call?'. Backfillable over
    existing runs since proposals are already stored in full_debate.
    """
    proposals = full_debate.get("proposals", {})
    predictions = {}
    for role in proposals:
        pred = parse_pundit_prediction(proposals.get(role))
        if pred:
            predictions[role] = pred
    return predictions


def extract_pundit_advances(full_debate: dict) -> dict:
    """Per-role final 'who advances' pick: rebuttal wins over proposal.

    Knockout-only — for group matches pundits emit no ADVANCES line, so this is
    simply empty and nothing downstream scores an advance.
    """
    proposals = full_debate.get("proposals", {})
    rebuttals = full_debate.get("rebuttals", {})
    advances = {}
    for role in proposals:
        pick = parse_pundit_advances(rebuttals.get(role)) or parse_pundit_advances(proposals.get(role))
        if pick:
            advances[role] = pick
    return advances


def _norm_team(name) -> str:
    """Loose team-name key for advance comparison (case/space/punctuation-insensitive)."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def build_track_records_from_runs(runs: list) -> dict:
    """Score every run that has both pundit_predictions and a recorded actual result."""
    records = {}
    for run in runs:
        actual = run.get("actual")
        preds = run.get("pundit_predictions")
        if not actual or not preds:
            continue
        advances = run.get("pundit_advances") or {}
        # Knockout-only: scored only when result-entry has recorded who actually went through.
        actual_advanced = actual.get("advanced")
        for role, pred in preds.items():
            rec = records.setdefault(role, {"matches": 0, "correct_result": 0, "correct_scoreline": 0,
                                            "advance_matches": 0, "advance_correct": 0, "last": None})
            correct_result = _result(pred["home_goals"], pred["away_goals"]) == actual["result"]
            correct_scoreline = (pred["home_goals"] == actual["home_goals"]
                                 and pred["away_goals"] == actual["away_goals"])
            rec["matches"] += 1
            rec["correct_result"] += int(correct_result)
            rec["correct_scoreline"] += int(correct_scoreline)
            rec["last"] = {
                "match": run.get("match_string", "?"),
                "predicted": f"{pred['home_goals']}-{pred['away_goals']}",
                "actual": f"{actual['home_goals']}-{actual['away_goals']}",
                "correct_result": correct_result,
            }
            # Separate binary advance-accuracy track (does not touch scoreline/result scoring).
            adv_pick = advances.get(role)
            if adv_pick and actual_advanced:
                rec["advance_matches"] += 1
                rec["advance_correct"] += int(_norm_team(adv_pick) == _norm_team(actual_advanced))
    return records


def _stage_for_date(date_dir: Path, cache: dict) -> str:
    """Stage of a run-day from its daily_summary.json 'stage' field.

    Safe default 'group': every historical run predates the knockouts, and an
    unknown/missing summary must never leak group matches into a knockout query.
    """
    key = date_dir.name
    if key in cache:
        return cache[key]
    stage = "group"
    try:
        data = json.loads((date_dir / "daily_summary.json").read_text())
        if isinstance(data, dict) and data.get("stage"):
            stage = data["stage"]
    except Exception:
        pass
    cache[key] = stage
    return stage


def build_track_records(runs_dir: Path = Path("runs"), stage: str = None) -> dict:
    """Score every completed run. With stage=('group'|'knockout'), restrict to runs
    from days of that stage — so the knockout leaderboard resets and the group
    record stays frozen as the group-stage epitaph. stage=None scores all-time."""
    runs = []
    stage_cache: dict = {}
    for path in sorted(runs_dir.glob("????-??-??/wc_*.json")):
        if path.name.endswith(("_context.json", "_thread.json", "_reasoning.json")):
            continue
        if stage is not None and _stage_for_date(path.parent, stage_cache) != stage:
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict):  # defensive: only run dicts, never sidecar lists
            runs.append(data)
    return build_track_records_from_runs(runs)


def format_track_record_block(role: str, records: dict) -> str:
    """Track-record paragraph for one pundit's system prompt. Empty string if no data."""
    rec = records.get(role)
    if not rec:
        return ""
    lines = [
        f"YOUR TRACK RECORD: {rec['correct_result']}/{rec['matches']} correct results, "
        f"{rec['correct_scoreline']}/{rec['matches']} exact scorelines."
    ]
    if rec.get("advance_matches"):
        lines.append(
            f"WHO-ADVANCES CALLS: {rec.get('advance_correct', 0)}/{rec['advance_matches']} "
            f"correct on which team went through."
        )
    last = rec.get("last")
    if last:
        verdict = "you got the result right" if last["correct_result"] else "you got it WRONG"
        lines.append(
            f"Last match ({last['match']}): you predicted {last['predicted']}, "
            f"it ended {last['actual']} — {verdict}."
        )
    standings = sorted(records.items(), key=lambda kv: (-kv[1]["correct_result"], -kv[1]["correct_scoreline"]))
    table = ", ".join(f"{r} {v['correct_result']}/{v['matches']}" for r, v in standings)
    lines.append(f"PANEL STANDINGS: {table}.")
    if len(standings) >= 2:
        pos = [r for r, _ in standings].index(role) + 1
        # Anti-conformity framing: the stakes must push pundits to double down on
        # their own style, not herd toward consensus/favorites. "Bland gets sacked
        # first" points the incentive gradient away from agreement.
        stakes = (f"SACK RACE: the pundit at the bottom of the panel standings after the "
                  f"group stage will be SACKED and replaced on air. You are currently {pos} of {len(standings)}. "
                  f"Know how the sacking really gets decided: the table matters, but the producers protect "
                  f"pundits the audience loves. Hedging, copying the panel consensus, or sounding like the "
                  f"others is the fastest way out — bland pundits get sacked first.")
        if pos == len(standings):
            stakes += (" You are in the SACK ZONE. Do not play it safe — double down on your way of "
                       "seeing football and make this debate unmissable.")
        lines.append(stakes)
    lines.append("Learn from your misses and sharpen this prediction — but never break character.")
    return "\n".join(lines)


def inject_track_records(persona_set: dict, records: dict) -> dict:
    """Copy of persona_set with track-record blocks appended to each non-Judge system prompt."""
    out = {}
    for role, config in persona_set.items():
        config = dict(config)
        if role != "K_Bot":
            block = format_track_record_block(role, records)
            if block:
                config["system"] = config["system"] + "\n\n" + block
        out[role] = config
    return out
