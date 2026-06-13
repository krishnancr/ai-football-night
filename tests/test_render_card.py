import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def card_run():
    run = json.loads((FIXTURES / "sample_run.json").read_text())
    run["match_slug"] = "brazil-croatia"
    # New-key proposals so the card's per-pundit take has something to quote.
    run["full_debate"]["proposals"] = {
        "Stat_Bot": "Brazil Elo (2050) exceeds Croatia by 120 points. PREDICTION: 2-1",
        "G_Bot": "Croatia live in Brazil's rest-defence channel with a 4-3-3. PREDICTION: 2-1",
        "R_Bot": "Croatia have the tournament pedigree to nick this. PREDICTION: 1-2",
    }
    return run


def _records():
    return {
        "Stat_Bot": {"matches": 3, "correct_result": 2, "correct_scoreline": 1, "last": None},
        "G_Bot": {"matches": 3, "correct_result": 3, "correct_scoreline": 0, "last": None},
        "R_Bot": {"matches": 3, "correct_result": 1, "correct_scoreline": 0,
                  "last": {"match": "Mexico vs South Africa", "predicted": "1-2", "actual": "2-0", "correct_result": False}},
    }


# ----- picks card -----

def test_picks_card_has_teams_and_picks(card_run):
    from render_card import build_picks_card
    html = build_picks_card(card_run)
    assert "BRAZIL" in html.upper()
    assert "CROATIA" in html.upper()
    assert html.count('class="pick"') == 4          # four scorelines rendered
    assert '<span class="dash">–</span>' in html    # scoreline separator present


def test_picks_card_has_all_four_bots(card_run):
    from render_card import build_picks_card
    html = build_picks_card(card_run)
    for name in ("STAT_BOT", "G_BOT", "R_BOT", "K_BOT"):
        assert name in html


def test_picks_card_flags_the_outlier(card_run):
    from render_card import build_picks_card
    html = build_picks_card(card_run)
    assert "THE OUTLIER" in html      # R_Bot picked the away side alone
    assert "FINAL VERDICT" in html    # judge card


def test_picks_card_escapes_llm_text(card_run):
    from render_card import build_picks_card
    card_run["decision"]["match_headline"] = '</div><script>alert(1)</script>'
    card_run["decision"]["home_goals"] = "<b>9</b>"
    html = build_picks_card(card_run)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>9</b>" not in html


def test_picks_card_renders_with_unknown_flag(card_run):
    """A team with no flag code must not raise — flags degrade to nothing."""
    from render_card import build_picks_card
    card_run["match_string"] = "Atlantis vs El Dorado"
    html = build_picks_card(card_run)
    assert "ATLANTIS" in html.upper()


# ----- sack race card -----

def test_sack_race_has_standings_and_sack_zone():
    from render_card import build_sack_race_card
    html = build_sack_race_card(_records())
    assert "THE SACK RACE" in html
    assert "SACK ZONE" in html
    assert "R_Bot" in html  # bottom of standings


def test_sack_race_after_n_matches_label():
    from render_card import build_sack_race_card
    html = build_sack_race_card(_records())
    assert "AFTER 3 MATCHES" in html  # max matches in _records


# ----- pure helpers -----

def test_lean_directions():
    from render_card import lean
    assert lean(2, 1) == "H"
    assert lean(1, 2) == "A"
    assert lean(1, 1) == "D"


def test_first_take_skips_throat_clearing():
    from render_card import first_take
    take = first_take("Right, listen. Brazil win because their Elo is 2050 and they press high.")
    assert not take.lower().startswith("right")
    assert "Brazil" in take


def test_chip_for_pulls_real_stat():
    from render_card import chip_for
    assert chip_for("They set up in a 4-3-3 block", "fallback") == "4-3-3"
    assert chip_for("nothing useful here", "fallback") == "fallback"
