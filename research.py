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

load_dotenv()


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("'", "").replace(".", "")


def load_base_context(home: str, away: str) -> dict:
    """Load pre-scraped base context if it exists."""
    slug = f"{slugify(home)}-{slugify(away)}"
    base_path = Path("runs/base") / f"wc_{slug}_base.json"
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

    queries = [
        f"{home} {away} World Cup 2026 betting odds",
        f"{home} {away} injuries squad news World Cup 2026",
        f"{home} vs {away} World Cup 2026 preview prediction",
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
    """Parse the synthesis LLM output; degrade gracefully instead of raising."""
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


def research_match(match_string: str) -> dict:
    """Full research: merge base context + daily Tavily search, synthesize to JSON."""
    parts = match_string.split(" vs ")
    if len(parts) != 2:
        raise ValueError(f"Match string must be 'Team A vs Team B', got: {match_string}")
    home, away = parts[0].strip(), parts[1].strip()

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
            f"{home} vs {away} head to head history football",
            f"{home} recent form results 2025 2026",
            f"{away} recent form results 2025 2026",
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

    synthesis_prompt = f"""You are a football analyst briefing an AI debate council before a World Cup 2026 match.

Match: {home} vs {away}

Pre-researched base context (historical, static):
{json.dumps(base, indent=2) if base else "None available"}

Fresh web search results (odds, injuries, latest news):
{json.dumps(search_results, indent=2)}

Synthesize everything into structured JSON. Prefer base context for H2H and key players. Prefer search results for odds, injuries, and recent news.
Return ONLY valid JSON (no prose before or after):
{{
  "home_team": "{home}",
  "away_team": "{away}",
  "match_date": null,
  "group": null,
  "form_home": [],
  "form_away": [],
  "h2h_summary": "summary of head-to-head record",
  "injuries_home": [],
  "injuries_away": [],
  "odds": {{"home_win": null, "draw": null, "away_win": null}},
  "key_players_home": [],
  "key_players_away": [],
  "context": "1-2 sentences about match context and stakes",
  "recent_news": "key news items in 2-3 sentences"
}}

Rules:
- form arrays use "W", "D", "L" strings for last 5 results (most recent last)
- injuries arrays use "Player Name (issue)" format
- odds use decimal format (e.g. 1.65) or null if not found
- If information is not available, use null or empty array — do not fabricate"""

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
                messages=[{"role": "user", "content": synthesis_prompt}],
                **extra,
            )
            raw = response.choices[0].message.content
        except Exception as e:
            print(f"  ⚠️  Synthesis call failed (attempt {attempt}): {type(e).__name__}: {e}")
            raw = None
        if raw and re.search(r"\{.*\}", raw, re.DOTALL):
            break
        if attempt == 1:
            print("  Retrying synthesis once...")
    return _parse_synthesis(raw, home, away, search_results)


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
