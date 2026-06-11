import json


def _search_results():
    return [{"query": "q1", "results": [
        {"title": "Mexico in fine form ahead of opener", "content": "...", "url": "u"},
    ]}]


def test_parse_synthesis_valid_json():
    from research import _parse_synthesis
    raw = '{"home_team": "Mexico", "away_team": "South Africa", "context": "opener"}'
    ctx = _parse_synthesis(raw, "Mexico", "South Africa", _search_results())
    assert ctx["home_team"] == "Mexico"
    assert "research_quality" not in ctx


def test_parse_synthesis_json_with_prose_wrapper():
    from research import _parse_synthesis
    raw = 'Here you go:\n{"home_team": "Mexico", "away_team": "South Africa"}\nHope that helps!'
    ctx = _parse_synthesis(raw, "Mexico", "South Africa", _search_results())
    assert ctx["home_team"] == "Mexico"


def test_parse_synthesis_none_returns_degraded():
    from research import _parse_synthesis
    ctx = _parse_synthesis(None, "Mexico", "South Africa", _search_results())
    assert ctx["home_team"] == "Mexico"
    assert ctx["away_team"] == "South Africa"
    assert ctx["research_quality"] == "degraded"
    assert "Mexico in fine form" in (ctx["recent_news"] or "")


def test_parse_synthesis_garbage_returns_degraded():
    from research import _parse_synthesis
    ctx = _parse_synthesis("I am unable to help with that.", "Mexico", "South Africa", _search_results())
    assert ctx["research_quality"] == "degraded"


def test_degraded_context_has_all_keys_formatters_need():
    from research import _parse_synthesis
    ctx = _parse_synthesis(None, "Mexico", "South Africa", [])
    for key in ("home_team", "away_team", "match_date", "group", "form_home", "form_away",
                "h2h_summary", "injuries_home", "injuries_away", "odds",
                "key_players_home", "key_players_away", "context", "recent_news"):
        assert key in ctx
    assert ctx["odds"] == {"home_win": None, "draw": None, "away_win": None}


# --- New tests for three-tier merge ---

def test_merge_context_tier1_base_always_wins():
    """Tier 1 fields from base must survive even when extracted has different values."""
    from research import merge_context
    base = {
        "h2h_summary": "Mexico leads 3-1",
        "h2h_record": {"home_wins": 3, "draws": 1, "away_wins": 1},
        "wc_history_home": "Mexico has qualified 17 times",
        "wc_history_away": "South Africa hosted 2010",
        "group_context": "Group A",
        "strengths_home": "Fast attack",
        "strengths_away": "Solid defence",
        "team_style_home": "High press",
        "team_style_away": "Counter",
        "venue": "Estadio Azteca",
    }
    extracted = {
        "h2h_summary": "LLM invented this",
        "h2h_record": "wrong",
        "form_home": ["W", "W", "D", "W", "L"],
        "form_away": ["L", "D", "W", "W", "W"],
        "key_players_home": ["Lozano (winger)"],
        "key_players_away": ["Tau (forward)"],
        "injuries_home": [],
        "injuries_away": [],
        "odds": {"home_win": 1.5, "draw": 3.5, "away_win": 6.0},
        "recent_news": "Big match coming up",
    }
    ctx = merge_context(base, extracted, "Mexico", "South Africa")
    # Tier 1 fields must come from base
    assert ctx["h2h_summary"] == "Mexico leads 3-1"
    assert ctx["h2h_record"] == {"home_wins": 3, "draws": 1, "away_wins": 1}
    assert ctx["venue"] == "Estadio Azteca"
    assert ctx["strengths_home"] == "Fast attack"
    # Tier 2 fields come from extracted
    assert ctx["odds"] == {"home_win": 1.5, "draw": 3.5, "away_win": 6.0}
    assert ctx["recent_news"] == "Big match coming up"
    # Tier 3 fields come from extracted (non-empty)
    assert ctx["form_home"] == ["W", "W", "D", "W", "L"]
    assert ctx["key_players_home"] == ["Lozano (winger)"]


def test_merge_context_tier3_falls_back_to_base_when_extracted_empty():
    """Tier 3: form and key_players fall back to base when extraction returns empty."""
    from research import merge_context
    base = {
        "form_home": ["W", "W", "W", "D", "W"],
        "form_away": ["L", "L", "D", "W", "L"],
        "key_players_home": ["Hernandez (striker)"],
        "key_players_away": ["Bafana (captain)"],
    }
    extracted = {
        "form_home": [],        # empty — should fall back to base
        "form_away": [],        # empty — should fall back to base
        "key_players_home": [], # empty — should fall back to base
        "key_players_away": [], # empty — should fall back to base
        "injuries_home": ["Guardado (hamstring)"],
        "injuries_away": [],
        "odds": {"home_win": None, "draw": None, "away_win": None},
        "recent_news": None,
    }
    ctx = merge_context(base, extracted, "Mexico", "South Africa")
    assert ctx["form_home"] == ["W", "W", "W", "D", "W"]
    assert ctx["form_away"] == ["L", "L", "D", "W", "L"]
    assert ctx["key_players_home"] == ["Hernandez (striker)"]
    assert ctx["key_players_away"] == ["Bafana (captain)"]
    # Tier 2 still comes from extracted
    assert ctx["injuries_home"] == ["Guardado (hamstring)"]


def test_validate_context_restores_empty_form_from_base():
    """validate_context should restore form_home from base when merge left it empty."""
    from research import validate_context
    base = {
        "form_home": ["W", "D", "W", "W", "L"],
        "form_away": ["D", "W", "W", "L", "W"],
        "key_players_home": ["Lozano (winger)"],
        "key_players_away": ["Tau (forward)"],
    }
    ctx = {
        "form_home": [],   # empty after merge
        "form_away": [],   # empty after merge
        "key_players_home": ["Lozano (winger)"],
        "key_players_away": ["Tau (forward)"],
        "h2h_summary": "Mexico leads",
    }
    validated, quality = validate_context(ctx, base)
    assert validated["form_home"] == ["W", "D", "W", "W", "L"]
    assert validated["form_away"] == ["D", "W", "W", "L", "W"]
    assert quality == "full"


def test_validate_context_sets_research_quality_full():
    """research_quality is 'full' when all four critical fields are populated."""
    from research import validate_context
    ctx = {
        "form_home": ["W", "W"],
        "form_away": ["L", "D"],
        "key_players_home": ["Lozano"],
        "key_players_away": ["Tau"],
        "h2h_summary": "Mexico leads",
    }
    validated, quality = validate_context(ctx, {})
    assert quality == "full"
    assert validated["research_quality"] == "full"


def test_validate_context_sets_research_quality_partial():
    """research_quality is 'partial' when 2 or 3 of the 4 critical fields are populated."""
    from research import validate_context
    ctx = {
        "form_home": ["W", "W"],
        "form_away": [],
        "key_players_home": ["Lozano"],
        "key_players_away": [],
        "h2h_summary": None,
    }
    validated, quality = validate_context(ctx, {})
    assert quality == "partial"
    assert validated["research_quality"] == "partial"


def test_validate_context_sets_research_quality_degraded():
    """research_quality is 'degraded' when fewer than 2 critical fields are populated."""
    from research import validate_context
    ctx = {
        "form_home": [],
        "form_away": [],
        "key_players_home": [],
        "key_players_away": [],
        "h2h_summary": None,
    }
    validated, quality = validate_context(ctx, {})
    assert quality == "degraded"
    assert validated["research_quality"] == "degraded"


def test_merge_context_no_base_uses_extracted_tier3():
    """With empty base, Tier 3 fields come from extracted directly."""
    from research import merge_context
    extracted = {
        "form_home": ["W", "L", "W"],
        "form_away": ["D", "W", "L"],
        "key_players_home": ["Player A (striker)"],
        "key_players_away": ["Player B (keeper)"],
        "injuries_home": [],
        "injuries_away": [],
        "odds": {"home_win": None, "draw": None, "away_win": None},
        "recent_news": None,
    }
    ctx = merge_context({}, extracted, "Mexico", "South Africa")
    assert ctx["form_home"] == ["W", "L", "W"]
    assert ctx["key_players_away"] == ["Player B (keeper)"]
    assert ctx["h2h_summary"] is None   # base was empty
