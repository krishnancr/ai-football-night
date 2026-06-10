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
