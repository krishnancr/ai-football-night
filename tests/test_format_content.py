import json
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def run_data():
    return json.loads((FIXTURES / "sample_run.json").read_text())


@pytest.fixture
def context_data():
    return json.loads((FIXTURES / "sample_context.json").read_text())


def test_format_substack_contains_prediction(run_data, context_data):
    from format_content import format_substack
    draft = format_substack(run_data, context_data)
    assert "Brazil" in draft
    assert "Croatia" in draft
    assert "2-1" in draft or ("2" in draft and "1" in draft)


def test_format_substack_leads_with_debate_quote(run_data, context_data):
    from format_content import format_substack
    draft = format_substack(run_data, context_data)
    quote_pos = draft.find("Contrarian")
    prediction_heading_pos = draft.find("Prediction")
    # The best debate quote should appear early — before or alongside prediction
    assert quote_pos > 0, "Contrarian quote not found in draft"
    assert quote_pos < 1500, "Debate quote appears too late in the draft"


def test_format_substack_includes_key_factors(run_data, context_data):
    from format_content import format_substack
    draft = format_substack(run_data, context_data)
    # At least one key factor from the fixture should appear
    assert "Modric" in draft or "clean sheet" in draft or "squad depth" in draft


def test_format_twitter_thread_returns_list(run_data, context_data):
    from format_content import format_twitter_thread
    thread = format_twitter_thread(run_data, context_data)
    assert isinstance(thread, list)
    assert len(thread) >= 4
    assert len(thread) <= 7


def test_format_twitter_thread_each_tweet_under_280(run_data, context_data):
    from format_content import format_twitter_thread
    thread = format_twitter_thread(run_data, context_data)
    for i, tweet in enumerate(thread):
        assert len(tweet) <= 280, f"Tweet {i} is {len(tweet)} chars (limit 280): {tweet}"


def test_format_twitter_thread_first_tweet_has_prediction(run_data, context_data):
    from format_content import format_twitter_thread
    thread = format_twitter_thread(run_data, context_data)
    first = thread[0]
    assert "Brazil" in first or "Croatia" in first
    assert "2" in first  # goals in prediction


def test_format_twitter_thread_tweet1_no_upset_has_panel_confidence(run_data, context_data):
    from format_content import format_twitter_thread
    thread = format_twitter_thread(run_data, context_data)
    first = thread[0]
    assert "Upset:" not in first, "Tweet 1 should not contain 'Upset:'"
    assert "panel confidence" in first, "Tweet 1 should contain 'panel confidence'"
    hook = run_data["decision"]["tweet_hook"]
    assert hook in first, f"Tweet 1 should contain tweet_hook: {hook!r}"


def test_format_twitter_thread_tweet3_uses_stat_bot_highlight(run_data, context_data):
    from format_content import format_twitter_thread
    thread = format_twitter_thread(run_data, context_data)
    tweet3 = thread[2]
    highlight = run_data["decision"]["stat_bot_highlight"]
    assert highlight in tweet3, f"Tweet 3 should contain stat_bot_highlight: {highlight!r}"
    # The full raw Stat_Bot proposal text should NOT appear verbatim
    raw_statman = run_data["full_debate"]["proposals"]["Statman"]
    assert raw_statman not in tweet3, "Tweet 3 should not contain full raw Stat_Bot proposal text"


def test_format_twitter_thread_tweet1_no_hook_fallback(context_data):
    from format_content import format_twitter_thread
    import copy
    run_no_hook = {
        "decision": {
            "home_goals": 1,
            "away_goals": 0,
            "confidence": 0.75,
            "tweet_hook": "",
            "stat_bot_highlight": "Some stat highlight",
            "match_headline": "Team A vs Team B",
            "studio_banter_quote": {"role": "Council", "exchange": "Heated debate."},
            "key_factors": ["Factor A"],
            "most_outrageous_take": "Outrageous!",
            "host_intro": "Host verdict here.",
        },
        "full_debate": {"proposals": {}},
    }
    thread = format_twitter_thread(run_no_hook, context_data)
    first = thread[0]
    # No blank line gap before "The panel got heated" when hook is empty
    assert "\n\n\n" not in first, "Tweet 1 should not have a blank line gap when tweet_hook is empty"
    assert "The panel got heated" in first


def test_format_twitter_thread_last_tweet_has_link(run_data, context_data):
    from format_content import format_twitter_thread
    thread = format_twitter_thread(run_data, context_data)
    last = thread[-1]
    # Last tweet should reference where to find more
    assert "substack" in last.lower() or "http" in last.lower() or "full" in last.lower()


def test_format_twitter_thread_statbot_tweet_not_empty_with_live_roles(run_data, context_data):
    """Live runs key proposals by Stat_Bot (not legacy Statman) — tweet 3 must not be empty."""
    from format_content import format_twitter_thread
    proposals = run_data["full_debate"]["proposals"]
    proposals["Stat_Bot"] = proposals.pop("Statman")
    thread = format_twitter_thread(run_data, context_data)
    statbot_tweet = thread[2]
    body = statbot_tweet.replace("📊 Stat_Bot:", "").replace("[3/5]", "").strip()
    assert len(body) > 20, f"Stat_Bot tweet body is empty/near-empty: {statbot_tweet!r}"


def test_personas_json_is_valid():
    """personas.json must remain valid JSON after edits."""
    import json
    from pathlib import Path
    personas_path = Path(__file__).parent.parent / "personas.json"
    data = json.loads(personas_path.read_text())
    assert "world_cup" in data
    assert "K_Bot" in data["world_cup"]


def test_kbot_system_contains_tweet_hook():
    """K_Bot system prompt must contain the tweet_hook field definition."""
    import json
    from pathlib import Path
    personas_path = Path(__file__).parent.parent / "personas.json"
    data = json.loads(personas_path.read_text())
    system = data["world_cup"]["K_Bot"]["system"]
    assert "tweet_hook" in system, "K_Bot system prompt missing tweet_hook field"


def test_kbot_system_contains_stat_bot_highlight():
    """K_Bot system prompt must contain the stat_bot_highlight field definition."""
    import json
    from pathlib import Path
    personas_path = Path(__file__).parent.parent / "personas.json"
    data = json.loads(personas_path.read_text())
    system = data["world_cup"]["K_Bot"]["system"]
    assert "stat_bot_highlight" in system, "K_Bot system prompt missing stat_bot_highlight field"


def test_kbot_system_match_headline_forbids_generic_phrases():
    """K_Bot match_headline instruction must list the FORBIDDEN phrases."""
    import json
    from pathlib import Path
    personas_path = Path(__file__).parent.parent / "personas.json"
    data = json.loads(personas_path.read_text())
    system = data["world_cup"]["K_Bot"]["system"]
    assert "FORBIDDEN" in system, "K_Bot system prompt missing FORBIDDEN phrases constraint for match_headline"
    assert "tactical battle" in system, "K_Bot system missing 'tactical battle' in FORBIDDEN list"


def test_kbot_system_banter_quote_is_pre_match_only():
    """K_Bot studio_banter_quote instruction must forbid post-match references."""
    import json
    from pathlib import Path
    personas_path = Path(__file__).parent.parent / "personas.json"
    data = json.loads(personas_path.read_text())
    system = data["world_cup"]["K_Bot"]["system"]
    assert "match has not been played yet" in system, "K_Bot system prompt missing pre-match-only constraint for studio_banter_quote"


def test_sample_run_decision_has_tweet_hook(run_data):
    """Sample run fixture decision must include tweet_hook field."""
    assert "tweet_hook" in run_data["decision"], "sample_run.json decision missing tweet_hook"
    assert len(run_data["decision"]["tweet_hook"]) > 0


def test_sample_run_decision_has_stat_bot_highlight(run_data):
    """Sample run fixture decision must include stat_bot_highlight field."""
    assert "stat_bot_highlight" in run_data["decision"], "sample_run.json decision missing stat_bot_highlight"
    assert len(run_data["decision"]["stat_bot_highlight"]) > 0
