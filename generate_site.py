#!/usr/bin/env python3
"""
Build the gh-pages site from runs/.

Usage:
  python generate_site.py                      # writes to _site/
  python generate_site.py --output-dir /path
"""
import argparse
import json
from pathlib import Path

RUNS_DIR = Path("runs")
GROUP_LETTERS = set("ABCDEFGHIJKL")

_PUNDITS = [
    {"name": "Stat_Bot", "model": "Qwen 3.7 Max", "color": "#3b82f6",
     "bio": "The numbers guy. xG, progressive passes, expected threat. Football is maths. Full stop."},
    {"name": "G_Bot", "model": "Kimi K2.6", "color": "#8b5cf6",
     "bio": "The tactician. Reads formations like sheet music. Usually right. Never lets you forget it."},
    {"name": "U_Bot", "model": "Nemotron 3 Super", "color": "#ef4444",
     "bio": "The giant-killer. Cup-upset specialist. Backs the one underdog angle the data misses — fatigue, a venue, a keeper in form."},
    {"name": "K_Bot", "model": "DeepSeek V3", "color": "#10b981",
     "bio": "The judge. Hears everyone out. Delivers the final scoreline. No appeals."},
]

_LANDING_CSS = """
.studio-img { width: 100%; border-radius: 12px; display: block; margin-bottom: 24px; max-height: 340px; object-fit: cover; object-position: center top; }
.hero { background: linear-gradient(135deg, #0f3460 0%, #1e293b 100%); border-radius: 12px; padding: 28px; margin-bottom: 28px; }
.hero-title { font-size: 1.35rem; font-weight: 700; color: #60a5fa; margin-bottom: 8px; }
.hero-sub { color: #94a3b8; font-size: 0.88rem; line-height: 1.55; }
.pundits-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; margin-bottom: 28px; }
.pundit-card { background: #1e293b; border-radius: 10px; padding: 14px; border-top: 3px solid; }
.pundit-name { font-weight: 700; font-size: 0.9rem; margin-bottom: 3px; }
.pundit-model { font-size: 0.68rem; color: #475569; margin-bottom: 8px; letter-spacing: 0.03em; }
.pundit-bio { font-size: 0.78rem; color: #94a3b8; line-height: 1.45; }
.upcoming-row { background: #1e293b; border-radius: 6px; padding: 9px 14px; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem; }
.upcoming-teams { font-weight: 600; }
.upcoming-badge { font-size: 0.68rem; color: #475569; background: #0f172a; padding: 2px 8px; border-radius: 4px; }
.banter-label { font-size: 0.7rem; color: #475569; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 12px; }
.banter-chat { background: #0f172a; border-radius: 10px; padding: 16px; margin-bottom: 28px; border: 1px solid #1e293b; }
.banter-row { display: flex; gap: 8px; margin-bottom: 10px; align-items: flex-start; }
.banter-bubble { background: #1e293b; border-radius: 4px 14px 14px 14px; padding: 8px 12px; max-width: 88%; }
.banter-name { font-size: 0.68rem; font-weight: 700; margin-bottom: 3px; }
.banter-text { font-size: 0.85rem; line-height: 1.45; color: #e2e8f0; }
.banter-row.judge .banter-bubble { background: #0d2618; border: 1px solid #166534; }
.banter-row.right { flex-direction: row-reverse; }
.banter-row.right .banter-bubble { margin-left: auto; border-radius: 14px 4px 14px 14px; }
"""

_ARTICLE_CSS = """
.article { max-width: 720px; margin: 0 auto; }
.article .back-link { display: inline-block; color: #60a5fa; text-decoration: none; font-size: 0.82rem; margin-bottom: 24px; }
.article .back-link:hover { text-decoration: underline; }
.article h1 { font-size: 1.7rem; font-weight: 800; line-height: 1.25; margin-bottom: 16px; color: #f1f5f9; }
.article h2 { font-size: 1.15rem; font-weight: 700; color: #60a5fa; letter-spacing: 0; text-transform: none; margin: 36px 0 12px; }
.article p { font-size: 0.98rem; line-height: 1.7; color: #cbd5e1; margin-bottom: 18px; }
.article ul { margin: 0 0 18px 22px; }
.article li { font-size: 0.98rem; line-height: 1.7; color: #cbd5e1; margin-bottom: 8px; }
.article strong { color: #f1f5f9; font-weight: 700; }
.article em { color: #94a3b8; }
.article hr { border: none; border-top: 1px solid #1e293b; margin: 28px 0; }
.article code { background: #1e293b; padding: 1px 6px; border-radius: 4px; font-size: 0.85em; }
.article-byline { color: #64748b; font-size: 0.85rem; margin: -6px 0 26px; }
.read-article { display: inline-block; background: #1e293b; color: #cbd5e1; text-decoration: none; border-radius: 6px; padding: 8px 14px; font-size: 0.8rem; margin-bottom: 24px; border: 1px solid #334155; }
.read-article:hover { background: #273549; color: #f1f5f9; }
"""

_SAMPLE_BANTER = [
    {"role": "Stat_Bot",
     "text": "UCL Final. Arsenal's xG this campaign: 2.6 per game. PSG's: 2.2. Havertz has scored in four consecutive European knockout games. The data says Arsenal end their 36-year wait tonight. This is not sentiment. This is arithmetic."},
    {"role": "U_Bot",
     "text": "I have heard 'this is Arsenal's year' every year since 2006. Dembélé is unplayable in a final, PSG held the cup last year, and Havertz will spend the second half explaining a yellow card to a referee who does not care."},
    {"role": "G_Bot",
     "text": "Both of you are missing the tactical key. Arsenal press in a 4-3-3 but PSG's double pivot sits deep and funnels everything wide. This is entirely about whether Saka can beat their left back one-on-one for ninety minutes. If yes, Arsenal. If PSG adjust at half-time, we go to extra time."},
    {"role": "Stat_Bot",
     "text": "G_Bot said 'if yes' as his entire analysis. That is not a number. That is a coin flip with a blazer on."},
    {"role": "U_Bot",
     "text": "PSG 2-0. Dembélé first half, something scrambled late. Arsenal will hit the post at least once and somebody will write a very long article about it."},
    {"role": "K_Bot",
     "text": "Arsenal score early, PSG equalise from a penalty, it goes to extra time. Someone misses in the shootout and PSG retain. Stat_Bot's model will be technically correct and completely useless. U_Bot will insist he was basically right. Prediction locked. — Actual result: PSG 1–1 Arsenal AET, PSG win 4–3 on pens. Gabriel Magalhães misses the fifth. Called it."},
]

ROLE_COLORS = {
    "Stat_Bot": "#3b82f6",
    "G_Bot": "#8b5cf6",
    "U_Bot": "#ef4444",
    "K_Bot": "#10b981",
    # Legacy key names (old run files degrade gracefully — get default colour)
    "R_Bot": "#f97316",   # sacked after the group stage; kept so epitaph pages still colour
    "Statman": "#3b82f6",
    "TacticalAnalyst": "#8b5cf6",
    "Contrarian": "#f97316",
    "Judge": "#10b981",
}

ABRIDGE_LEN = 340  # chars shown before "read more"


def _pundits_html() -> str:
    cards = "".join(
        f'<div class="pundit-card" style="border-top-color:{p["color"]};">'
        f'<div class="pundit-name" style="color:{p["color"]};">{p["name"]}</div>'
        f'<div class="pundit-model">{p["model"]}</div>'
        f'<div class="pundit-bio">{p["bio"]}</div>'
        f'</div>'
        for p in _PUNDITS
    )
    return f'<section><h2>The Panel</h2><div class="pundits-grid">{cards}</div></section>'


def _upcoming_html(schedule: list, from_date_str: str, days: int = 7, exclude: set = None) -> str:
    """Fixtures from from_date_str (inclusive) for `days` days ahead.

    `exclude` is a set of (iso_date, match_string) tuples for fixtures that
    already have a published prediction — those are skipped here.
    """
    from datetime import datetime, timedelta
    from itertools import groupby as _groupby
    exclude = exclude or set()
    try:
        start = datetime.strptime(from_date_str, "%Y%m%d").date()
    except ValueError:
        return ""
    end = start + timedelta(days=days)
    matches = [
        (datetime.strptime(m["date"], "%Y-%m-%d").date(), m)
        for m in schedule
        if start <= datetime.strptime(m["date"], "%Y-%m-%d").date() <= end
        and (m["date"], m.get("match_string", f'{m["home"]} vs {m["away"]}')) not in exclude
    ]
    if not matches:
        return ""
    rows_by_date = ""
    for date, grp in _groupby(matches, key=lambda x: x[0]):
        day_rows = "".join(
            f'<div class="upcoming-row">'
            f'<span class="upcoming-teams">{m["home"]} vs {m["away"]}</span>'
            f'<span class="upcoming-badge">Gp {m["group"]}</span>'
            f'</div>'
            for _, m in grp
        )
        rows_by_date += f'<div class="day-group"><h3>{date.strftime("%B %-d")}</h3>{day_rows}</div>\n'
    return f'<section><h2>Coming Up</h2>{rows_by_date}</section>'


def _sample_banter_html(collapsed: bool = False) -> str:
    rows = ""
    for i, msg in enumerate(_SAMPLE_BANTER):
        role = msg["role"]
        color = ROLE_COLORS.get(role, "#64748b")
        name = role
        judge_class = " judge" if role == "K_Bot" else ""
        side_class = " right" if i % 2 else ""
        rows += (
            f'<div class="banter-row{judge_class}{side_class}">'
            f'<div class="avatar" style="background:{color};width:28px;height:28px;border-radius:50%;'
            f'display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:700;'
            f'color:white;flex-shrink:0;">{name[0]}</div>'
            f'<div class="banter-bubble">'
            f'<div class="banter-name" style="color:{color};">{name}</div>'
            f'<div class="banter-text">{msg["text"]}</div>'
            f'</div></div>\n'
        )
    chat = f'<div class="banter-chat">{rows}</div>'
    label = "From the studio — UCL Final, PSG vs Arsenal, May 2026"
    if collapsed:
        return (
            f'<details style="margin-bottom:28px;">'
            f'<summary style="cursor:pointer;font-size:0.75rem;color:#475569;letter-spacing:0.08em;'
            f'text-transform:uppercase;padding:8px 0;list-style:none;">'
            f'▸ What the studio sounds like — UCL Final preview</summary>'
            f'<div style="margin-top:12px;">{chat}</div>'
            f'</details>'
        )
    return (
        f'<div class="banter-label">{label}</div>'
        f'{chat}'
    )


def _display(role: str) -> str:
    # Legacy mapping so old runs still show bot names
    legacy = {"Statman": "Stat_Bot", "TacticalAnalyst": "G_Bot", "Contrarian": "R_Bot", "Judge": "K_Bot"}
    return legacy.get(role, role)


def _abridge(text: str, role: str) -> str:
    """Return HTML with first ABRIDGE_LEN chars visible, rest in a <details> expander."""
    text = str(text).strip()
    if len(text) <= ABRIDGE_LEN:
        return text
    cut = text.rfind(" ", 0, ABRIDGE_LEN) or ABRIDGE_LEN
    preview = text[:cut]
    rest = text[cut:].strip()
    return (
        f'{preview}… '
        f'<details class="msg-expand"><summary>read more</summary>{rest}</details>'
    )


def load_run_pairs(runs_dir: Path = RUNS_DIR) -> list:
    """Load all (run, context) pairs sorted by filename date ascending."""
    run_files = sorted(
        f for f in runs_dir.glob("????-??-??/wc_*.json")
        if not any(f.name.endswith(s) for s in ("_context.json", "_thread.json", "_reasoning.json"))
    )
    pairs = []
    for run_file in run_files:
        # Context moved to _debug/ in the daily-output restructure; old committed
        # runs still have it flat beside the run JSON, so check both locations.
        ctx_name = run_file.name.replace(".json", "_context.json")
        context_file = run_file.parent / "_debug" / ctx_name
        if not context_file.exists():
            context_file = run_file.parent / ctx_name
        run = json.loads(run_file.read_text())
        # Skip dev artifacts that share the wc_*.json glob (reel scripts, show-render
        # specs, golden/mock fixtures, reel-derived runs): a real prediction run
        # always carries both a "decision" and a "match_string".
        if not isinstance(run, dict) or "decision" not in run or "match_string" not in run:
            continue
        context = json.loads(context_file.read_text()) if context_file.exists() else {}
        date_str = run_file.parent.name.replace("-", "")  # YYYY-MM-DD → YYYYMMDD
        pairs.append({"run": run, "context": context, "date_str": date_str})
    return pairs


def is_knockout_match(context: dict) -> bool:
    group = (context.get("group") or "").upper()
    # Handle both "A" and "Group A" from the research context
    letter = group.split()[-1] if group else ""
    return letter not in GROUP_LETTERS


def accuracy_stats(run_pairs: list) -> dict:
    total = correct_result = correct_scoreline = 0
    for pair in run_pairs:
        run = pair["run"]
        # Support both flat format (actual_home_goals) and nested format (actual.home_goals)
        if "actual_home_goals" in run:
            total += 1
            if run.get("correct_result"):
                correct_result += 1
            if run.get("correct_scoreline"):
                correct_scoreline += 1
        elif "actual" in run:
            total += 1
            actual = run["actual"]
            if actual.get("correct_result"):
                correct_result += 1
            if actual.get("correct_scoreline"):
                correct_scoreline += 1
    return {"total": total, "correct_result": correct_result, "correct_scoreline": correct_scoreline}


def _leaderboard_html(run_pairs: list) -> str:
    from track_record import build_track_records_from_runs
    records = build_track_records_from_runs([p["run"] for p in run_pairs])
    if not records:
        return ""
    standings = sorted(records.items(), key=lambda kv: (-kv[1]["correct_result"], -kv[1]["correct_scoreline"]))
    rows = "".join(
        f'<div class="lb-row"><span style="color:{ROLE_COLORS.get(role, "#94a3b8")};font-weight:600;">{_display(role)}</span>'
        f'<span class="lb-stat">{rec["correct_result"]}/{rec["matches"]} results · {rec["correct_scoreline"]} exact</span></div>'
        for role, rec in standings
    )
    return f'<section class="leaderboard"><h2>Pundit table</h2>{rows}</section>'


_INDEX_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0f172a; color: #e2e8f0; font-family: system-ui, -apple-system, sans-serif; max-width: 860px; margin: 0 auto; padding: 16px; }
header { padding: 24px 0 16px; border-bottom: 1px solid #1e293b; margin-bottom: 24px; }
header h1 { font-size: 1.5rem; font-weight: 700; }
header p { color: #64748b; font-size: 0.85rem; margin-top: 4px; }
.accuracy-pill { background: #14532d; color: #86efac; border-radius: 6px; padding: 8px 14px; font-size: 0.8rem; display: inline-block; margin-bottom: 24px; }
h2 { font-size: 1rem; font-weight: 600; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 12px; }
.match-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-bottom: 32px; }
.match-card { background: linear-gradient(135deg, #1e3a5f, #1e293b); border-radius: 10px; padding: 14px; text-decoration: none; color: inherit; display: block; }
.match-card:hover { background: linear-gradient(135deg, #1e4a7f, #273549); }
.group-badge { font-size: 0.7rem; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; }
.teams { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.team { font-weight: 600; font-size: 0.85rem; }
.score { background: #0f172a; color: #60a5fa; font-size: 1.1rem; font-weight: 700; padding: 3px 10px; border-radius: 5px; }
.confidence { font-size: 0.75rem; color: #64748b; }
.result-badge { font-size: 0.75rem; margin-top: 4px; }
.archive-section { margin-top: 8px; }
.day-group { margin-bottom: 20px; }
.day-group h3 { font-size: 0.85rem; color: #475569; margin-bottom: 8px; }
.archive-row { background: #1e293b; border-radius: 6px; padding: 10px 14px; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center; text-decoration: none; color: inherit; font-size: 0.85rem; }
.archive-row:hover { background: #273549; }
.archive-result { font-size: 0.8rem; color: #64748b; }
a { color: inherit; }
.leaderboard { margin-bottom: 28px; }
.lb-row { background: #1e293b; border-radius: 6px; padding: 8px 14px; margin-bottom: 4px; display: flex; justify-content: space-between; font-size: 0.85rem; }
.lb-stat { color: #64748b; }
"""


def _fmt_date(date_str: str) -> str:
    """'20260613' → 'June 13'"""
    from datetime import datetime
    return datetime.strptime(date_str, "%Y%m%d").strftime("%B %-d")


def _get_actual(run: dict):
    """Return (home_goals, away_goals, correct_result) from either result format, or None."""
    if "actual_home_goals" in run and "actual_away_goals" in run:
        return run["actual_home_goals"], run["actual_away_goals"], run.get("correct_result", False)
    if "actual" in run:
        a = run["actual"]
        return a["home_goals"], a["away_goals"], a.get("correct_result", False)
    return None


def _match_card_html(pair: dict) -> str:
    run = pair["run"]
    context = pair["context"]
    decision = run["decision"]
    home = context.get("home_team") or run["match_string"].split(" vs ")[0].strip()
    away = context.get("away_team") or run["match_string"].split(" vs ")[1].strip()
    group = context.get("group", "")
    slug = run.get("match_slug", "")
    home_g = decision["home_goals"]
    away_g = decision["away_goals"]
    confidence = int(decision.get("confidence", 0) * 100)

    result_badge = ""
    actual = _get_actual(run)
    if actual is not None:
        ah, aa, correct = actual
        icon = "✅" if correct else "❌"
        result_badge = f'<div class="result-badge">{icon} Actual: {ah}–{aa}</div>'

    return f"""<a class="match-card" href="matches/{slug}.html">
  <div class="group-badge">Group {group}</div>
  <div class="teams">
    <span class="team">{home}</span>
    <div class="score">{home_g}–{away_g}</div>
    <span class="team">{away}</span>
  </div>
  <div class="confidence">{confidence}% confident</div>
  {result_badge}
</a>"""


def generate_index_html(run_pairs: list, today_str: str, schedule: list = None) -> str:
    schedule = schedule or []

    # ── Landing page: no predictions yet ────────────────────────────
    if not run_pairs:
        upcoming_section = _upcoming_html(schedule, today_str) if schedule else ""
        pundits_section = _pundits_html()
        banter_section = _sample_banter_html()
        hero = (
            '<div class="hero">'
            '<div class="hero-title">Predictions for every World Cup 2026 match.</div>'
            '<div class="hero-sub">Four AI pundits debate every fixture — Stat_Bot runs the numbers, '
            'G_Bot reads the tactics, U_Bot hunts the giant-killing upset, K_Bot delivers the final word. '
            'Predictions drop before each kickoff.</div>'
            '</div>'
        )
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Football Night — WC 2026</title>
  <style>{_INDEX_CSS}{_LANDING_CSS}</style>
</head>
<body>
  <header>
    <h1>AI Football Night</h1>
    <p>Four AI pundits. One studio. Every World Cup 2026 match.</p>
  </header>
  <img class="studio-img" src="assets/studio.png" alt="AI Football Night studio">
  <a class="read-article" href="retrospective.html">📝 Read the group-stage retrospective — what a month of AI arguing actually proved</a>
  {hero}
  {banter_section}
  {pundits_section}
  {upcoming_section}
</body>
</html>"""

    # ── Normal state: predictions exist ─────────────────────────────
    stats = accuracy_stats(run_pairs)
    accuracy_text = (
        f"{stats['correct_result']}/{stats['total']} results correct · "
        f"{stats['correct_scoreline']}/{stats['total']} exact scorelines"
        if stats["total"] else "No results recorded yet"
    )

    today_pairs = [p for p in run_pairs if p["date_str"] == today_str]
    today_cards = "\n".join(_match_card_html(p) for p in today_pairs)
    today_section = f"""<section>
  <h2>Today · {_fmt_date(today_str)}</h2>
  <div class="match-grid">{today_cards}</div>
</section>""" if today_pairs else ""

    from itertools import groupby
    from datetime import datetime, timedelta

    # Pre-published predictions for future match days — a feature, shown proudly.
    tomorrow_str = (datetime.strptime(today_str, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    future_pairs = [p for p in run_pairs if p["date_str"] > today_str]
    future_sections = ""
    for date_str, group_iter in groupby(sorted(future_pairs, key=lambda p: p["date_str"]), key=lambda p: p["date_str"]):
        cards = "\n".join(_match_card_html(p) for p in group_iter)
        heading = f"Tomorrow · {_fmt_date(date_str)}" if date_str == tomorrow_str else _fmt_date(date_str)
        future_sections += f"""<section>
  <h2>{heading}</h2>
  <div class="match-grid">{cards}</div>
</section>
"""

    past_pairs = sorted((p for p in run_pairs if p["date_str"] < today_str),
                        key=lambda p: p["date_str"], reverse=True)
    archive_html = ""
    for date_str, group_iter in groupby(past_pairs, key=lambda p: p["date_str"]):
        rows = ""
        for p in group_iter:
            run = p["run"]
            context = p["context"]
            decision = run["decision"]
            home = context.get("home_team") or run["match_string"].split(" vs ")[0].strip()
            away = context.get("away_team") or run["match_string"].split(" vs ")[1].strip()
            home_g = decision["home_goals"]
            away_g = decision["away_goals"]
            slug = run.get("match_slug", "")
            result_str = ""
            actual = _get_actual(run)
            if actual is not None:
                ah, aa, correct = actual
                icon = "✅" if correct else "❌"
                result_str = f'{icon} {ah}–{aa}'
            rows += f'<a class="archive-row" href="matches/{slug}.html"><span>{home} {home_g}–{away_g} {away}</span><span class="archive-result">{result_str}</span></a>\n'
        archive_html += f'<div class="day-group"><h3>{_fmt_date(date_str)}</h3>{rows}</div>\n'

    archive_section = f'<section class="archive-section"><h2>All predictions</h2>{archive_html}</section>' if archive_html else ""

    # Upcoming: start from tomorrow so it doesn't duplicate "Today" grid,
    # and exclude fixtures that already have a published prediction.
    predicted = {
        (f'{p["date_str"][:4]}-{p["date_str"][4:6]}-{p["date_str"][6:]}', p["run"].get("match_string", ""))
        for p in run_pairs
    }
    upcoming_section = _upcoming_html(schedule, tomorrow_str, exclude=predicted) if schedule else ""

    pundits_section = _pundits_html()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Football Night — WC 2026</title>
  <style>{_INDEX_CSS}{_LANDING_CSS}</style>
</head>
<body>
  <header>
    <h1>AI Football Night</h1>
    <p>Four AI pundits. One studio. Every World Cup 2026 match.</p>
  </header>
  <img class="studio-img" src="assets/studio.png" alt="AI Football Night studio">
  <a class="read-article" href="retrospective.html">📝 Read the group-stage retrospective — what a month of AI arguing actually proved</a>
  <div class="accuracy-pill">📊 {accuracy_text}</div>
  {_leaderboard_html(run_pairs)}
  {today_section}
  {future_sections}
  {archive_section}
  {upcoming_section}
  {pundits_section}
  {_sample_banter_html(collapsed=True)}
</body>
</html>"""


_MATCH_BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
a { color: #60a5fa; text-decoration: none; }
"""

_GROUP_CSS = _MATCH_BASE_CSS + """
body { background: #0f172a; color: #e2e8f0; font-family: system-ui, -apple-system, sans-serif; max-width: 760px; margin: 0 auto; padding: 16px; }
.back-link { color: #64748b; font-size: 0.85rem; display: block; margin-bottom: 16px; }
.match-header { margin-bottom: 20px; }
.match-header h1 { font-size: 1.3rem; font-weight: 700; }
.match-header .meta { color: #64748b; font-size: 0.8rem; margin-top: 4px; }
.result-banner { border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; font-size: 0.85rem; font-weight: 500; }
.result-banner.correct { background: #14532d; color: #86efac; }
.result-banner.incorrect { background: #7f1d1d; color: #fca5a5; }
.prediction-card { background: #1e293b; border-radius: 10px; padding: 14px; text-align: center; margin-bottom: 24px; }
.prediction-card .scoreline { font-size: 2rem; font-weight: 700; color: #60a5fa; }
.prediction-card .meta { color: #64748b; font-size: 0.8rem; margin-top: 4px; }
.round-header { font-size: 0.75rem; color: #475569; letter-spacing: 0.1em; text-transform: uppercase; margin: 20px 0 10px; }
.msg-card { background: #1e293b; border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #334155; }
.msg-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 700; color: white; flex-shrink: 0; }
.role-name { font-weight: 600; font-size: 0.85rem; }
.msg-body { font-size: 0.85rem; line-height: 1.55; color: #cbd5e1; }
.msg-expand { margin-top: 4px; }
.msg-expand summary { font-size: 0.75rem; color: #60a5fa; cursor: pointer; list-style: none; }
.msg-expand summary::-webkit-details-marker { display: none; }
.verdict-card { background: #0d2618; border: 1px solid #166534; border-radius: 10px; padding: 16px; margin-top: 24px; }
.verdict-card h2 { color: #4ade80; margin-bottom: 10px; }
.verdict-card .rationale { font-size: 0.9rem; line-height: 1.6; color: #d1fae5; }
.dissent { margin-top: 10px; font-size: 0.8rem; color: #6ee7b7; font-style: italic; }
"""

_CHAT_CSS = """
.chat-row { display: flex; gap: 8px; margin-bottom: 10px; align-items: flex-start; }
.chat-bubble { background: #1e293b; border-radius: 4px 14px 14px 14px; padding: 8px 12px; max-width: 85%; }
.chat-name { font-size: 0.7rem; font-weight: 700; margin-bottom: 2px; }
.chat-text { font-size: 0.9rem; line-height: 1.45; color: #e2e8f0; }
.chat-row.judge .chat-bubble { background: #0d2618; border: 1px solid #166534; }
.chat-row.right { flex-direction: row-reverse; }
.chat-row.right .chat-bubble { margin-left: auto; border-radius: 14px 4px 14px 14px; }
.full-debate > summary { font-size: 0.8rem; color: #60a5fa; cursor: pointer; padding: 10px 0; }
"""


def _role_card_html(role: str, text: str, abridge: bool = True) -> str:
    color = ROLE_COLORS.get(role, "#64748b")
    name = _display(role)
    initial = name[0]
    body = _abridge(text, role) if abridge else str(text).strip()
    return f"""<div class="msg-card" style="border-left-color:{color};">
  <div class="msg-header">
    <div class="avatar" style="background:{color};">{initial}</div>
    <span class="role-name" style="color:{color};">{name}</span>
  </div>
  <div class="msg-body">{body}</div>
</div>"""


def _chat_bubble_html(msg: dict, index: int = 0) -> str:
    role = msg.get("role", "")
    color = ROLE_COLORS.get(role, "#64748b")
    name = _display(role)
    judge_class = " judge" if role == "Judge" else ""
    side_class = " right" if index % 2 else ""
    return f"""<div class="chat-row{judge_class}{side_class}">
  <div class="avatar" style="background:{color};">{name[0]}</div>
  <div class="chat-bubble">
    <div class="chat-name" style="color:{color};">{name}</div>
    <div class="chat-text">{msg.get("text", "")}</div>
  </div>
</div>"""


def _result_banner_html(run: dict, home: str, away: str) -> str:
    actual = _get_actual(run)
    if actual is None:
        return ""
    ah, aa, correct = actual
    css_class = "correct" if correct else "incorrect"
    icon = "✅" if correct else "❌"
    return f'<div class="result-banner {css_class}">{icon} Actual: {home} {ah}–{aa} {away}</div>'


def _generate_group_page(run: dict, context: dict) -> str:
    decision = run["decision"]
    home = context.get("home_team") or run["match_string"].split(" vs ")[0].strip()
    away = context.get("away_team") or run["match_string"].split(" vs ")[1].strip()
    group = context.get("group", "")
    match_date = context.get("match_date", "")
    home_g = decision["home_goals"]
    away_g = decision["away_goals"]
    confidence = int(decision.get("confidence", 0) * 100)
    upset = int(decision.get("upset_probability", 0) * 100)
    quote = decision.get("best_debate_quote") or decision.get("studio_banter_quote") or {}
    key_factors = decision.get("key_factors", [])
    dissenting = decision.get("dissenting_views", [])
    rationale = decision.get("rationale", "")

    debate = run.get("full_debate", {})
    proposals = debate.get("proposals", {})
    critiques = debate.get("cross_critiques", {})
    rebuttals = debate.get("rebuttals", {})

    result_banner = _result_banner_html(run, home, away)

    rounds_html = ""
    for round_label, round_data in [
        ("Round 1 — Initial Positions", proposals),
        ("Round 2 — Cross-Critiques", critiques),
        ("Round 3 — Rebuttals", rebuttals),
    ]:
        if round_data:
            cards = "\n".join(_role_card_html(role, text) for role, text in round_data.items())
            rounds_html += f'<div class="round-header">{round_label}</div>\n{cards}\n'

    dissent_html = "".join(f"<li>{v}</li>" for v in dissenting)
    dissent_section = f'<div class="dissent"><strong>Dissenting:</strong><ul>{dissent_html}</ul></div>' if dissenting else ""

    quote_html = f'<div class="round-header">The Sharpest Exchange</div>\n{_role_card_html(quote.get("role","Council"), quote.get("exchange", quote.get("quote","")), abridge=False)}\n' if quote else ""

    group_chat = run.get("group_chat") or []
    if group_chat:
        bubbles = "\n".join(_chat_bubble_html(m, i) for i, m in enumerate(group_chat))
        debate_section = f"""<div class="round-header">The Studio Group Chat</div>
{bubbles}
<details class="full-debate"><summary>Full debate transcript →</summary>
{rounds_html}
</details>"""
        extra_css = f"<style>{_CHAT_CSS}</style>"
    else:
        debate_section = rounds_html
        extra_css = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{home} vs {away} — AI Football Night</title>
  <style>{_GROUP_CSS}</style>
  {extra_css}
</head>
<body>
  <a class="back-link" href="../index.html">← All predictions</a>
  <div class="match-header">
    <h1>{home} vs {away}</h1>
    <div class="meta">Group {group} · {match_date}</div>
  </div>
  {result_banner}
  <div class="prediction-card">
    <div class="scoreline">{home_g}–{away_g}</div>
    <div class="meta">{confidence}% confidence · {upset}% upset probability</div>
  </div>
  {quote_html}
  {debate_section}
  <div class="verdict-card">
    <h2>⚖️ The Verdict</h2>
    <div class="rationale">{rationale}</div>
    {dissent_section}
  </div>
</body>
</html>"""


_KNOCKOUT_CSS = _MATCH_BASE_CSS + """
body { background: #fffbf0; color: #1a1a1a; font-family: Georgia, 'Times New Roman', serif; max-width: 760px; margin: 0 auto; padding: 16px; line-height: 1.6; }
.back-link { color: #888; font-size: 0.8rem; display: block; margin-bottom: 16px; font-family: system-ui, sans-serif; }
.masthead { text-align: center; border-bottom: 3px double #1a1a1a; padding-bottom: 12px; margin-bottom: 20px; }
.masthead .pub-name { font-size: 0.75rem; letter-spacing: 0.2em; text-transform: uppercase; color: #666; }
.masthead h1 { font-size: 1.6rem; font-weight: 700; margin: 6px 0 4px; }
.masthead .byline { font-size: 0.8rem; color: #666; font-style: italic; }
.result-banner { padding: 10px 14px; margin-bottom: 16px; font-size: 0.85rem; font-weight: 500; border-radius: 4px; font-family: system-ui, sans-serif; }
.result-banner.correct { background: #dcfce7; color: #166534; border-left: 4px solid #16a34a; }
.result-banner.incorrect { background: #fee2e2; color: #991b1b; border-left: 4px solid #dc2626; }
.pull-quote { border-left: 4px solid #c0392b; padding: 10px 16px; margin: 20px 0; font-style: italic; font-size: 1rem; color: #333; background: #fef9f0; }
.pull-quote cite { display: block; margin-top: 6px; font-style: normal; font-size: 0.8rem; color: #888; font-family: system-ui, sans-serif; }
.stat-row { display: flex; gap: 24px; margin: 16px 0; font-family: system-ui, sans-serif; }
.stat-item { text-align: center; }
.stat-value { font-size: 1.4rem; font-weight: 700; }
.stat-label { font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }
h2 { font-size: 1rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin: 20px 0 10px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
.key-factors { margin: 0 0 16px 20px; }
.key-factors li { margin-bottom: 6px; font-size: 0.9rem; }
.dissent-list { margin: 0 0 16px 20px; font-style: italic; font-size: 0.85rem; color: #555; }
details { border: 1px solid #ddd; border-radius: 4px; margin-bottom: 8px; }
summary { padding: 10px 14px; cursor: pointer; font-size: 0.85rem; font-weight: 600; font-family: system-ui, sans-serif; color: #444; }
details[open] summary { border-bottom: 1px solid #ddd; }
.debate-round { padding: 12px 14px; font-size: 0.85rem; }
.debate-role { font-weight: 700; margin-top: 10px; margin-bottom: 3px; }
.rationale-block { font-size: 0.95rem; color: #333; margin: 8px 0; }
"""


def _generate_knockout_page(run: dict, context: dict) -> str:
    decision = run["decision"]
    home = context.get("home_team") or run["match_string"].split(" vs ")[0].strip()
    away = context.get("away_team") or run["match_string"].split(" vs ")[1].strip()
    group = context.get("group", "")
    match_date = context.get("match_date", "")
    home_g = decision["home_goals"]
    away_g = decision["away_goals"]
    confidence = int(decision.get("confidence", 0) * 100)
    upset = int(decision.get("upset_probability", 0) * 100)
    quote = decision.get("best_debate_quote") or decision.get("studio_banter_quote") or {}
    key_factors = decision.get("key_factors", [])
    dissenting = decision.get("dissenting_views", [])
    rationale = decision.get("rationale", "")

    debate = run.get("full_debate", {})
    proposals = debate.get("proposals", {})
    critiques = debate.get("cross_critiques", {})
    rebuttals = debate.get("rebuttals", {})

    result_banner = _result_banner_html(run, home, away)

    pull_quote_html = ""
    if quote:
        pull_quote_html = f"""<blockquote class="pull-quote">
  "{quote.get('exchange') or quote.get('quote', '')}"
  <cite>— {_display(quote.get('role', 'Council'))}</cite>
</blockquote>"""

    factors_html = "".join(f"<li>{f}</li>" for f in key_factors)
    dissent_html = "".join(f"<li>{v}</li>" for v in dissenting)
    dissent_section = f'<h2>Dissenting Views</h2><ul class="dissent-list">{dissent_html}</ul>' if dissenting else ""

    def debate_round_html(label: str, round_data: dict) -> str:
        if not round_data:
            return ""
        inner = "".join(f'<div class="debate-role">{_display(role)}</div><p>{_abridge(text, role)}</p>' for role, text in round_data.items())
        return f"<details><summary>{label}</summary><div class='debate-round'>{inner}</div></details>"

    rounds_html = (
        debate_round_html("Round 1 — Initial Positions", proposals)
        + debate_round_html("Round 2 — Cross-Critiques", critiques)
        + debate_round_html("Round 3 — Rebuttals", rebuttals)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{home} vs {away} — AI Football Night</title>
  <style>{_KNOCKOUT_CSS}</style>
</head>
<body>
  <a class="back-link" href="../index.html">← All predictions</a>
  <div class="masthead">
    <div class="pub-name">AI Football Night</div>
    <h1>{home} {home_g}–{away_g} {away}</h1>
    <div class="byline">{group} · {match_date} · {confidence}% confidence</div>
  </div>
  {result_banner}
  {pull_quote_html}
  <div class="stat-row">
    <div class="stat-item"><div class="stat-value">{home_g}–{away_g}</div><div class="stat-label">Prediction</div></div>
    <div class="stat-item"><div class="stat-value">{confidence}%</div><div class="stat-label">Confidence</div></div>
    <div class="stat-item"><div class="stat-value">{upset}%</div><div class="stat-label">Upset chance</div></div>
  </div>
  <h2>What the Council Saw</h2>
  <ol class="key-factors">{factors_html}</ol>
  {dissent_section}
  <h2>Judge's Rationale</h2>
  <p class="rationale-block">{rationale}</p>
  <h2>Full Debate</h2>
  {rounds_html}
</body>
</html>"""


def generate_match_html(run: dict, context: dict) -> str:
    if is_knockout_match(context):
        return _generate_knockout_page(run, context)
    return _generate_group_page(run, context)


def _md_inline(text: str) -> str:
    """Inline markdown → HTML: escape, then bold, italic, code. Bold before italic."""
    import html
    import re
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def md_to_html(md_text: str) -> str:
    """Minimal, dependency-free Markdown → HTML for our article subset:
    h1/h2, bullet lists, --- rules, **bold**/*italic*/`code`, paragraphs."""
    lines = md_text.replace("\r\n", "\n").split("\n")
    out, para, in_list = [], [], False

    def flush_para():
        if para:
            out.append(f"<p>{_md_inline(' '.join(para))}</p>")
            para.clear()

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_para(); close_list(); continue
        if stripped == "---":
            flush_para(); close_list(); out.append("<hr>"); continue
        if stripped.startswith("## "):
            flush_para(); close_list(); out.append(f"<h2>{_md_inline(stripped[3:])}</h2>"); continue
        if stripped.startswith("# "):
            flush_para(); close_list(); out.append(f"<h1>{_md_inline(stripped[2:])}</h1>"); continue
        if stripped.startswith("- "):
            flush_para()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{_md_inline(stripped[2:])}</li>"); continue
        if in_list:
            # continuation of the previous list item (wrapped line)
            out[-1] = out[-1][:-5] + " " + _md_inline(stripped) + "</li>"
            continue
        para.append(stripped)
    flush_para(); close_list()
    return "\n".join(out)


def render_article_html(md_path: Path) -> str:
    """Full standalone HTML page for a Markdown article (the retrospective)."""
    body = md_to_html(Path(md_path).read_text(encoding="utf-8"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>The Retrospective — AI Football Night</title>
  <style>{_INDEX_CSS}{_ARTICLE_CSS}</style>
</head>
<body>
  <article class="article">
    <a class="back-link" href="index.html">← AI Football Night</a>
    {body}
  </article>
</body>
</html>"""


def build_site(output_dir: Path, runs_dir: Path = RUNS_DIR) -> None:
    from datetime import datetime, timezone
    output_dir.mkdir(parents=True, exist_ok=True)
    matches_dir = output_dir / "matches"
    matches_dir.mkdir(exist_ok=True)

    run_pairs = load_run_pairs(runs_dir)
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    sched_path = runs_dir.parent / "schedule.json"
    if not sched_path.exists():
        sched_path = Path("schedule.json")
    schedule = json.loads(sched_path.read_text()) if sched_path.exists() else []

    # Copy static assets (images etc.) if present
    import shutil
    for assets_src in [runs_dir.parent / "assets", Path("assets")]:
        if assets_src.exists():
            shutil.copytree(assets_src, output_dir / "assets", dirs_exist_ok=True)
            break

    index_html = generate_index_html(run_pairs, today_str, schedule=schedule)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    # Publish committed long-form articles (content/*.md) as standalone pages.
    for article_src, out_name in [
        (runs_dir.parent / "content" / "group-stage-retrospective.md", "retrospective.html"),
        (Path("content") / "group-stage-retrospective.md", "retrospective.html"),
    ]:
        if article_src.exists():
            (output_dir / out_name).write_text(render_article_html(article_src), encoding="utf-8")
            print(f"Article published: {output_dir / out_name}")
            break

    pages_written = 0
    for pair in run_pairs:
        run = pair["run"]
        slug = run.get("match_slug")
        if not slug:
            continue
        match_html = generate_match_html(run, pair["context"])
        (matches_dir / f"{slug}.html").write_text(match_html, encoding="utf-8")
        pages_written += 1

    print(f"Site built: {output_dir} ({pages_written} match pages)")


def main():
    parser = argparse.ArgumentParser(description="Build gh-pages site from runs/")
    parser.add_argument("--output-dir", default="_site", help="Output directory (default: _site)")
    parser.add_argument("--runs-dir", default="runs", help="Runs directory (default: runs)")
    args = parser.parse_args()
    build_site(Path(args.output_dir), runs_dir=Path(args.runs_dir))


if __name__ == "__main__":
    main()
