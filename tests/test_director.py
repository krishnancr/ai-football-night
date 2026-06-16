import json
from unittest.mock import patch

import director
from director import SHOT_GRAMMAR, BOT_PROFILES, BEATS, VALID_SPEAKERS, VALID_DURATIONS, MIN_STATIC


SAMPLE_RUN = {
    "match_string": "Belgium vs Egypt",
    "match_slug": "belgium-egypt",
    "persona_set": {"K_Bot": "deepseek/deepseek-chat-v3-0324"},
    "decision": {
        "home_goals": 3, "away_goals": 1, "rationale": "Belgium's attacking depth overwhelms a deep block over 90 minutes.",
        "match_headline": "De Bruyne's half-space chess vs Egypt's block",
        "tweet_hook": "Egypt conceded 2 in 10 qualifiers; Belgium average 3.6 a game.",
        "host_intro": "Stat_Bot ignored the keeper, G_Bot built around a suspended pivot, R_Bot backed the wrong resilience.",
        "stat_bot_highlight": "Belgium average 3.625 goals a game; Egypt's clean sheets came against weaker sides.",
        "most_outrageous_take": "R_Bot says Salah drags Egypt to a 1-0 win on a slick surface.",
        "studio_banter_quote": {"role": "Stat_Bot", "exchange": "Stat_Bot: 0.2 GA is a fantasy.\nG_Bot: Numbers ignore compactness."},
    },
    "group_chat": [
        {"role": "Stat_Bot", "text": "Belgium 73.8% per Elo. Egypt's 0.2 GA is cute but irrelevant against 3.6 a game."},
        {"role": "G_Bot", "text": "That 73.8% means nothing against a vertically compact 4-2-3-1 with rest defense."},
        {"role": "R_Bot", "text": "Egypt conceded TWO in ten qualifiers. Seven clean sheets. That back line can defend."},
        {"role": "K_Bot", "text": "Three egos, one scoreline. Let's get to it."},
    ],
    "pundit_predictions": {"Stat_Bot": {"home_goals": 3, "away_goals": 0}},
}


def test_shot_grammar_entries_well_formed():
    assert SHOT_GRAMMAR  # non-empty
    for name, g in SHOT_GRAMMAR.items():
        assert set(g) >= {"framing", "camera", "static", "default_duration"}
        assert isinstance(g["static"], bool)
        assert g["default_duration"] in VALID_DURATIONS


def test_at_least_two_static_shot_types_exist():
    statics = [n for n, g in SHOT_GRAMMAR.items() if g["static"]]
    assert len(statics) >= 2


def test_bot_profiles_cover_all_four_bots():
    assert set(BOT_PROFILES) == VALID_SPEAKERS
    for p in BOT_PROFILES.values():
        assert p["identity"] and p["voice"]


def test_beats_are_five_host_bookended():
    assert [b["beat"] for b in BEATS] == ["cold_open", "claim", "counter", "escalation", "verdict"]
    assert BEATS[0]["speaker"] == "K_Bot" and BEATS[-1]["speaker"] == "K_Bot"
    assert BEATS[1]["speaker"] is None and BEATS[2]["speaker"] is None and BEATS[3]["speaker"] is None
    for b in BEATS:
        assert b["default_shot"] in SHOT_GRAMMAR
