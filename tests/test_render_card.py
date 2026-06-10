import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def card_run():
    run = json.loads((FIXTURES / "sample_run.json").read_text())
    run["match_slug"] = "brazil-croatia"
    run["group_chat"] = [
        {"role": "Stat_Bot", "text": "xG says Brazil 2.1 per game. R_Bot, that's a number — look it up."},
        {"role": "R_Bot", "text": "Numbers never won a World Cup, son. Croatia have the minerals."},
        {"role": "G_Bot", "text": "You're both ignoring Brazil's rest defence. Croatia live in that channel."},
        {"role": "K_Bot", "text": "Gentlemen. On the record: Brazil 2-1. Someone's getting sacked at this rate."},
        {"role": "Stat_Bot", "text": "Put me down for 2-1 exact. The scatter graph has spoken."},
        {"role": "R_Bot", "text": "Scatter graphs. In a WORLD CUP. Unbelievable."},
    ]
    return run


def _records():
    return {
        "Stat_Bot": {"matches": 3, "correct_result": 2, "correct_scoreline": 1, "last": None},
        "G_Bot": {"matches": 3, "correct_result": 3, "correct_scoreline": 0, "last": None},
        "R_Bot": {"matches": 3, "correct_result": 1, "correct_scoreline": 0, "last": None},
    }


def test_card_html_has_scoreline_and_teams(card_run):
    from render_card import build_card_html
    html = build_card_html(card_run, _records())
    assert "BRAZIL" in html.upper()
    assert "CROATIA" in html.upper()
    assert "2–1" in html


def test_card_html_selects_four_bubbles(card_run):
    from render_card import build_card_html
    html = build_card_html(card_run, _records())
    assert html.count('class="bubble"') == 4


def test_card_html_has_sack_zone_for_bottom_pundit(card_run):
    from render_card import build_card_html
    html = build_card_html(card_run, _records())
    assert "SACK ZONE" in html
    assert "R_Bot" in html  # bottom of _records standings


def test_card_html_empty_records_state(card_run):
    from render_card import build_card_html
    html = build_card_html(card_run, {})
    assert "Records start after Matchday 1" in html
    assert "SACK ZONE" not in html


def test_card_html_no_group_chat_falls_back_to_debate(card_run):
    from render_card import build_card_html
    card_run.pop("group_chat")
    html = build_card_html(card_run, _records())
    # Falls back to proposal excerpts — card still renders with bubbles
    assert html.count('class="bubble"') >= 2


def test_bubble_selection_is_deterministic(card_run):
    from render_card import select_bubbles
    chat = card_run["group_chat"]
    quote = card_run["decision"]["studio_banter_quote"]["exchange"]
    assert select_bubbles(chat, quote) == select_bubbles(chat, quote)
    assert len(select_bubbles(chat, quote)) == 4


def test_card_html_escapes_llm_text(card_run):
    from render_card import build_card_html
    card_run["group_chat"][0]["text"] = '</div><script>alert(1)</script> xG says no'
    card_run["decision"]["home_goals"] = "<b>9</b>"
    html = build_card_html(card_run, _records())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>9</b>" not in html


def test_card_html_truncates_long_messages(card_run):
    from render_card import build_card_html, CARD_MSG_LIMIT
    card_run["group_chat"][0]["text"] = "A" * 220
    html = build_card_html(card_run, _records())
    assert "A" * 220 not in html
    assert "A" * CARD_MSG_LIMIT + "…" in html


def test_card_html_shrinks_score_for_long_team_names(card_run):
    from render_card import build_card_html
    card_run["match_string"] = "Bosnia and Herzegovina vs Korea Republic"
    html = build_card_html(card_run, _records())
    assert "font-size: 34px" in html
