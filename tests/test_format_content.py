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
