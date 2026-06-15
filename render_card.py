#!/usr/bin/env python3
"""
Render the daily share cards: run JSON -> HTML -> PNG.

Two card types, both deterministic (no generative step):
  • Picks card  — 1080x1350 (4:5 mobile) per match: the 4-way pick divergence,
    the lone outlier flagged, the judge's verdict. Output: <stem>_card.png
  • Sack race   — 1080x1350 once per day: season standings + the sack zone.
    Output: runs/<date>/sack_race.png

Character identity is a designed vector crest per bot (no portraits, no emoji) so
the look is identical every render. Team flags come from flagcdn (remote); a
missing flag degrades to no-flag, never an error. The screenshot (Playwright) is
isolated in screenshot_card(); HTML building is pure. CI calls main() with
continue-on-error — a render failure must never block the daily run (the post
pack ships text-only).

Usage:
  python render_card.py runs/2026-06-13/wc_brazil-morocco.json
  python render_card.py --date 2026-06-13     # all matches that day + sack race
"""
import argparse
import json
import re
import sys
from collections import Counter
from html import escape
from pathlib import Path

import teams

ROLES = ("Stat_Bot", "G_Bot", "R_Bot", "K_Bot")

CHARS = {
    "Stat_Bot": {"name": "STAT_BOT", "tag": "THE DATA",      "color": "#3b82f6", "mono": "S", "shape": "shield"},
    "G_Bot":    {"name": "G_BOT",    "tag": "THE TACTICIAN",  "color": "#10b981", "mono": "G", "shape": "hex"},
    "R_Bot":    {"name": "R_BOT",    "tag": "THE CONTRARIAN", "color": "#f59e0b", "mono": "R", "shape": "roundel"},
    "K_Bot":    {"name": "K_BOT",    "tag": "THE VERDICT",    "color": "#a855f7", "mono": "K", "shape": "diamond"},
}

# FIFA canonical name -> flagcdn ISO code (home nations use gb-* subdivisions).
FLAG = {
    "Argentina": "ar", "Australia": "au", "Austria": "at", "Belgium": "be",
    "Bosnia and Herzegovina": "ba", "Brazil": "br", "Cabo Verde": "cv", "Cameroon": "cm",
    "Canada": "ca", "Chile": "cl", "Colombia": "co", "Costa Rica": "cr",
    "Côte d'Ivoire": "ci", "Croatia": "hr", "Curaçao": "cw", "Czechia": "cz", "Denmark": "dk",
    "Ecuador": "ec", "Egypt": "eg", "England": "gb-eng", "France": "fr",
    "Germany": "de", "Ghana": "gh", "Haiti": "ht", "Honduras": "hn",
    "Iran": "ir", "Italy": "it", "Jamaica": "jm", "Japan": "jp", "Jordan": "jo",
    "Korea Republic": "kr", "Mexico": "mx", "Morocco": "ma", "Netherlands": "nl",
    "New Zealand": "nz", "Nigeria": "ng", "Norway": "no", "Panama": "pa",
    "Paraguay": "py", "Peru": "pe", "Poland": "pl", "Portugal": "pt", "Qatar": "qa",
    "Saudi Arabia": "sa", "Scotland": "gb-sct", "Senegal": "sn", "Serbia": "rs",
    "South Africa": "za", "Spain": "es", "Sweden": "se", "Switzerland": "ch",
    "Tunisia": "tn", "Türkiye": "tr", "Ukraine": "ua", "United States": "us",
    "Uruguay": "uy", "Uzbekistan": "uz", "Wales": "gb-wls",
}
ABBR = {
    "Australia": "AUS", "Brazil": "BRA", "Bosnia and Herzegovina": "BIH",
    "Canada": "CAN", "Croatia": "CRO", "Czechia": "CZE", "Haiti": "HAI",
    "Korea Republic": "KOR", "Mexico": "MEX", "Morocco": "MAR", "Paraguay": "PAR",
    "Qatar": "QAT", "Scotland": "SCO", "South Africa": "RSA", "Switzerland": "SUI",
    "Türkiye": "TUR", "United States": "USA",
}


def abbr(name: str) -> str:
    return ABBR.get(name) or re.sub(r"[^A-Za-z]", "", name)[:3].upper()


def flag_code(name: str) -> str:
    """flagcdn code via the canonical FIFA name; '' if unknown (degrades to no flag)."""
    return FLAG.get(teams.canonical(name), FLAG.get(name, ""))


# ----- character crest (designed vector badge; deterministic, no emoji) -----

_CREST_PATH = {
    "shield":  "M32 3 L58 13 V34 C58 50 46 58 32 62 C18 58 6 50 6 34 V13 Z",
    "hex":     "M32 3 L57 17 V47 L32 61 L7 47 V17 Z",
    "diamond": "M32 2 L62 32 L32 62 L2 32 Z",
}


def crest(role: str, size: int = 58) -> str:
    c = CHARS[role]
    col = c["color"]
    gid = f"g{role}{size}"
    if c["shape"] == "roundel":
        body = f'<circle cx="32" cy="32" r="29" fill="url(#{gid})" stroke="{col}" stroke-width="2.5"/>'
    else:
        body = (f'<path d="{_CREST_PATH[c["shape"]]}" fill="url(#{gid})" stroke="{col}" '
                f'stroke-width="2.5" stroke-linejoin="round"/>')
    return (f'<svg class="crest" width="{size}" height="{size}" viewBox="0 0 64 64">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{col}" stop-opacity="0.45"/>'
            f'<stop offset="1" stop-color="{col}" stop-opacity="0.08"/></linearGradient></defs>{body}'
            f'<text x="32" y="33" text-anchor="middle" dominant-baseline="central" '
            f'font-family="Inter,sans-serif" font-size="28" font-weight="900" fill="#f8fafc">{c["mono"]}</text></svg>')


# ----- pure helpers -----

_THROAT = ("right", "look", "ok", "okay", "listen", "see", "well", "so", "honestly", "now")


def _teams(run: dict) -> tuple:
    match_string = run.get("match_string", "Home vs Away")
    if " vs " in match_string:
        home, away = [t.strip() for t in match_string.split(" vs ", 1)]
    else:
        home, away = "Home", "Away"
    return home, away


def first_take(text, n=150):
    """First *substantive* sentence: skip markdown, throat-clearing, and lines that
    just address another pundit. Prefer one carrying a number."""
    raw = re.sub(r"[*_`#>]+", "", str(text or ""))
    raw = re.sub(r"^\s*\d+[\.\)]\s*", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    sents = [s for s in re.split(r"(?<=[.!?:])\s", raw) if len(s) > 16]

    def ok(s):
        first = re.sub(r"[^a-z]", "", s.split()[0].lower()) if s.split() else ""
        if first in _THROAT:
            return False
        if re.match(r"^(Stat_Bot|G_Bot|R_Bot|K_Bot)[,\s]", s):
            return False
        if s.endswith(":") or re.search(r"(BATTLE|DILEMMA|#\d)\s*$", s):
            return False
        return True

    cand = (next((s for s in sents if ok(s) and re.search(r"\d", s)), None)
            or next((s for s in sents if ok(s)), None) or (sents[0] if sents else ""))
    return (cand[:n].rsplit(" ", 1)[0] + "…") if len(cand) > n else cand


def chip_for(text, fallback=""):
    """A short key-stat chip pulled from the pundit's own argument (real, not invented)."""
    t = str(text or "")
    for pat, fmt in [(r"\b\d-\d-\d(?:-\d)?\b", None), (r"Elo[^\d]*(\d{3,4})", "Elo {}"),
                     (r"by (\d{2,3}) points", "+{} Elo pts"), (r"missing ([A-Z][a-z]+)", "missing {}")]:
        m = re.search(pat, t)
        if m:
            return m.group(0) if fmt is None else fmt.format(m.group(1))
    return fallback


def lean(hg, ag):
    return "H" if hg > ag else ("A" if ag > hg else "D")


# ----- picks card (4:5 mobile, 2x2 grid) -----

def _pick_card_html(role, hg, ag, take, chip, *, home, away, judge=False, outlier=False, conf=None):
    c = CHARS[role]
    klass = "card judge" if judge else ("card outlier" if outlier else "card")
    flag = ('<div class="flag verdict">FINAL VERDICT</div>' if judge
            else '<div class="flag upset">THE OUTLIER</div>' if outlier else "")
    try:  # scores are normally ints, but decision may be "?" if missing
        lv = lean(int(hg), int(ag))
    except (TypeError, ValueError):
        lv = None
    lt = {"H": f"WIN {abbr(home)}", "A": f"WIN {abbr(away)}", "D": "DRAW"}.get(lv, "")
    lcls = {"H": "win", "A": "upset", "D": "draw"}.get(lv, "draw")
    lean_html = f'<div class="lean {lcls}">{escape(lt)}</div>' if lt else ""
    conf_html = ""
    if conf is not None:  # honest: only the judge has a real confidence value
        pips = "".join(f'<span class="pip {"on" if i < conf else ""}"></span>' for i in range(5))
        conf_html = (f'<div class="conf-wrap"><span class="conf-label">JUDGE CONFIDENCE</span>'
                     f'<div class="conf">{pips}</div></div>')
    return f"""
    <div class="{klass}">{flag}
      <div class="chead">{crest(role)}<div>
        <div class="cname" style="color:{c['color']};">{escape(c['name'])}</div>
        <div class="ctag">{escape(c['tag'])}</div></div></div>
      <div class="pickrow"><div class="pick">{escape(str(hg))}<span class="dash">–</span>{escape(str(ag))}</div>
        {lean_html}</div>
      <div class="chip">{escape(chip)}</div>
      <div class="take">“{escape(take)}”</div>
      {conf_html}
    </div>"""


def build_pick_cards(run: dict) -> tuple:
    """The 4 pick-card HTML blocks + (home, away, headline). Pure."""
    home, away = _teams(run)
    preds = run.get("pundit_predictions") or {}
    dec = run.get("decision", {})
    props = run.get("full_debate", {}).get("proposals", {})
    headline = dec.get("match_headline", "")

    pl = {r: lean(preds[r]["home_goals"], preds[r]["away_goals"]) for r in preds}
    cnt = Counter(pl.values())
    minority = [r for r, v in pl.items() if cnt[v] == 1] if len(cnt) > 1 else []

    chip_fb = {"Stat_Bot": "hard numbers", "G_Bot": "tactical edge", "R_Bot": "the eye test"}
    cards = ""
    for role in ("Stat_Bot", "G_Bot", "R_Bot"):
        p = preds.get(role)
        if not p:
            continue
        cards += _pick_card_html(role, p["home_goals"], p["away_goals"], first_take(props.get(role)),
                                 chip_for(props.get(role), chip_fb[role]), home=home, away=away,
                                 outlier=(role in minority))
    cards += _pick_card_html("K_Bot", dec.get("home_goals", "?"), dec.get("away_goals", "?"),
                             first_take(dec.get("tweet_hook") or dec.get("match_headline")),
                             f'{int(dec.get("confidence", 0) * 100)}% confident', home=home, away=away,
                             judge=True, conf=round(dec.get("confidence", 0.5) * 5))
    return cards, home, away, headline


_HEAD = """<style>
 * { margin:0; box-sizing:border-box; }
 body { width:1080px; height:1350px; font-family:'Inter',system-ui,-apple-system,sans-serif;
   background:radial-gradient(120% 90% at 50% -10%, #1d2a4d 0%, #0b1120 58%, #060a13 100%);
   color:#f1f5f9; display:flex; flex-direction:column; overflow:hidden; position:relative; }
 body::before { content:""; position:absolute; inset:0;
   background:repeating-linear-gradient(90deg, rgba(148,163,184,0.035) 0 2px, transparent 2px 150px); }
 .top { display:flex; justify-content:space-between; align-items:center; padding:30px 50px 0; z-index:1; }
 .brand { font-size:20px; font-weight:800; letter-spacing:5px; color:#e2e8f0; }
 .brand .dot { color:#22d3ee; }
 .roundel { font-size:16px; font-weight:900; letter-spacing:1px; color:#0b1120;
   background:linear-gradient(135deg,#fde68a,#f59e0b); padding:6px 16px; border-radius:99px; }
 .meta { font-size:15px; letter-spacing:1.5px; color:#94a3b8; font-weight:600; text-align:right; }
 .crest { flex-shrink:0; }
 .strip { display:flex; justify-content:center; padding:22px 50px; border-top:1px solid rgba(148,163,184,0.16);
   background:rgba(6,10,19,0.7); z-index:1; }
 .handle { font-size:16px; color:#64748b; letter-spacing:2px; font-weight:700; }
</style>"""


def build_picks_card(run: dict) -> str:
    """4:5 mobile picks card (1080x1350): 2x2 grid of the panel's calls."""
    cards, home, away, headline = build_pick_cards(run)
    fimg = lambda t: (f'<img class="cflag" src="https://flagcdn.com/h120/{flag_code(t)}.png">' if flag_code(t) else "")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{_HEAD}<style>
 .matchup {{ display:flex; align-items:center; justify-content:center; gap:30px; padding:34px 50px 0; z-index:1; }}
 .cflag {{ height:82px; border-radius:8px; box-shadow:0 8px 22px -6px rgba(0,0,0,0.7); }}
 .teams {{ font-size:56px; font-weight:900; line-height:1.05; text-align:center; }}
 .teams .vs {{ color:#475569; font-size:30px; font-weight:700; display:block; margin:4px 0; }}
 .subline {{ text-align:center; font-size:18px; color:#cbd5e1; margin-top:18px; padding:0 60px; z-index:1;
   font-weight:600; line-height:1.4; }}
 .deck {{ flex:1; display:grid; grid-template-columns:1fr 1fr; gap:24px; padding:34px 50px 20px; z-index:1; }}
 .card {{ background:rgba(20,29,48,0.72); border:1px solid rgba(148,163,184,0.16); border-radius:22px;
   padding:26px 24px 24px; display:flex; flex-direction:column; gap:16px; position:relative; }}
 .card.judge {{ background:rgba(38,26,58,0.6); border-color:rgba(168,85,247,0.5);
   box-shadow:0 0 0 1px rgba(168,85,247,0.22), 0 18px 40px -16px rgba(168,85,247,0.55); }}
 .card.outlier {{ border-color:rgba(245,158,11,0.5); }}
 .flag {{ position:absolute; top:-14px; left:50%; transform:translateX(-50%); font-size:13px; font-weight:800;
   letter-spacing:1.5px; padding:6px 15px; border-radius:99px; white-space:nowrap; }}
 .flag.verdict {{ background:#a855f7; color:#fff; }}
 .flag.upset {{ background:#f59e0b; color:#1a1206; }}
 .chead {{ display:flex; align-items:center; gap:14px; }}
 .cname {{ font-size:22px; font-weight:800; }}
 .ctag {{ font-size:13px; font-weight:700; letter-spacing:1.5px; color:#64748b; margin-top:3px; }}
 .pickrow {{ display:flex; align-items:center; justify-content:space-between;
   border-top:1px solid rgba(148,163,184,0.12); border-bottom:1px solid rgba(148,163,184,0.12); padding:14px 2px; }}
 .pick {{ font-size:62px; font-weight:900; line-height:1; }}
 .pick .dash {{ color:#475569; margin:0 3px; }}
 .lean {{ font-size:15px; font-weight:800; letter-spacing:1px; padding:8px 13px; border-radius:9px; }}
 .lean.win {{ background:rgba(34,211,238,0.15); color:#67e8f9; }}
 .lean.upset {{ background:rgba(245,158,11,0.18); color:#fbbf24; }}
 .lean.draw {{ background:rgba(148,163,184,0.18); color:#cbd5e1; }}
 .chip {{ align-self:flex-start; font-size:15px; font-weight:700; color:#cbd5e1;
   background:rgba(148,163,184,0.12); border:1px solid rgba(148,163,184,0.18); padding:6px 14px; border-radius:99px; }}
 .take {{ font-size:18px; line-height:1.55; color:#e2e8f0; font-style:italic; flex:1; }}
 .conf-wrap {{ margin-top:auto; }}
 .conf-label {{ font-size:12px; font-weight:800; letter-spacing:1.5px; color:#64748b; }}
 .conf {{ display:flex; gap:6px; margin-top:8px; }}
 .pip {{ width:100%; height:7px; border-radius:3px; background:rgba(148,163,184,0.18); }}
 .card.judge .pip.on {{ background:#c084fc; }}
</style></head><body>
 <div class="top"><div class="brand">AI FOOTBALL NIGHT <span class="dot">●</span></div>
   <div class="roundel">\U0001F3C6 WC26</div><div class="meta">WORLD CUP 2026</div></div>
 <div class="matchup">{fimg(home)}<div class="teams">{escape(home.upper())}<span class="vs">vs</span>{escape(away.upper())}</div>{fimg(away)}</div>
 <div class="subline">{escape(headline)}</div>
 <div class="deck">{cards}</div>
 <div class="strip"><span class="handle">AI FOOTBALL NIGHT · @AIFootballNight</span></div>
</body></html>"""


# ----- sack race card (4:5 mobile, season standings) -----

def build_sack_race_card(records: dict) -> str:
    """4:5 mobile standings card (1080x1350): the season race + the sack zone."""
    standings = sorted(records.items(), key=lambda kv: (-kv[1]["correct_result"], -kv[1]["correct_scoreline"]))
    n_played = max((rec["matches"] for rec in records.values()), default=0)
    rows = ""
    for i, (role, rec) in enumerate(standings):
        c = CHARS.get(role, {"color": "#94a3b8", "tag": ""})
        sack = (i == len(standings) - 1)
        played, results, exact = rec["matches"], rec["correct_result"], rec["correct_scoreline"]
        acc = round(100 * results / played) if played else 0
        last = rec.get("last") or {}
        last_html = ""
        if last:
            hit = last.get("correct_result")
            last_html = (f'<span class="res {"ok" if hit else "no"}">{"✓" if hit else "✗"}</span>'
                         f'<span class="lastpred">{escape(last.get("predicted","–"))} / {escape(last.get("actual","–"))}</span>')
        crown = ' <span class="crown">\U0001F451</span>' if i == 0 else ""
        sb = '<div class="sackflag">⚠ SACK ZONE</div>' if sack else ""
        rows += f"""<div class="trow{' sack' if sack else ''}"><div class="rank">{i+1}</div>
          <div class="who">{crest(role,52)}<div><div class="wn" style="color:{c['color']};">{escape(role)}{crown}</div>
          <div class="wt">{escape(c.get('tag',''))}</div></div></div>
          <div class="rstats"><div class="rmain">{results}<span class="den">/{played}</span> <span class="rlbl">results</span></div>
          <div class="rsub">{exact} exact · {acc}% · {last_html}</div></div>{sb}</div>"""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{_HEAD}<style>
 .title {{ text-align:center; padding:40px 50px 6px; z-index:1; }}
 .title h1 {{ font-size:72px; font-weight:900; letter-spacing:3px;
   background:linear-gradient(90deg,#f87171,#fbbf24); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
 .title .sub {{ font-size:17px; color:#94a3b8; letter-spacing:2px; margin-top:12px; font-weight:600; }}
 .table {{ flex:1; display:flex; flex-direction:column; gap:26px; padding:40px 50px; z-index:1; justify-content:center; }}
 .trow {{ display:flex; align-items:center; gap:22px; background:rgba(20,29,48,0.72);
   border:1px solid rgba(148,163,184,0.16); border-radius:20px; padding:30px 28px; position:relative; }}
 .trow.sack {{ border-color:rgba(248,113,113,0.55); background:rgba(48,20,24,0.55); box-shadow:0 0 0 1px rgba(248,113,113,0.25); }}
 .rank {{ font-size:46px; font-weight:900; color:#475569; width:50px; text-align:center; }}
 .trow.sack .rank {{ color:#f87171; }}
 .who {{ display:flex; align-items:center; gap:18px; flex:1; }}
 .wn {{ font-size:30px; font-weight:800; }}
 .wt {{ font-size:14px; font-weight:700; letter-spacing:1.5px; color:#64748b; margin-top:3px; }}
 .crown {{ font-size:22px; }}
 .rstats {{ text-align:right; }}
 .rmain {{ font-size:40px; font-weight:900; color:#e2e8f0; }}
 .rmain .den {{ font-size:24px; color:#64748b; }}
 .rmain .rlbl {{ font-size:15px; color:#64748b; font-weight:700; letter-spacing:1px; }}
 .rsub {{ font-size:16px; color:#94a3b8; font-weight:600; margin-top:6px; }}
 .res {{ font-weight:900; }} .res.ok {{ color:#34d399; }} .res.no {{ color:#f87171; }}
 .lastpred {{ color:#94a3b8; }}
 .sackflag {{ position:absolute; right:24px; top:-14px; font-size:13px; font-weight:800; letter-spacing:1.5px;
   background:#ef4444; color:#fff; padding:6px 15px; border-radius:99px; }}
</style></head><body>
 <div class="top"><div class="brand">AI FOOTBALL NIGHT <span class="dot">●</span></div>
   <div class="roundel">\U0001F3C6 WC26</div><div class="meta">SEASON STANDINGS</div></div>
 <div class="title"><h1>THE SACK RACE</h1>
   <div class="sub">WORLD CUP 2026 · AFTER {n_played} MATCHES · LAST PUNDIT GETS SACKED</div></div>
 <div class="table">{rows}</div>
 <div class="strip"><span class="handle">@AIFootballNight · #WorldCup26</span></div>
</body></html>"""


def screenshot_card(html: str, out_path: Path, width: int = 1080, height: int = 1350) -> bool:
    """HTML string -> PNG at width×height. Returns False (never raises) on failure."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  playwright not installed — skipping card render (text-only day)")
        return False
    try:
        html_path = out_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(html_path.resolve().as_uri())
            page.wait_for_timeout(900)  # let remote flags load
            page.screenshot(path=str(out_path))
            browser.close()
        html_path.unlink(missing_ok=True)
        print(f"  Card: {out_path}")
        return True
    except Exception as e:
        print(f"  ⚠️  Card render failed ({e}) — text-only day, run not blocked")
        return False


def render_for_run(run_path: Path) -> bool:
    run = json.loads(Path(run_path).read_text())
    html = build_picks_card(run)
    out_path = Path(run_path).parent / f"{Path(run_path).stem}_card.png"
    return screenshot_card(html, out_path)


def render_sack_race(date_dir: Path, runs_root: Path) -> bool:
    from track_record import build_track_records
    records = build_track_records(runs_root)
    if not records:
        print("  No track records yet — skipping sack race card")
        return False
    return screenshot_card(build_sack_race_card(records), date_dir / "sack_race.png")


def main():
    parser = argparse.ArgumentParser(description="Render share card PNG(s) from run JSON")
    parser.add_argument("run_file", nargs="?", help="Path to a wc_*.json run file")
    parser.add_argument("--date", help="Render all successful matches from that day's summary + sack race (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.date:
        date_dir = Path("runs") / args.date
        summary_path = date_dir / "daily_summary.json"
        if not summary_path.exists():
            print(f"No summary for {args.date}: {summary_path}")
            sys.exit(0)
        summary = json.loads(summary_path.read_text())
        ok = 0
        for match in summary.get("matches", []):
            if match.get("success") and Path(match["run_file"]).exists():
                ok += render_for_run(Path(match["run_file"]))
        render_sack_race(date_dir, date_dir.parent)
        print(f"Rendered {ok} picks card(s) + sack race")
    elif args.run_file:
        success = render_for_run(Path(args.run_file))
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
