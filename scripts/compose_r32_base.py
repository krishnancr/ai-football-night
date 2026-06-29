#!/usr/bin/env python3
"""Compose Round-of-32 base-context files by reusing already-vetted group-stage
per-team data, spending network only on the one genuinely-new pairing piece
(head-to-head).

The R32 schedule has 16 fixtures with no base-context files. Every R32 team
already has 3 vetted group-stage base files on disk, so per-team blocks (form,
key_players, team_style, wc_history, strengths, stats) and tournament form (from
real results in runs/<date>/) can be reused deterministically. Only the H2H for
the brand-new pairing requires a (paid) search + extraction call.

Usage:
    python3 scripts/compose_r32_base.py            # dry-run, no fetch unless --fetch
    python3 scripts/compose_r32_base.py --no-fetch # explicit free dry-run
    python3 scripts/compose_r32_base.py --write     # write base files (fetches h2h)

Self-contained compose logic; reuses teams.py for identity and the same
OpenAI/Tavily client env pattern as research.py for the lone networked call.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# Allow running as `python3 scripts/compose_r32_base.py` from the repo root and
# importing top-level modules (teams.py) when imported as a module from tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import teams  # noqa: E402

# All group-stage run dirs are dated on or before this; knockout dirs are later.
# Used to keep group-stage form derivation from picking up knockout results.
GROUP_STAGE_CUTOFF = "2026-06-27"

# Per-team schema keys, in the order they live (suffixed _home/_away) in a base
# file. latest_base_for_team returns these (unsuffixed).
PER_TEAM_KEYS = ["form", "key_players", "team_style", "wc_history", "strengths", "stats"]

_RUN_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SIDECAR_SUFFIXES = ("_context.json", "_thread.json", "_reasoning.json")

_GROUP_CONTEXT = (
    "Round of 32 knockout — no draws; level after 90 goes to extra time and "
    "penalties. Winner advances to the Round of 16."
)


def _empty_h2h() -> dict:
    """The empty-safe head-to-head dict used whenever H2H is unknown."""
    return {
        "h2h_summary": None,
        "h2h_record": {"home_wins": 0, "draws": 0, "away_wins": 0, "notable_results": []},
    }


def latest_base_for_team(team_name, base_dir=Path("runs/base")):
    """Find the most relevant existing base file containing this team and return
    a normalized per-team dict (form, key_players, team_style, wc_history,
    strengths, stats) pulled from the correct _home/_away side.

    Deterministic: if a team appears in multiple base files, pick the latest
    match_date, breaking ties by filename. Returns None if no file contains the
    team."""
    base_dir = Path(base_dir)
    if not base_dir.is_dir():
        return None
    tslug = teams.slug(team_name)
    candidates = []  # (match_date, filename, side, data)
    for path in sorted(base_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        side = None
        if teams.slug(data.get("home_team", "")) == tslug:
            side = "home"
        elif teams.slug(data.get("away_team", "")) == tslug:
            side = "away"
        if side is None:
            continue
        candidates.append((data.get("match_date") or "", path.name, side, data))
    if not candidates:
        return None
    # Latest match_date, then filename — both sort lexically as desired.
    _date, _name, side, data = max(candidates, key=lambda c: (c[0], c[1]))
    return {key: data.get(f"{key}_{side}") for key in PER_TEAM_KEYS}


def group_form_for_team(team_name, runs_dir=Path("runs")):
    """Scan dated run dirs, find this team's completed group matches (run has an
    'actual' result), and return W/D/L letters from the team's perspective,
    most-recent-last. Empty list if none."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return []
    tslug = teams.slug(team_name)
    dated = []  # (date_str, letter)
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir() or not _RUN_DIR_RE.match(child.name):
            continue
        # Group stage only — skip knockout dirs.
        if child.name > GROUP_STAGE_CUTOFF:
            continue
        for run_path in sorted(child.glob("wc_*.json")):
            if run_path.name.endswith(_SIDECAR_SUFFIXES):
                continue
            try:
                run = json.loads(run_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            actual = run.get("actual")
            match_string = run.get("match_string")
            if not actual or not match_string or " vs " not in match_string:
                continue
            home, away = (p.strip() for p in match_string.split(" vs ", 1))
            if teams.slug(home) == tslug:
                side = "home"
            elif teams.slug(away) == tslug:
                side = "away"
            else:
                continue
            result = actual.get("result")
            if result == "draw":
                letter = "D"
            elif result == "home_win":
                letter = "W" if side == "home" else "L"
            elif result == "away_win":
                letter = "W" if side == "away" else "L"
            else:
                continue
            dated.append((child.name, letter))
    dated.sort(key=lambda d: d[0])
    return [letter for _date, letter in dated]


def compose_base(fixture, h2h, base_dir=Path("runs/base"), runs_dir=Path("runs")):
    """Pure/deterministic. Build the full R32 base-file dict for one fixture.

    `fixture` is a schedule entry; `h2h` is {h2h_summary, h2h_record} (possibly
    empty/None). Per-team blocks come from latest_base_for_team; form prefers
    actual tournament results (last 5) over the per-team base form. Produces all
    20 schema keys; never fabricates per-team facts."""
    home_name = teams.canonical(fixture["home"])
    away_name = teams.canonical(fixture["away"])

    home_block = latest_base_for_team(fixture["home"], base_dir) or {}
    away_block = latest_base_for_team(fixture["away"], base_dir) or {}

    # Prefer real tournament form (last 5), fall back to the per-team base form.
    home_group_form = group_form_for_team(fixture["home"], runs_dir)
    away_group_form = group_form_for_team(fixture["away"], runs_dir)
    form_home = home_group_form[-5:] if home_group_form else (home_block.get("form") or [])
    form_away = away_group_form[-5:] if away_group_form else (away_block.get("form") or [])

    h2h = h2h or {}
    h2h_summary = h2h.get("h2h_summary")
    h2h_record = h2h.get("h2h_record") or _empty_h2h()["h2h_record"]

    return {
        "home_team": home_name,
        "away_team": away_name,
        "group": "R32",
        "match_date": fixture.get("date"),
        "venue": fixture.get("venue"),
        "h2h_summary": h2h_summary,
        "h2h_record": h2h_record,
        "form_home": form_home,
        "form_away": form_away,
        "key_players_home": home_block.get("key_players") or [],
        "key_players_away": away_block.get("key_players") or [],
        "team_style_home": home_block.get("team_style"),
        "team_style_away": away_block.get("team_style"),
        "wc_history_home": home_block.get("wc_history"),
        "wc_history_away": away_block.get("wc_history"),
        "group_context": _GROUP_CONTEXT,
        "strengths_home": home_block.get("strengths") or [],
        "strengths_away": away_block.get("strengths") or [],
        "stats_home": home_block.get("stats") or {},
        "stats_away": away_block.get("stats") or {},
    }


def fetch_h2h(home, away):
    """The ONLY networked function. One Tavily search + one extraction LLM call
    returning {h2h_summary, h2h_record}. On ANY failure (no key, network error,
    unparseable) return the empty-safe h2h dict — never raises."""
    home_q, away_q = teams.search(home), teams.search(away)

    if not os.getenv("TAVILY_API_KEY"):
        print(f"  [h2h] {home} vs {away}: TAVILY_API_KEY unset — empty h2h")
        return _empty_h2h()

    try:
        from tavily import TavilyClient
        from openai import OpenAI
    except Exception as e:  # pragma: no cover - import guard
        print(f"  [h2h] {home} vs {away}: client import failed ({e}) — empty h2h")
        return _empty_h2h()

    query = f"{home_q} vs {away_q} all-time head to head record history"
    try:
        tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        result = tavily.search(query, max_results=3, search_depth="basic")
        snippets = [
            {"title": r["title"], "content": r["content"][:500], "url": r["url"]}
            for r in result.get("results", [])
        ]
    except Exception as e:
        print(f"  [h2h] {home} vs {away}: search failed ({type(e).__name__}) — empty h2h")
        return _empty_h2h()

    prompt = f"""You are extracting the all-time head-to-head record between {home_q} (home) and {away_q} (away) from football news snippets.

Search results:
{json.dumps(snippets, indent=2)}

Return ONLY valid JSON, no prose:
{{
  "h2h_summary": "1-2 sentences summarising their all-time meetings, or null if unknown",
  "h2h_record": {{
    "home_wins": 0,
    "draws": 0,
    "away_wins": 0,
    "notable_results": ["score (winner) - competition - year"]
  }}
}}
Rules:
- home_wins = wins for {home_q}; away_wins = wins for {away_q}; draws = drawn meetings.
- Use 0 for unknown counts and [] for notable_results if none found.
- h2h_summary: null if the snippets contain no head-to-head info. Do not fabricate."""

    try:
        client = OpenAI(
            base_url=os.getenv("COUNCIL_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("COUNCIL_API_KEY", "ollama"),
        )
        research_model = os.getenv("RESEARCH_MODEL", "mistral:7b")
        research_fallback = os.getenv("RESEARCH_MODEL_FALLBACK")
        extra = {}
        if research_fallback:
            extra["extra_body"] = {"models": [research_model, research_fallback]}
        # GLM-5.1 is a thinking model: an 800-token budget gets fully consumed by
        # reasoning and returns EMPTY content with no JSON (the h2h is computed but
        # never emitted). Give it room (matching research.py's 2048) and retry once
        # — the same recovery research.py uses for the same model.
        raw = ""
        for attempt in (1, 2):
            response = client.chat.completions.create(
                model=research_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                **extra,
            )
            raw = response.choices[0].message.content or ""
            if re.search(r"\{.*\}", raw, re.DOTALL):
                break
            if attempt == 1:
                print(f"  [h2h] {home} vs {away}: empty extraction — retrying once")
    except Exception as e:
        print(f"  [h2h] {home} vs {away}: extraction failed ({type(e).__name__}) — empty h2h")
        return _empty_h2h()

    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        print(f"  [h2h] {home} vs {away}: no JSON in extraction — empty h2h")
        return _empty_h2h()
    try:
        parsed = json.loads(json_match.group())
    except json.JSONDecodeError:
        print(f"  [h2h] {home} vs {away}: unparseable extraction — empty h2h")
        return _empty_h2h()

    record = parsed.get("h2h_record") or {}
    h2h = {
        "h2h_summary": parsed.get("h2h_summary"),
        "h2h_record": {
            "home_wins": record.get("home_wins", 0) or 0,
            "draws": record.get("draws", 0) or 0,
            "away_wins": record.get("away_wins", 0) or 0,
            "notable_results": record.get("notable_results") or [],
        },
    }
    print(f"  [h2h] {home} vs {away}: found")
    return h2h


def _r32_fixtures(schedule_path=Path("schedule.json")):
    schedule = json.loads(Path(schedule_path).read_text())
    return [m for m in schedule if m.get("group") == "R32"]


def compose_all(write=False, fetch=True, base_dir=Path("runs/base"),
                runs_dir=Path("runs"), schedule_path=Path("schedule.json")):
    """Compose all R32 base files. fetch=True spends paid h2h calls; write=True
    saves to base_dir/teams.base_filename(home, away). Returns the composed
    dicts."""
    base_dir = Path(base_dir)
    composed = []
    for fixture in _r32_fixtures(schedule_path):
        h2h = fetch_h2h(fixture["home"], fixture["away"]) if fetch else _empty_h2h()
        base = compose_base(fixture, h2h, base_dir=base_dir, runs_dir=runs_dir)
        filename = teams.base_filename(fixture["home"], fixture["away"])
        out_path = base_dir / filename
        h2h_state = "found" if base.get("h2h_summary") else "empty"
        if write:
            base_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(base, indent=2))
            verb = "wrote"
        else:
            verb = "would write"
        print(
            f"  {base['home_team']} vs {base['away_team']} -> {filename} "
            f"| {verb} | h2h: {h2h_state} | form_home={base['form_home']} "
            f"form_away={base['form_away']}"
        )
        composed.append(base)
    return composed


def main():
    parser = argparse.ArgumentParser(description="Compose Round-of-32 base-context files.")
    parser.add_argument("--write", action="store_true",
                        help="write base files (default: dry-run, print what would be written)")
    parser.add_argument("--no-fetch", dest="fetch", action="store_false",
                        help="skip the paid h2h search/extraction; compose with empty h2h")
    parser.set_defaults(fetch=True)
    args = parser.parse_args()

    mode = "WRITE" if args.write else "DRY-RUN"
    fetch_state = "with h2h fetch" if args.fetch else "no fetch (empty h2h)"
    print(f"Composing R32 base files [{mode}, {fetch_state}]")
    composed = compose_all(write=args.write, fetch=args.fetch)
    print(f"Composed {len(composed)} R32 fixtures.")


if __name__ == "__main__":
    main()
