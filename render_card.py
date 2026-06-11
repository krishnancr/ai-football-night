#!/usr/bin/env python3
"""
Render the daily 1200x675 share card: run JSON -> HTML -> PNG.

Deterministic by design — no generative step. Avatars are committed portraits
(assets/avatars/<Role>.png) embedded as base64; colored-initial circles until
they exist. The screenshot (Playwright) is isolated in screenshot_card(); HTML
building is pure. CI calls main() with continue-on-error — a render failure
must never block the daily run (the post pack ships text-only).

Usage:
  python render_card.py runs/wc_brazil-croatia_20260613.json
  python render_card.py --date 2026-06-13     # all matches in that day's summary
"""
import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROLES = ("Stat_Bot", "G_Bot", "R_Bot", "K_Bot")
ROLE_COLORS = {"Stat_Bot": "#3b82f6", "G_Bot": "#10b981", "R_Bot": "#f59e0b", "K_Bot": "#a855f7"}
AVATAR_DIR = Path("assets/avatars")
CARD_MSG_LIMIT = 140  # max chars per chat bubble before truncation


def _teams(run: dict) -> tuple:
    match_string = run.get("match_string", "Home vs Away")
    if " vs " in match_string:
        home, away = [t.strip() for t in match_string.split(" vs ", 1)]
    else:
        home, away = "Home", "Away"
    return home, away


def select_bubbles(chat: list, banter_exchange: str, n: int = 4) -> list:
    """Deterministic: window of n messages around the studio banter quote;
    fallback: first window where someone names another pundit; else first n."""
    if not chat:
        return []
    idx = None
    exchange = banter_exchange or ""
    for i, msg in enumerate(chat):
        head = msg["text"][:30]
        if head and head in exchange:
            idx = i
            break
    if idx is None:
        for i, msg in enumerate(chat):
            if any(role in msg["text"] for role in ROLES if role != msg["role"]):
                idx = i
                break
    if idx is None:
        idx = 0
    start = max(0, min(idx, len(chat) - n))
    return chat[start:start + n]


def _avatar_html(role: str) -> str:
    color = ROLE_COLORS.get(role, "#64748b")
    portrait = AVATAR_DIR / f"{role}.png"
    if portrait.exists():
        b64 = base64.b64encode(portrait.read_bytes()).decode()
        return (f'<img class="avatar" src="data:image/png;base64,{b64}" '
                f'style="border:2px solid {color};" alt="{escape(role)}">')
    return (f'<div class="avatar" style="background:{color};">{escape(role[0])}</div>')


def _leaderboard_html(records: dict) -> str:
    if not records:
        return '<span class="lb-empty">📊 Records start after Matchday 1</span>'
    standings = sorted(records.items(),
                       key=lambda kv: (-kv[1]["correct_result"], -kv[1]["correct_scoreline"]))
    parts = ['<span class="lb-label">📊 PANEL FORM:</span>']
    for i, (role, rec) in enumerate(standings):
        score = f"{rec['correct_result']}/{rec['matches']}"
        if i == len(standings) - 1:
            parts.append(f'<span class="lb-item sack"><b>{escape(role)}</b> {score} — SACK ZONE</span>')
        else:
            parts.append(f'<span class="lb-item"><b>{escape(role)}</b> {score}</span>')
    return "".join(parts)


def _fallback_chat_from_debate(run: dict) -> list:
    """No group_chat (LLM step failed that day): excerpt the proposals instead."""
    legacy = {"Statman": "Stat_Bot", "TacticalAnalyst": "G_Bot", "Contrarian": "R_Bot", "Judge": "K_Bot"}
    proposals = run.get("full_debate", {}).get("proposals", {})
    chat = []
    for role, text in proposals.items():
        display = legacy.get(role, role)
        first_sentence = str(text or "").strip().split(". ")[0][:200]
        if first_sentence:
            chat.append({"role": display, "text": first_sentence})
    return chat


def build_card_html(run: dict, records: dict) -> str:
    home, away = _teams(run)
    decision = run.get("decision", {})
    home_g = decision.get("home_goals", "?")
    away_g = decision.get("away_goals", "?")
    banter = (decision.get("studio_banter_quote") or {}).get("exchange", "")

    chat = run.get("group_chat") or _fallback_chat_from_debate(run)
    bubbles = select_bubbles(chat, banter)

    rows = ""
    for i, msg in enumerate(bubbles):
        role = msg["role"]
        color = ROLE_COLORS.get(role, "#64748b")
        side = "right" if i % 2 else ""
        judge = " judge" if role == "K_Bot" else ""
        text = msg["text"]
        if len(text) > CARD_MSG_LIMIT:
            text = text[:CARD_MSG_LIMIT] + "…"
        rows += (
            f'<div class="row {side}">{_avatar_html(role)}'
            f'<div class="bubble"><div class="who{judge}" style="color:{color};">{escape(role)}</div>'
            f'<div class="msg">{escape(text)}</div></div></div>\n'
        )

    matchday = datetime.now(timezone.utc).strftime("%d %b %Y").upper()
    score_style = ' style="font-size: 34px;"' if len(home) + len(away) > 22 else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  * {{ margin: 0; box-sizing: border-box; }}
  body {{ width: 1200px; height: 675px; font-family: system-ui, -apple-system, sans-serif;
         background: linear-gradient(160deg, #0c1220 0%, #1a2238 100%); color: #f1f5f9;
         display: flex; flex-direction: column; overflow: hidden; }}
  .header {{ padding: 26px 40px 16px; display: flex; justify-content: space-between;
            align-items: baseline; border-bottom: 1px solid rgba(148,163,184,0.25); }}
  .show {{ font-size: 18px; letter-spacing: 4px; color: #94a3b8; font-weight: 600; }}
  .score {{ font-size: 46px; font-weight: 800; letter-spacing: 1px; }}
  .verdict {{ font-size: 16px; color: #94a3b8; }}
  .chat {{ flex: 1; padding: 20px 40px; display: flex; flex-direction: column;
          gap: 14px; justify-content: center; }}
  .row {{ display: flex; gap: 14px; align-items: flex-start; max-width: 76%; }}
  .row.right {{ align-self: flex-end; flex-direction: row-reverse; }}
  .avatar {{ width: 52px; height: 52px; border-radius: 50%; flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px; font-weight: 800; color: white; object-fit: cover; }}
  .bubble {{ background: rgba(30,41,59,0.85); border: 1px solid rgba(148,163,184,0.2);
            border-radius: 16px; padding: 11px 16px; }}
  .who {{ font-size: 13px; font-weight: 700; margin-bottom: 4px; }}
  .msg {{ font-size: 17px; line-height: 1.4; }}
  .strip {{ border-top: 1px solid rgba(148,163,184,0.25); padding: 14px 40px;
           display: flex; justify-content: space-between; align-items: center;
           background: rgba(12,18,32,0.6); }}
  .lb-label {{ color: #94a3b8; font-size: 14px; margin-right: 18px; }}
  .lb-item {{ font-size: 15px; color: #cbd5e1; margin-right: 22px; }}
  .lb-item.sack {{ color: #f87171; }}
  .lb-empty {{ font-size: 14px; color: #94a3b8; }}
  .foot {{ font-size: 13px; color: #64748b; letter-spacing: 2px; }}
</style></head><body>
  <div class="header">
    <div>
      <div class="show">AI FOOTBALL NIGHT</div>
      <div class="score"{score_style}>{escape(home.upper())} {escape(str(home_g))}–{escape(str(away_g))} {escape(away.upper())}</div>
    </div>
    <div class="verdict">THE PANEL'S VERDICT</div>
  </div>
  <div class="chat">
{rows}  </div>
  <div class="strip">
    <div>{_leaderboard_html(records)}</div>
    <div class="foot">WORLD CUP 2026 · {matchday}</div>
  </div>
</body></html>"""


def screenshot_card(html: str, out_path: Path) -> bool:
    """HTML string -> 1200x675 PNG. Returns False (never raises) on failure."""
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
            page = browser.new_page(viewport={"width": 1200, "height": 675})
            page.goto(html_path.resolve().as_uri())
            page.screenshot(path=str(out_path))
            browser.close()
        html_path.unlink(missing_ok=True)
        print(f"  Card: {out_path}")
        return True
    except Exception as e:
        print(f"  ⚠️  Card render failed ({e}) — text-only day, run not blocked")
        return False


def render_for_run(run_path: Path) -> bool:
    from track_record import build_track_records
    run = json.loads(Path(run_path).read_text())
    records = build_track_records(Path(run_path).parent.parent)
    html = build_card_html(run, records)
    out_path = Path(run_path).parent / f"{Path(run_path).stem}_card.png"
    return screenshot_card(html, out_path)


def main():
    parser = argparse.ArgumentParser(description="Render share card PNG(s) from run JSON")
    parser.add_argument("run_file", nargs="?", help="Path to a wc_*.json run file")
    parser.add_argument("--date", help="Render all successful matches from that day's summary (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.date:
        summary_path = Path("runs") / args.date / "daily_summary.json"
        if not summary_path.exists():
            print(f"No summary for {args.date}: {summary_path}")
            sys.exit(0)
        summary = json.loads(summary_path.read_text())
        ok = 0
        for match in summary.get("matches", []):
            if match.get("success") and Path(match["run_file"]).exists():
                ok += render_for_run(Path(match["run_file"]))
        print(f"Rendered {ok} card(s)")
    elif args.run_file:
        success = render_for_run(Path(args.run_file))
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
