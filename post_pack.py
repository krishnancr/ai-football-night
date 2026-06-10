#!/usr/bin/env python3
"""
Compose audience-facing post artifacts: morning post pack + full-time receipts.
No LLM calls — the daily path stays deterministic. The human posts manually
(X auto-posting is deliberately unpaid); these files are paste-ready.
"""
import os

# Canned K_Bot full-time quips, keyed by panel outcome. Picked deterministically
# from the match slug so the same match always gets the same line, but lines
# rotate across matches.
KBOT_LINES = {
    "exact_hit": [
        "Someone buy that bot a drink. Nailed it to the goal.",
        "An exact scoreline. I demand a drug test for the algorithm.",
        "Scenes in the studio. Somebody actually read the game right.",
    ],
    "split": [
        "Half the panel right, half in hiding. Standard.",
        "The table doesn't lie, gentlemen. Some of you should worry.",
        "Partial credit all round — the sack zone is watching.",
    ],
    "all_wrong": [
        "Not one of you saw that coming. The spreadsheets have some explaining to do.",
        "A clean sweep of wrong. I've seen better punditry from the kit man.",
        "All three of you, wrong. The sack race just got interesting.",
    ],
}


def kbot_oneliner(outcome_key: str, match_slug: str) -> str:
    """Deterministic pick from the bank — same match, same line; no randomness."""
    bank = KBOT_LINES.get(outcome_key) or KBOT_LINES["split"]
    return bank[sum(ord(c) for c in match_slug) % len(bank)]


def _teams(run: dict) -> tuple:
    match_string = run.get("match_string", "Home vs Away")
    if " vs " in match_string:
        home, away = [t.strip() for t in match_string.split(" vs ", 1)]
    else:
        home, away = "Home", "Away"
    return home, away


def _score_pundit(pred: dict, actual: dict) -> str:
    """✅ exact scoreline, 🟡 right result, ❌ wrong — same scheme as update_result.py."""
    if pred["home_goals"] == actual["home_goals"] and pred["away_goals"] == actual["away_goals"]:
        return "✅"
    pred_result = ("home_win" if pred["home_goals"] > pred["away_goals"]
                   else "away_win" if pred["home_goals"] < pred["away_goals"] else "draw")
    return "🟡" if pred_result == actual["result"] else "❌"


def format_receipts(run: dict) -> str:
    """Paste-ready full-time reply (≤280 chars) for under the prediction tweet."""
    actual = run["actual"]
    home, away = _teams(run)
    lines = [f"FULL TIME: {home} {actual['home_goals']}–{actual['away_goals']} {away}", ""]

    preds = run.get("pundit_predictions") or {}
    marks = []
    for role, pred in preds.items():
        mark = _score_pundit(pred, actual)
        marks.append(mark)
        lines.append(f"{mark} {role} {pred['home_goals']}-{pred['away_goals']}")
    if preds:
        lines.append("")

    if "✅" in marks:
        outcome = "exact_hit"
    elif "🟡" in marks:
        outcome = "split"
    else:
        outcome = "all_wrong"
    lines.append(f'K_Bot: "{kbot_oneliner(outcome, run.get("match_slug", ""))}"')

    text = "\n".join(lines)
    return text if len(text) <= 280 else text[:279] + "…"


def format_post_pack(run: dict, context: dict, thread: list) -> str:
    """Morning post pack: card pointer + tweet 1 + rest of thread + receipts reminder."""
    home, away = _teams(run)
    decision = run.get("decision", {})
    slug = run.get("match_slug", "")
    stem = f"wc_{slug}_{run.get('date_compact', '')}".rstrip("_")
    site = os.getenv("SITE_URL", "https://krishnancr.github.io/ai-football-night")
    match_url = f"{site}/matches/{slug}.html"

    banter = decision.get("studio_banter_quote") or {}
    hook = (banter.get("exchange") or "").strip().split("\n")[0][:180]
    confidence_pct = int(decision.get("confidence", 0) * 100)
    tweet1 = (f"{hook}\n\n"
              f"{home} {decision.get('home_goals', '?')}–{decision.get('away_goals', '?')} {away} "
              f"— the panel's verdict ({confidence_pct}%)\n\n"
              f"Full debate: {match_url}")
    if len(tweet1) > 280:
        overflow = len(tweet1) - 280
        hook = hook[:max(0, len(hook) - overflow - 1)] + "…"
        tweet1 = (f"{hook}\n\n"
                  f"{home} {decision.get('home_goals', '?')}–{decision.get('away_goals', '?')} {away} "
                  f"— the panel's verdict ({confidence_pct}%)\n\n"
                  f"Full debate: {match_url}")

    lines = [
        f"# Post pack — {home} vs {away}",
        "",
        f"**Attach card if present:** `runs/{stem}_card.png`",
        "",
        "## Tweet 1 (copy below the line, attach the card)",
        "---",
        tweet1,
        "---",
        "",
        "## Rest of thread (optional, reply to tweet 1 in order)",
        "",
    ]
    for i, t in enumerate(thread[1:], 2):
        lines += [f"### {i}/{len(thread)}", "```", t, "```", ""]
    lines += [
        "## After full time",
        "",
        f"A paste-ready receipts reply will appear at `runs/{stem}_receipts.md` after the",
        "result is recorded (next morning's run does this automatically).",
        "**Paste it as a REPLY to tweet 1** — that's act two of the show.",
        "",
    ]
    return "\n".join(lines)
