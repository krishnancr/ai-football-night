#!/usr/bin/env python3
"""
Research a World Cup match using Tavily web search.
Two-tier: base context (static, pre-scraped) + daily context (fresh, match-day).
Usage: python research.py "Brazil vs Croatia"
Output: match_context.json
"""
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
from tavily import TavilyClient

import teams

load_dotenv()


def load_base_context(home: str, away: str) -> dict:
    """Load pre-scraped base context if it exists. Keyed via teams.py so the
    '-vs-' filename convention and name aliases can't break the join."""
    base_path = Path("runs/base") / teams.base_filename(home, away)
    if base_path.exists():
        return json.loads(base_path.read_text())
    return {}


def research_daily(match_string: str) -> dict:
    """Run Tavily queries for fresh match-day data: odds, injuries, breaking news."""
    parts = match_string.split(" vs ")
    if len(parts) != 2:
        raise ValueError(f"Match string must be 'Team A vs Team B', got: {match_string}")
    home, away = parts[0].strip(), parts[1].strip()

    if not os.getenv("TAVILY_API_KEY"):
        raise EnvironmentError("TAVILY_API_KEY is not set — check your .env file")

    tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    home_q, away_q = teams.search(home), teams.search(away)
    queries = [
        f"{home_q} {away_q} World Cup 2026 betting odds",
        f"{home_q} {away_q} injuries squad news World Cup 2026",
        f"{home_q} vs {away_q} World Cup 2026 preview prediction",
    ]

    search_results = []
    for query in queries:
        try:
            result = tavily.search(query, max_results=3, search_depth="basic")
            search_results.append({
                "query": query,
                "results": [
                    {"title": r["title"], "content": r["content"][:500], "url": r["url"]}
                    for r in result.get("results", [])
                ],
            })
            print(f"  [daily] {query[:60]}...")
        except Exception as e:
            print(f"  Warning: daily search failed for '{query}': {e}")
            search_results.append({"query": query, "results": [], "error": str(e)})

    return {"search_results": search_results, "home": home, "away": away}


def _degraded_context(home: str, away: str, search_results: list) -> dict:
    """Minimal valid context when synthesis fails — the show must go on."""
    titles = [r["title"] for sr in search_results for r in sr.get("results", [])][:6]
    return {
        "home_team": home, "away_team": away, "match_date": None, "group": None,
        "form_home": [], "form_away": [], "h2h_summary": None,
        "injuries_home": [], "injuries_away": [],
        "odds": {"home_win": None, "draw": None, "away_win": None},
        "key_players_home": [], "key_players_away": [],
        "context": "Research synthesis unavailable — the panel debates on limited context.",
        "recent_news": "; ".join(titles)[:400] or None,
        "research_quality": "degraded",
    }


def _parse_synthesis(raw, home: str, away: str, search_results: list) -> dict:
    """Parse LLM extraction output; degrade gracefully instead of raising."""
    raw = raw or ""
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    candidate = json_match.group() if json_match else raw
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    print(f"  ⚠️  Synthesis output unusable ({len(raw)} chars) — using degraded context")
    return _degraded_context(home, away, search_results)


def merge_context(base: dict, extracted: dict, home: str, away: str) -> dict:
    """Three-tier deterministic merge: base for history, live for injuries/odds/news,
    live-with-base-fallback for form and key players."""
    ctx = {
        "home_team": home,
        "away_team": away,
        "match_date": base.get("match_date"),
        "group": base.get("group"),
        "venue": base.get("venue"),
        # Tier 1 — always base
        "h2h_summary": base.get("h2h_summary"),
        "h2h_record": base.get("h2h_record"),
        "wc_history_home": base.get("wc_history_home"),
        "wc_history_away": base.get("wc_history_away"),
        "group_context": base.get("group_context"),
        "strengths_home": base.get("strengths_home"),
        "strengths_away": base.get("strengths_away"),
        "team_style_home": base.get("team_style_home"),
        "team_style_away": base.get("team_style_away"),
        "stats_home": base.get("stats_home"),
        "stats_away": base.get("stats_away"),
        # Tier 2 — always live (null/empty if not found)
        "injuries_home": extracted.get("injuries_home") or [],
        "injuries_away": extracted.get("injuries_away") or [],
        "odds": extracted.get("odds") or {"home_win": None, "draw": None, "away_win": None},
        "recent_news": extracted.get("recent_news"),
        # Tier 3 — live if present, else base
        "form_home": extracted.get("form_home") or base.get("form_home") or [],
        "form_away": extracted.get("form_away") or base.get("form_away") or [],
        "key_players_home": extracted.get("key_players_home") or base.get("key_players_home") or [],
        "key_players_away": extracted.get("key_players_away") or base.get("key_players_away") or [],
        "context": base.get("group_context") or base.get("context"),
    }
    return ctx


def validate_context(ctx: dict, base: dict) -> tuple:
    """Returns (validated_ctx, quality: 'full'|'partial'|'degraded')"""
    issues = []

    # H2H: should always come from base; log if base had no h2h
    if not ctx.get("h2h_summary") and not base.get("h2h_summary"):
        issues.append("h2h_summary missing from both base and live")

    for issue in issues:
        print(f"  ⚠️  Research validation: {issue}")

    # Quality rating
    critical_fields = ["form_home", "form_away", "key_players_home", "key_players_away"]
    populated = sum(1 for f in critical_fields if ctx.get(f))
    if populated == 4:
        quality = "full"
    elif populated >= 2:
        quality = "partial"
    else:
        quality = "degraded"

    if quality == "degraded":
        print(f"  ❌ RESEARCH DEGRADED for {ctx.get('home_team')} vs {ctx.get('away_team')} "
              f"— base loaded={bool(base)}, critical fields populated={populated}/4. "
              f"Bots will debate near-blind.")
    ctx["research_quality"] = quality
    return ctx, quality


def research_match(match_string: str) -> dict:
    """Full research: merge base context + daily Tavily extraction, three-tier merge to JSON."""
    parts = match_string.split(" vs ")
    if len(parts) != 2:
        raise ValueError(f"Match string must be 'Team A vs Team B', got: {match_string}")
    home, away = parts[0].strip(), parts[1].strip()
    home_q, away_q = teams.search(home), teams.search(away)

    base = load_base_context(home, away)
    if base:
        print(f"  Loaded base context for {home} vs {away}")
    else:
        print(f"  No base context found — running full search")

    daily = research_daily(match_string)
    search_results = daily["search_results"]

    # If no base context, supplement with historical Tavily queries
    if not base:
        tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        for query in [
            f"{home_q} vs {away_q} head to head history football",
            f"{home_q} recent form results 2025 2026",
            f"{away_q} recent form results 2025 2026",
        ]:
            try:
                result = tavily.search(query, max_results=3, search_depth="basic")
                search_results.append({
                    "query": query,
                    "results": [
                        {"title": r["title"], "content": r["content"][:500], "url": r["url"]}
                        for r in result.get("results", [])
                    ],
                })
                print(f"  [fallback] {query[:60]}...")
            except Exception as e:
                search_results.append({"query": query, "results": [], "error": str(e)})

    extraction_prompt = f"""You are extracting structured facts from football news snippets about {home_q} vs {away_q}.

Search results:
{json.dumps(search_results, indent=2)}

Extract ONLY the following fields. Return ONLY valid JSON, no prose:
{{
  "injuries_home": ["Player Name (issue)"],
  "injuries_away": ["Player Name (issue)"],
  "odds": {{"home_win": null, "draw": null, "away_win": null}},
  "recent_news": "2-3 sentences of key news",
  "form_home": ["W","D","L"],
  "form_away": ["W","D","L"],
  "key_players_home": ["Name (role)"],
  "key_players_away": ["Name (role)"]
}}
Rules:
- injuries_home: confirmed injuries for {home_q}. Empty list [] if none found.
- injuries_away: confirmed injuries for {away_q}. Empty list [] if none found.
- odds: decimal odds or null for each value
- recent_news: null if nothing notable
- form_home: last 5 results for {home_q}, most recent last. Empty list [] if not found.
- form_away: last 5 results for {away_q}, most recent last. Empty list [] if not found.
- key_players_home: key players for {home_q} to watch. Empty list [] if not found.
- key_players_away: key players for {away_q} to watch. Empty list [] if not found.
- Use null for unknown values, empty list [] if no items found. Do not fabricate.
- Only include form/key_players if explicitly mentioned in the search results."""

    client = OpenAI(
        base_url=os.getenv("COUNCIL_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("COUNCIL_API_KEY", "ollama"),
    )
    research_model = os.getenv("RESEARCH_MODEL", "mistral:7b")
    research_fallback = os.getenv("RESEARCH_MODEL_FALLBACK")
    extra = {}
    if research_fallback:
        extra["extra_body"] = {"models": [research_model, research_fallback]}
    raw = None
    for attempt in (1, 2):
        try:
            response = client.chat.completions.create(
                model=research_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": extraction_prompt}],
                **extra,
            )
            raw = response.choices[0].message.content
        except Exception as e:
            print(f"  ⚠️  Extraction call failed (attempt {attempt}): {type(e).__name__}: {e}")
            raw = None
        if raw and re.search(r"\{.*\}", raw, re.DOTALL):
            break
        if attempt == 1:
            print("  Retrying extraction once...")

    extracted = _parse_synthesis(raw, home, away, search_results)

    # If extraction itself failed completely, return the degraded context directly
    if extracted.get("research_quality") == "degraded":
        return extracted

    # Deterministic three-tier merge
    ctx = merge_context(base, extracted, home, away)

    # Validation guardrails
    ctx, quality = validate_context(ctx, base)
    print(f"  Research quality: {quality}")

    return ctx


def main():
    if len(sys.argv) < 2:
        print('Usage: python research.py "Brazil vs Croatia"')
        sys.exit(1)

    match_string = sys.argv[1]
    print(f"\nResearching: {match_string}")
    context = research_match(match_string)

    output_path = Path("match_context.json")
    output_path.write_text(json.dumps(context, indent=2))
    print(f"\nSaved to: {output_path}")
    print(json.dumps(context, indent=2))


if __name__ == "__main__":
    main()
