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


from director import condense_run


def test_condense_run_pulls_decision_and_chat():
    c = condense_run(SAMPLE_RUN)
    assert c["match"] == "Belgium vs Egypt"
    assert c["slug"] == "belgium-egypt"
    assert c["home_goals"] == 3 and c["away_goals"] == 1
    assert c["host_intro"].startswith("Stat_Bot ignored")
    assert c["stat_bot_highlight"].startswith("Belgium average")
    assert c["most_outrageous_take"].startswith("R_Bot says Salah")
    assert c["rationale"].startswith("Belgium's attacking depth")
    assert len(c["group_chat"]) == 4
    assert c["group_chat"][0] == {"role": "Stat_Bot", "text": SAMPLE_RUN["group_chat"][0]["text"]}


def test_condense_run_tolerates_missing_fields():
    c = condense_run({"match_string": "A vs B", "match_slug": "a-b"})
    assert c["match"] == "A vs B"
    assert c["host_intro"] == "" and c["group_chat"] == []
    assert c["home_goals"] == "?" and c["away_goals"] == "?"


from director import build_director_prompt, _source_text, _word_cap


def test_word_cap_scales_with_duration():
    assert _word_cap(6) == 18 and _word_cap(8) == 24 and _word_cap(10) == 30


def test_source_text_picks_best_available_per_beat():
    c = condense_run(SAMPLE_RUN)
    assert _source_text(c, "cold_open").startswith("Stat_Bot ignored")   # host_intro
    assert _source_text(c, "claim").startswith("Belgium average")         # stat_bot_highlight
    assert _source_text(c, "escalation").startswith("R_Bot says Salah")   # most_outrageous_take
    assert _source_text(c, "verdict").startswith("Belgium's attacking")   # rationale


def test_source_text_verdict_falls_back_to_scoreline():
    c = condense_run({"match_string": "A vs B", "match_slug": "a-b"})
    assert _source_text(c, "verdict") == "?-?"


def test_build_prompt_includes_material_beats_and_grammar():
    prompt = build_director_prompt(condense_run(SAMPLE_RUN), n_shots=5)
    assert "Belgium vs Egypt" in prompt
    assert "Egypt conceded TWO in ten qualifiers" in prompt  # a group_chat line
    assert "cold_open" in prompt and "verdict" in prompt
    assert "PUSH_IN" in prompt and "PUNDIT_STATIC" in prompt  # shot vocabulary offered
    assert '"source"' in prompt and '"shot_type"' in prompt   # schema keys named


from director import parse_shot_script

_OBJ = {"match": "A vs B", "reel_title": "t", "shots": [{"n": 1, "beat": "cold_open"}]}


def test_parse_plain_object():
    assert parse_shot_script(json.dumps(_OBJ)) == _OBJ


def test_parse_strips_markdown_fences():
    assert parse_shot_script("```json\n" + json.dumps(_OBJ) + "\n```") == _OBJ


def test_parse_extracts_object_from_prose():
    assert parse_shot_script("Here you go:\n" + json.dumps(_OBJ) + "\nDone") == _OBJ


def test_parse_returns_none_on_garbage():
    assert parse_shot_script("no json here") is None
    assert parse_shot_script(None) is None
    assert parse_shot_script(json.dumps({"no": "shots"})) is None
    assert parse_shot_script(json.dumps(["a", "list"])) is None


from director import validate_and_repair


def _script(shots):
    return {"match": "Belgium vs Egypt", "reel_title": "t", "shots": shots}


def test_validate_coerces_to_five_beats_in_order():
    out = validate_and_repair(_script([]), condense_run(SAMPLE_RUN), n_shots=5)
    assert [s["beat"] for s in out["shots"]] == ["cold_open", "claim", "counter", "escalation", "verdict"]
    assert [s["n"] for s in out["shots"]] == [1, 2, 3, 4, 5]


def test_validate_forces_host_on_bookends_and_distinct_pundits():
    out = validate_and_repair(_script([]), condense_run(SAMPLE_RUN), n_shots=5)
    s = out["shots"]
    assert s[0]["speaker"] == "K_Bot" and s[4]["speaker"] == "K_Bot"
    middles = {s[1]["speaker"], s[2]["speaker"], s[3]["speaker"]}
    assert middles == {"Stat_Bot", "G_Bot", "R_Bot"}  # three distinct pundits


def test_validate_repairs_bad_speaker_and_duplicate_pundits():
    bad = [
        {"n": 1, "beat": "cold_open", "speaker": "R_Bot", "line": "hi", "source": "host_intro", "shot_type": "PUSH_IN", "duration": 6, "performance": "leans in"},
        {"n": 2, "beat": "claim", "speaker": "Stat_Bot", "line": "a", "source": "stat_bot_highlight", "shot_type": "PUNDIT_STATIC", "duration": 6, "performance": "points"},
        {"n": 3, "beat": "counter", "speaker": "Stat_Bot", "line": "b", "source": "group_chat", "shot_type": "LATERAL_TRACK", "duration": 6, "performance": "nods"},
        {"n": 4, "beat": "escalation", "speaker": "Stat_Bot", "line": "c", "source": "most_outrageous_take", "shot_type": "LOW_ANGLE", "duration": 6, "performance": "scowls"},
        {"n": 5, "beat": "verdict", "speaker": "G_Bot", "line": "d", "source": "rationale", "shot_type": "PULL_BACK", "duration": 6, "performance": "smiles"},
    ]
    out = validate_and_repair(_script(bad), condense_run(SAMPLE_RUN), n_shots=5)["shots"]
    assert out[0]["speaker"] == "K_Bot" and out[4]["speaker"] == "K_Bot"
    assert {out[1]["speaker"], out[2]["speaker"], out[3]["speaker"]} == {"Stat_Bot", "G_Bot", "R_Bot"}


def test_validate_fills_blank_line_from_source_and_records_provenance():
    out = validate_and_repair(_script([]), condense_run(SAMPLE_RUN), n_shots=5)["shots"]
    assert out[0]["line"] and out[0]["source"]   # cold_open got a real line + provenance
    assert all(s["line"] for s in out)


def test_validate_truncates_overlong_line_to_word_cap():
    long = " ".join(["word"] * 50)
    shots = [{"n": 1, "beat": "cold_open", "speaker": "K_Bot", "line": long, "source": "host_intro", "shot_type": "PUSH_IN", "duration": 6, "performance": "leans in"}]
    out = validate_and_repair(_script(shots), condense_run(SAMPLE_RUN), n_shots=5)["shots"]
    assert len(out[0]["line"].split()) <= 18  # _word_cap(6)


def test_validate_fixes_bad_duration_and_shot_type():
    shots = [{"n": 1, "beat": "cold_open", "speaker": "K_Bot", "line": "hi", "source": "host_intro", "shot_type": "BOGUS", "duration": 7, "performance": "leans in"}]
    out = validate_and_repair(_script(shots), condense_run(SAMPLE_RUN), n_shots=5)["shots"]
    assert out[0]["duration"] in VALID_DURATIONS
    assert out[0]["shot_type"] in SHOT_GRAMMAR


from director import _repair_dynamism


def _types(shots):
    return [s["shot_type"] for s in shots]


def _static_count(shots):
    return sum(1 for s in shots if SHOT_GRAMMAR[s["shot_type"]]["static"])


def test_dynamism_guarantees_min_two_static():
    shots = [{"n": i + 1, "beat": BEATS[i]["beat"], "shot_type": "PUSH_IN"} for i in range(5)]
    out = _repair_dynamism([dict(s) for s in shots])
    assert _static_count(out) >= MIN_STATIC


def test_dynamism_breaks_adjacent_moving_repeats():
    shots = [{"n": i + 1, "beat": BEATS[i]["beat"], "shot_type": "PUSH_IN"} for i in range(5)]
    out = _repair_dynamism([dict(s) for s in shots])
    t = _types(out)
    # no two adjacent identical MOVING types
    assert all(not (t[i] == t[i + 1] and not SHOT_GRAMMAR[t[i]]["static"]) for i in range(len(t) - 1))


def test_dynamism_ensures_at_least_two_distinct_types():
    shots = [{"n": i + 1, "beat": BEATS[i]["beat"], "shot_type": "PUNDIT_STATIC"} for i in range(5)]
    out = _repair_dynamism([dict(s) for s in shots])
    assert len(set(_types(out))) >= 2


def test_dynamism_leaves_a_good_assignment_untouched():
    good = ["PUSH_IN", "PUNDIT_STATIC", "LATERAL_TRACK", "LOW_ANGLE", "PULL_BACK"]
    shots = [{"n": i + 1, "beat": BEATS[i]["beat"], "shot_type": good[i]} for i in range(5)]
    out = _repair_dynamism([dict(s) for s in shots])
    assert _types(out) == good


from director import compose_ltx_prompt

_SHOT = {"n": 1, "beat": "cold_open", "speaker": "K_Bot",
         "line": "Belgium average three goals a game; Egypt's clean sheets get tested.",
         "source": "host_intro", "shot_type": "PUSH_IN", "duration": 6,
         "performance": "leans in and raises an eyebrow"}


def test_compose_starts_with_framing_then_lighting():
    out = compose_ltx_prompt(_SHOT)
    assert out.startswith("Medium-close shot.")       # framing first
    assert "Cool neon studio key light" in out         # lighting next


def test_compose_puts_dialogue_in_quotes_and_camera_and_voice():
    out = compose_ltx_prompt(_SHOT)
    assert '"' + _SHOT["line"] + '"' in out             # dialogue inline in quotes
    assert "pushes in" in out                            # camera move phrase
    assert "British broadcast accent" in out             # voice/accent last


def test_compose_under_200_words_and_no_onscreen_text():
    out = compose_ltx_prompt(_SHOT)
    assert len(out.split()) <= 200
    assert "text on screen" not in out.lower() and "subtitle" not in out.lower()


def test_compose_uses_identity_anchor_not_portrait_redescription():
    out = compose_ltx_prompt(_SHOT)
    assert "The android host K_Bot" in out


from director import fallback_shot_script


def test_fallback_produces_valid_five_shot_reel():
    out = fallback_shot_script(condense_run(SAMPLE_RUN), n_shots=5)
    s = out["shots"]
    assert [x["beat"] for x in s] == ["cold_open", "claim", "counter", "escalation", "verdict"]
    assert s[0]["speaker"] == "K_Bot" and s[4]["speaker"] == "K_Bot"
    assert {s[1]["speaker"], s[2]["speaker"], s[3]["speaker"]} == {"Stat_Bot", "G_Bot", "R_Bot"}
    assert all(x["line"] and x["source"] for x in s)
    assert sum(1 for x in s if SHOT_GRAMMAR[x["shot_type"]]["static"]) >= MIN_STATIC


def test_fallback_survives_empty_run():
    out = fallback_shot_script(condense_run({"match_string": "A vs B", "match_slug": "a-b"}), n_shots=5)
    assert len(out["shots"]) == 5
    assert out["shots"][4]["line"] == "?-?"  # verdict falls back to scoreline
