import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def scored_run():
    run = json.loads((FIXTURES / "sample_run.json").read_text())
    run["match_slug"] = "brazil-croatia"
    run["pundit_predictions"] = {
        "Stat_Bot": {"home_goals": 2, "away_goals": 1},
        "G_Bot": {"home_goals": 1, "away_goals": 0},
        "R_Bot": {"home_goals": 1, "away_goals": 1},
    }
    run["actual"] = {
        "home_goals": 2, "away_goals": 1, "result": "home_win",
        "correct_scoreline": True, "correct_result": True,
    }
    return run


def test_receipts_contains_full_time_score(scored_run):
    from post_pack import format_receipts
    text = format_receipts(scored_run)
    assert "FULL TIME" in text
    assert "Brazil 2–1 Croatia" in text


def test_receipts_marks_each_pundit(scored_run):
    from post_pack import format_receipts
    text = format_receipts(scored_run)
    assert "✅ Stat_Bot" in text     # exact scoreline
    assert "🟡 G_Bot" in text        # right result (home win), wrong score
    assert "❌ R_Bot" in text        # wrong result (predicted draw)


def test_receipts_fits_one_tweet(scored_run):
    from post_pack import format_receipts
    assert len(format_receipts(scored_run)) <= 280


def test_receipts_includes_kbot_line(scored_run):
    from post_pack import format_receipts
    assert "K_Bot:" in format_receipts(scored_run)


def test_kbot_oneliner_deterministic():
    from post_pack import kbot_oneliner
    a = kbot_oneliner("all_wrong", "brazil-croatia")
    b = kbot_oneliner("all_wrong", "brazil-croatia")
    assert a == b
    assert len(a) > 10


def test_kbot_oneliner_varies_by_match():
    from post_pack import kbot_oneliner
    lines = {kbot_oneliner("split", f"slug-{i}") for i in range(12)}
    assert len(lines) >= 2  # bank rotation, not one fixed string


def test_receipts_handles_missing_predictions(scored_run):
    from post_pack import format_receipts
    scored_run["pundit_predictions"] = {}
    text = format_receipts(scored_run)
    assert "FULL TIME" in text  # degrades gracefully, never raises


def test_post_pack_tweet1_is_thread_first_verbatim(scored_run):
    """Tweet 1 in the pack is thread[0] verbatim — the copy can't drift from the card."""
    from post_pack import format_post_pack
    scored_run["date_compact"] = "20260613"
    pack = format_post_pack(scored_run, {}, ["LEAD TWEET matching the card", "t2"])
    tweet1 = pack.split("---\n")[1].rsplit("\n---", 1)[0].strip()
    assert tweet1 == "LEAD TWEET matching the card"


def test_post_pack_points_to_picks_card_and_sack_race(scored_run):
    from post_pack import format_post_pack
    scored_run["date_compact"] = "20260613"
    pack = format_post_pack(scored_run, {}, ["only tweet"])
    assert "_card.png" in pack       # picks card
    assert "sack_race.png" in pack   # finale
    assert "REPLY" in pack


def test_receipts_no_predictions_uses_neutral_quip(scored_run):
    from post_pack import format_receipts, KBOT_LINES
    scored_run["pundit_predictions"] = {}
    text = format_receipts(scored_run)
    assert any(line in text for line in KBOT_LINES["no_calls"])
