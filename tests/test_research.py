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


def test_validate_context_quality_rating():
    """Quality rating: all 4 critical fields → 'full'; 2 → 'partial'; 0 → 'degraded'."""
    from research import validate_context

    # All 4 critical fields populated → full
    ctx_full = {
        "form_home": ["W", "D", "W", "W", "L"],
        "form_away": ["D", "W", "W", "L", "W"],
        "key_players_home": ["Lozano (winger)"],
        "key_players_away": ["Tau (forward)"],
        "h2h_summary": "Mexico leads",
    }
    validated, quality = validate_context(ctx_full, {})
    assert quality == "full"
    assert validated["research_quality"] == "full"

    # 2 critical fields populated → partial
    ctx_partial = {
        "form_home": ["W", "W"],
        "form_away": [],
        "key_players_home": ["Lozano (winger)"],
        "key_players_away": [],
        "h2h_summary": None,
    }
    validated, quality = validate_context(ctx_partial, {})
    assert quality == "partial"
    assert validated["research_quality"] == "partial"

    # 0 critical fields populated → degraded
    ctx_degraded = {
        "form_home": [],
        "form_away": [],
        "key_players_home": [],
        "key_players_away": [],
        "h2h_summary": None,
    }
    validated, quality = validate_context(ctx_degraded, {})
    assert quality == "degraded"
    assert validated["research_quality"] == "degraded"


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


def test_load_base_context_finds_vs_named_file(tmp_path, monkeypatch):
    """The real base files are named with '-vs-'; the loader must find them."""
    base_dir = tmp_path / "runs" / "base"
    base_dir.mkdir(parents=True)
    (base_dir / "wc_korea-republic-vs-czechia_base.json").write_text(
        json.dumps({"h2h_summary": "KR leads", "form_home": ["W", "W"]})
    )
    monkeypatch.chdir(tmp_path)
    from research import load_base_context
    base = load_base_context("Korea Republic", "Czechia")
    assert base["h2h_summary"] == "KR leads"
    assert base["form_home"] == ["W", "W"]


def test_validate_context_logs_loudly_when_degraded(capsys):
    from research import validate_context
    ctx = {"form_home": [], "form_away": [], "key_players_home": [], "key_players_away": []}
    out_ctx, quality = validate_context(ctx, base={})
    assert quality == "degraded"
    captured = capsys.readouterr()
    assert "DEGRADED" in captured.out  # visible, not silent


def test_load_base_context_resolves_ivory_coast_exonym(tmp_path, monkeypatch):
    """Base files on disk use the exonym slug 'ivory-coast', but teams.slug()
    canonicalises to 'cote-divoire'. The loader must still find them (Bug 1)."""
    base_dir = tmp_path / "runs" / "base"
    base_dir.mkdir(parents=True)
    (base_dir / "wc_germany-vs-ivory-coast_base.json").write_text(
        json.dumps({"h2h_summary": "GER leads", "form_home": ["W", "W"]})
    )
    (base_dir / "wc_curacao-vs-ivory-coast_base.json").write_text(
        json.dumps({"h2h_summary": "tight", "stats_away": {"elo": 1500}})
    )
    monkeypatch.chdir(tmp_path)
    from research import load_base_context
    base = load_base_context("Germany", "Ivory Coast")
    assert base["h2h_summary"] == "GER leads"
    assert base["form_home"] == ["W", "W"]
    base2 = load_base_context("Curaçao", "Ivory Coast")
    assert base2["stats_away"]["elo"] == 1500


class _FakeLLMClient:
    """Drop-in for research.OpenAI whose extraction always returns junk JSON."""
    def __init__(self, content="I cannot help with that.", **_kw):
        self._content = content
        completions = type("C", (), {"create": lambda _self, **_k: self._resp()})()
        self.chat = type("Chat", (), {"completions": completions})()

    def _resp(self):
        msg = type("M", (), {"content": self._content})()
        choice = type("Ch", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


def test_research_match_keeps_base_when_extraction_fails(monkeypatch):
    """Extraction failing both attempts must NOT discard a base file that loaded
    from disk — Tier-1 history/stats/h2h and Tier-3 fallbacks survive (Bug 2)."""
    import research
    base = {
        "h2h_summary": "Ghana and Panama have history",
        "wc_history_home": "Ghana reached the 2010 quarters",
        "stats_home": {"elo": 1600},
        "form_home": ["W", "D", "W", "L", "W"],
        "form_away": ["L", "L", "D", "W", "D"],
        "key_players_home": ["Kudus (winger)"],
        "key_players_away": ["Carrasquilla (midfielder)"],
    }
    monkeypatch.setattr(research, "load_base_context", lambda h, a: dict(base))
    monkeypatch.setattr(research, "research_daily", lambda m: {
        "search_results": [{"query": "q", "results": [
            {"title": "Ghana name squad", "content": "x", "url": "u"}]}],
        "home": "Ghana", "away": "Panama",
    })
    monkeypatch.setattr(research, "OpenAI", _FakeLLMClient)

    ctx = research.research_match("Ghana vs Panama")
    # Tier-1 base fields survived despite extraction dying
    assert ctx["h2h_summary"] == "Ghana and Panama have history"
    assert ctx["wc_history_home"] == "Ghana reached the 2010 quarters"
    assert ctx["stats_home"]["elo"] == 1600
    # Tier-3 base fallbacks fill all four critical fields → not blind
    assert ctx["form_home"] == ["W", "D", "W", "L", "W"]
    assert ctx["key_players_home"] == ["Kudus (winger)"]
    # Re-rated by validate_context; base fallbacks lift it out of 'degraded'
    assert ctx["research_quality"] == "full"
    # The "synthesis unavailable" news signal is preserved
    assert "Ghana name squad" in (ctx.get("recent_news") or "")


def test_research_match_degraded_when_no_base_and_extraction_fails(monkeypatch):
    """When base is genuinely empty AND extraction fails, degraded is correct."""
    import research
    monkeypatch.setattr(research, "load_base_context", lambda h, a: {})
    monkeypatch.setattr(research, "research_daily", lambda m: {
        "search_results": [{"query": "q", "results": [
            {"title": "Some news", "content": "x", "url": "u"}]}],
        "home": "Foo", "away": "Bar",
    })
    monkeypatch.setattr(research, "OpenAI", _FakeLLMClient)
    # No base → research_match runs the historical Tavily fallback; stub it out.
    class _FakeTavily:
        def __init__(self, **_kw): pass
        def search(self, *_a, **_k): return {"results": []}
    monkeypatch.setattr(research, "TavilyClient", _FakeTavily)
    monkeypatch.setenv("TAVILY_API_KEY", "x")

    ctx = research.research_match("Foo vs Bar")
    assert ctx["research_quality"] == "degraded"


def test_merge_context_passes_stats_blocks_from_base():
    from research import merge_context
    base = {
        "stats_home": {"fifa_rank": 23, "elo": 1789, "qual": {"P": 10, "W": 7, "D": 2, "L": 1, "GF": 22, "GA": 8}},
        "stats_away": {"fifa_rank": 40, "elo": 1650, "qual": {"P": 10, "W": 5, "D": 2, "L": 3, "GF": 15, "GA": 12}},
    }
    ctx = merge_context(base, extracted={}, home="Korea Republic", away="Czechia")
    assert ctx["stats_home"]["elo"] == 1789
    assert ctx["stats_away"]["qual"]["GF"] == 15
