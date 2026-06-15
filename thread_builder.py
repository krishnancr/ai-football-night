#!/usr/bin/env python3
"""
Compose ONE postable thread (THREAD.md) for a whole match day.

This is the daily build's headline artifact: every match's picks card plus the
sack-race card, assembled into a single copy-paste thread with the right tweet
copy and hashtags. No LLM calls and no network — every line is composed from
fields the (already-paid) debate produced (match_headline, tweet_hook,
most_outrageous_take) and from track_record standings, so the daily path stays
deterministic and free. It lands in runs/<date>/THREAD.md so CI commits it.
"""
import json
from pathlib import Path

import teams
from render_card import flag_code
from track_record import build_track_records

ROLE_ORDER = ["Stat_Bot", "G_Bot", "R_Bot"]
EVERGREEN_TAGS = "#FIFAWorldCup #WeAre26"
FINALE_TAGS = "#FIFAWorldCup"

# flagcdn codes that aren't a plain 2-letter ISO pair have no regional-indicator
# emoji — the home nations use the subdivision tag sequence instead.
_SPECIAL_FLAG = {
    "gb-eng": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
    "gb-sct": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
    "gb-wls": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
}


def flag_emoji(name: str) -> str:
    """Unicode flag for a team name via its flagcdn code; '' if unknown."""
    code = flag_code(name)
    if not code:
        return ""
    if code in _SPECIAL_FLAG:
        return _SPECIAL_FLAG[code]
    if len(code) == 2 and code.isalpha():
        return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in code.lower())
    return ""


def match_hashtag(home: str, away: str) -> str:
    """Per-match tag in FIFA's convention: #HOMAWA from the official trigrams."""
    return f"#{teams.fifa_code(home)}{teams.fifa_code(away)}"


def _teams(run: dict) -> tuple:
    match_string = run.get("match_string", "Home vs Away")
    if " vs " in match_string:
        home, away = [t.strip() for t in match_string.split(" vs ", 1)]
        return home, away
    return "Home", "Away"


def _trim(text: str, limit: int = 200) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _lean(home_goals: int, away_goals: int) -> str:
    return "H" if home_goals > away_goals else ("A" if away_goals > home_goals else "D")


def _outlier_note(preds: dict) -> str:
    """' R_Bot is the outlier.' when exactly one pundit leans against the others."""
    from collections import Counter
    leans = {r: _lean(p["home_goals"], p["away_goals"]) for r, p in preds.items()}
    if len(set(leans.values())) <= 1:
        return ""
    counts = Counter(leans.values())
    minority = [r for r, lv in leans.items() if counts[lv] == 1]
    return f" {minority[0]} is the outlier." if len(minority) == 1 else ""


def _card_path(date_str: str, run: dict) -> str:
    slug = run.get("match_slug", "")
    return f"runs/{date_str}/wc_{slug}_card.png"


def _load_day_runs(date_dir: Path) -> list:
    """Completed run dicts for a date dir (skips sidecars, parse-errors, non-dicts)."""
    runs = []
    for f in sorted(date_dir.glob("wc_*.json")):
        if f.name.endswith(("_context.json", "_thread.json", "_reasoning.json")):
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        decision = data.get("decision") if isinstance(data, dict) else None
        if decision and not decision.get("parse_error"):
            runs.append(data)
    return runs


def _lead_block(run: dict, n_games: int, date_str: str, total_posts: int) -> str:
    home, away = _teams(run)
    d = run["decision"]
    hg, ag = d["home_goals"], d["away_goals"]
    conf = int(d.get("confidence", 0) * 100)
    hook = _trim(d.get("tweet_hook") or d.get("most_outrageous_take") or "")
    hf, af = flag_emoji(home), flag_emoji(away)
    games_word = "game" if n_games == 1 else "games"
    body = (
        f"{n_games} World Cup {games_word} today. Our 4 AI pundits agreed on almost nothing. 🧵\n\n"
        f"Most confident call of the day — {conf}%:\n"
        f"{hf} {home} {hg}–{ag} {away} {af}\n\n"
        f"{hook}\n\n"
        f"{EVERGREEN_TAGS} {match_hashtag(home, away)}"
    )
    return (
        f"## Post 1/{total_posts} — LEAD  ·  attach `{_card_path(date_str, run)}`\n\n"
        f"```\n{body}\n```"
    )


def _match_block(run: dict, position: int, date_str: str, total_posts: int) -> str:
    home, away = _teams(run)
    d = run["decision"]
    hg, ag = d["home_goals"], d["away_goals"]
    hook = _trim(d.get("tweet_hook") or d.get("match_headline") or "")
    hf, af = flag_emoji(home), flag_emoji(away)
    preds = run.get("pundit_predictions") or {}
    pick_lines = [
        f"• {r} → {preds[r]['home_goals']}–{preds[r]['away_goals']}"
        for r in ROLE_ORDER if r in preds
    ]
    picks = ("\n".join(pick_lines) + "\n\n") if pick_lines else ""
    body = (
        f"{hf} {home} vs {away} {af}\n\n"
        f"{hook}\n\n"
        f"{picks}"
        f"Verdict: {hg}–{ag}.{_outlier_note(preds)}\n\n"
        f"{EVERGREEN_TAGS} {match_hashtag(home, away)}"
    )
    return (
        f"## Post {position}/{total_posts}  ·  attach `{_card_path(date_str, run)}`\n\n"
        f"```\n{body}\n```"
    )


def _standings_sentence(records: dict) -> str:
    if not records:
        return "Standings open — the first results are still to land."
    standings = sorted(
        records.items(),
        key=lambda kv: (-kv[1]["correct_result"], -kv[1]["correct_scoreline"]),
    )
    total = max(v["matches"] for _, v in standings)
    top = standings[0][1]["correct_result"]
    leaders = [r for r, v in standings if v["correct_result"] == top]
    bottom_role, bottom = standings[-1]
    if len(leaders) == 1:
        lead_txt = f"{leaders[0]} leads with {top}/{total} correct"
    elif len(leaders) == 2:
        lead_txt = f"{leaders[0]} & {leaders[1]} lead, tied at {top} correct"
    else:
        lead_txt = f"{', '.join(leaders)} lead, tied at {top} correct"
    return (f"After {total} matches: {lead_txt}. "
            f"{bottom_role} sits bottom with just {bottom['correct_result']} right.")


def _finale_block(records: dict, date_str: str, total_posts: int) -> str:
    body = (
        "This is what they're actually playing for. 🪑\n\n"
        f"{_standings_sentence(records)}\n\n"
        "One more bad week and there's a seat by the door. 👇\n\n"
        f"{FINALE_TAGS}"
    )
    return (
        f"## Post {total_posts}/{total_posts} — FINALE  ·  attach `runs/{date_str}/sack_race.png`\n\n"
        f"```\n{body}\n```"
    )


def _pretty_date(date_str: str) -> str:
    """2026-06-15 → '15 Jun 2026'; passthrough if not a date."""
    from datetime import datetime
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%-d %b %Y")
    except ValueError:
        return date_str


def build_thread_md(date_str: str, runs_root: Path = Path("runs")) -> str:
    """The full THREAD.md text for a match day, or '' if there are no usable runs."""
    runs = _load_day_runs(runs_root / date_str)
    if not runs:
        return ""
    # Highest confidence leads the thread — that's what shows in-timeline.
    runs.sort(key=lambda r: r["decision"].get("confidence", 0), reverse=True)
    records = build_track_records(runs_root)

    n_games = len(runs)
    total_posts = n_games + 1
    parts = [
        f"# Daily thread — {_pretty_date(date_str)} ({n_games} "
        f"{'game' if n_games == 1 else 'games'} + Sack Race)",
        "",
        "Post as a single thread. One image per post. Lead post is what shows "
        "in-timeline, so it carries the strongest hook.",
        "",
        "---",
        "",
        _lead_block(runs[0], n_games, date_str, total_posts),
        "",
        "---",
        "",
    ]
    for i, run in enumerate(runs[1:], start=2):
        parts += [_match_block(run, i, date_str, total_posts), "", "---", ""]
    parts += [_finale_block(records, date_str, total_posts), "", "---", ""]
    parts += [
        "**After full time:** reply to Post 1 with the receipts (who called it, "
        "who got it wrong) — that's act two, where the season-long story compounds.",
        "",
    ]
    return "\n".join(parts)


def write_thread_md(date_str: str, runs_root: Path = Path("runs")) -> Path | None:
    """Write runs/<date>/THREAD.md. Returns the path, or None if there's nothing to post."""
    text = build_thread_md(date_str, runs_root)
    if not text:
        return None
    path = runs_root / date_str / "THREAD.md"
    path.write_text(text, encoding="utf-8")
    return path


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    if not date:
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = write_thread_md(date)
    print(f"Wrote {out}" if out else f"No usable runs for {date} — nothing written")
