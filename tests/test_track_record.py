import json
from pathlib import Path

from track_record import (
    parse_pundit_prediction,
    parse_pundit_advances,
    extract_pundit_predictions,
    extract_pundit_advances,
    build_track_records,
    build_track_records_from_runs,
    format_track_record_block,
    inject_track_records,
)


def test_parse_pundit_prediction_basic():
    assert parse_pundit_prediction("blah blah\nPREDICTION: 2-1") == {"home_goals": 2, "away_goals": 1}


def test_parse_pundit_prediction_en_dash_and_spaces():
    assert parse_pundit_prediction("PREDICTION: 3 – 0") == {"home_goals": 3, "away_goals": 0}


def test_parse_pundit_prediction_takes_last_occurrence():
    text = "Earlier I said PREDICTION: 1-1 but on reflection...\nPREDICTION: 2-0"
    assert parse_pundit_prediction(text) == {"home_goals": 2, "away_goals": 0}


def test_parse_pundit_prediction_none_when_missing():
    assert parse_pundit_prediction("no prediction line here") is None
    assert parse_pundit_prediction(None) is None


def test_extract_prefers_rebuttal_over_proposal():
    debate = {
        "proposals": {"Stat_Bot": "PREDICTION: 2-1"},
        "rebuttals": {"Stat_Bot": "I concede the midfield point. PREDICTION: 1-1"},
    }
    assert extract_pundit_predictions(debate) == {"Stat_Bot": {"home_goals": 1, "away_goals": 1}}


def test_extract_falls_back_to_proposal():
    debate = {
        "proposals": {"U_Bot": "vibes say PREDICTION: 0-2"},
        "rebuttals": {"U_Bot": "I stand by everything I said."},
    }
    assert extract_pundit_predictions(debate) == {"U_Bot": {"home_goals": 0, "away_goals": 2}}


def _write_run(runs_dir, slug, preds, actual):
    date_dir = runs_dir / "2026-06-11"
    date_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "match_string": slug.replace("-", " vs ", 1),
        "decision": {"home_goals": 9, "away_goals": 9},
        "pundit_predictions": preds,
    }
    if actual:
        run["actual"] = actual
    (date_dir / f"wc_{slug}.json").write_text(json.dumps(run))


def test_build_track_records_scores_pundits(tmp_path):
    runs = tmp_path / "runs"
    _write_run(runs, "mexico-southafrica",
               {"Stat_Bot": {"home_goals": 2, "away_goals": 1}, "U_Bot": {"home_goals": 1, "away_goals": 1}},
               {"home_goals": 1, "away_goals": 1, "result": "draw"})
    records = build_track_records(runs)
    assert records["Stat_Bot"]["matches"] == 1
    assert records["Stat_Bot"]["correct_result"] == 0
    assert records["U_Bot"]["correct_result"] == 1
    assert records["U_Bot"]["correct_scoreline"] == 1
    assert records["U_Bot"]["last"]["predicted"] == "1-1"


def test_build_track_records_skips_unscored_runs(tmp_path):
    runs = tmp_path / "runs"
    _write_run(runs, "brazil-morocco", {"Stat_Bot": {"home_goals": 2, "away_goals": 0}}, actual=None)
    assert build_track_records(runs) == {}


def test_format_block_empty_without_data():
    assert format_track_record_block("Stat_Bot", {}) == ""


def test_format_block_mentions_record_and_standings():
    records = {
        "Stat_Bot": {"matches": 2, "correct_result": 1, "correct_scoreline": 0,
                     "last": {"match": "Brazil vs Morocco", "predicted": "2-0", "actual": "1-1", "correct_result": False}},
        "U_Bot": {"matches": 2, "correct_result": 2, "correct_scoreline": 1, "last": None},
    }
    block = format_track_record_block("Stat_Bot", records)
    assert "1/2" in block
    assert "2-0" in block and "1-1" in block
    assert "U_Bot 2/2" in block


def test_inject_appends_to_debaters_not_judge():
    persona_set = {
        "Stat_Bot": {"model": "m", "system": "You are Stat_Bot."},
        "K_Bot": {"model": "m", "system": "You are the judge."},
    }
    records = {"Stat_Bot": {"matches": 1, "correct_result": 1, "correct_scoreline": 1, "last": None}}
    out = inject_track_records(persona_set, records)
    assert "TRACK RECORD" in out["Stat_Bot"]["system"]
    assert out["K_Bot"]["system"] == "You are the judge."
    # original untouched
    assert "TRACK RECORD" not in persona_set["Stat_Bot"]["system"]


def test_inject_noop_without_records():
    persona_set = {"Stat_Bot": {"model": "m", "system": "You are Stat_Bot."}}
    out = inject_track_records(persona_set, {})
    assert out["Stat_Bot"]["system"] == "You are Stat_Bot."


def _records_two_pundits():
    return {
        "Stat_Bot": {"matches": 3, "correct_result": 3, "correct_scoreline": 1,
                     "last": {"match": "A vs B", "predicted": "2-1", "actual": "2-1", "correct_result": True}},
        "U_Bot": {"matches": 3, "correct_result": 0, "correct_scoreline": 0,
                  "last": {"match": "A vs B", "predicted": "0-2", "actual": "2-1", "correct_result": False}},
    }


def test_track_record_block_includes_sack_race_stakes():
    from track_record import format_track_record_block
    block = format_track_record_block("Stat_Bot", _records_two_pundits())
    assert "SACK" in block
    assert "currently 1 of 2" in block


def test_bottom_pundit_gets_sack_zone_warning():
    from track_record import format_track_record_block
    block = format_track_record_block("U_Bot", _records_two_pundits())
    assert "SACK ZONE" in block
    assert "currently 2 of 2" in block


def test_leader_does_not_get_sack_zone_warning():
    from track_record import format_track_record_block
    block = format_track_record_block("Stat_Bot", _records_two_pundits())
    assert "SACK ZONE" not in block


def test_build_track_records_ignores_reasoning_sidecar(tmp_path):
    """A *_reasoning.json sidecar (a JSON list) must not crash track-record building."""
    import json
    from pathlib import Path
    from track_record import build_track_records
    day = tmp_path / "2026-06-12"
    day.mkdir()
    # a reasoning sidecar is a LIST, not a run dict — must be skipped, not crash
    (day / "wc_a-vs-b_reasoning.json").write_text(json.dumps([{"role": "Stat_Bot", "reasoning": "x"}]))
    # a real run with predictions + actual still scores fine
    (day / "wc_a-vs-b.json").write_text(json.dumps({
        "match_string": "A vs B",
        "pundit_predictions": {"Stat_Bot": {"home_goals": 2, "away_goals": 1}},
        "actual": {"home_goals": 2, "away_goals": 1, "result": "home_win"},
    }))
    records = build_track_records(runs_dir=tmp_path)
    assert records["Stat_Bot"]["correct_result"] == 1


# ===== CHANGE 2: knockout ADVANCES parsing =====

def test_parse_advances_basic():
    assert parse_pundit_advances("PREDICTION: 2-1\nADVANCES: Brazil") == "Brazil"


def test_parse_advances_team_name_with_spaces():
    assert parse_pundit_advances("ADVANCES: South Africa") == "South Africa"
    assert parse_pundit_advances("ADVANCES: Côte d'Ivoire") == "Côte d'Ivoire"


def test_parse_advances_strips_trailing_punctuation_and_markdown():
    assert parse_pundit_advances("**ADVANCES: Brazil.**") == "Brazil"


def test_parse_advances_takes_last_occurrence():
    text = "Early I leant ADVANCES: Japan\nBut finally ADVANCES: Netherlands"
    assert parse_pundit_advances(text) == "Netherlands"


def test_parse_advances_none_when_missing():
    assert parse_pundit_advances("PREDICTION: 1-0, no advance line") is None
    assert parse_pundit_advances(None) is None


def test_extract_advances_prefers_rebuttal_over_proposal():
    debate = {
        "proposals": {"U_Bot": "PREDICTION: 1-1\nADVANCES: Japan"},
        "rebuttals": {"U_Bot": "On reflection. PREDICTION: 1-1\nADVANCES: Croatia"},
    }
    assert extract_pundit_advances(debate) == {"U_Bot": "Croatia"}


def test_extract_advances_empty_for_group_stage_debate():
    # group-stage debates carry no ADVANCES line -> nothing extracted
    debate = {"proposals": {"Stat_Bot": "PREDICTION: 2-0"}, "rebuttals": {}}
    assert extract_pundit_advances(debate) == {}


# ===== advance scoring against actual.advanced =====

def test_advance_scoring_when_actual_advanced_present():
    runs = [{
        "match_string": "Brazil vs Croatia",
        "pundit_predictions": {"Stat_Bot": {"home_goals": 1, "away_goals": 1},
                               "U_Bot": {"home_goals": 1, "away_goals": 1}},
        "pundit_advances": {"Stat_Bot": "Brazil", "U_Bot": "Croatia"},
        "actual": {"home_goals": 1, "away_goals": 1, "result": "draw", "advanced": "Croatia"},
    }]
    records = build_track_records_from_runs(runs)
    assert records["U_Bot"]["advance_matches"] == 1
    assert records["U_Bot"]["advance_correct"] == 1
    assert records["Stat_Bot"]["advance_matches"] == 1
    assert records["Stat_Bot"]["advance_correct"] == 0


def test_advance_not_scored_when_actual_advanced_absent():
    runs = [{
        "match_string": "Brazil vs Croatia",
        "pundit_predictions": {"U_Bot": {"home_goals": 1, "away_goals": 1}},
        "pundit_advances": {"U_Bot": "Croatia"},
        "actual": {"home_goals": 1, "away_goals": 1, "result": "draw"},  # no 'advanced'
    }]
    records = build_track_records_from_runs(runs)
    # scoreline/result still scored, advance track simply stays at zero (no crash)
    assert records["U_Bot"]["matches"] == 1
    assert records["U_Bot"]["advance_matches"] == 0


def test_advance_match_is_case_and_punctuation_insensitive():
    runs = [{
        "match_string": "South Africa vs Mexico",
        "pundit_predictions": {"U_Bot": {"home_goals": 2, "away_goals": 1}},
        "pundit_advances": {"U_Bot": "south africa"},
        "actual": {"home_goals": 2, "away_goals": 1, "result": "home_win", "advanced": "South Africa"},
    }]
    records = build_track_records_from_runs(runs)
    assert records["U_Bot"]["advance_correct"] == 1


# ===== stage-scoped record building =====

def _write_staged_run(runs_dir, date, stage, role, preds, actual):
    day = runs_dir / date
    day.mkdir(parents=True, exist_ok=True)
    (day / "daily_summary.json").write_text(json.dumps({"date": date, "stage": stage, "matches": []}))
    slug = f"{role.lower()}-day"
    (day / f"wc_{slug}.json").write_text(json.dumps({
        "match_string": "A vs B",
        "pundit_predictions": {role: preds},
        "actual": actual,
    }))


def test_stage_filter_excludes_group_runs_from_knockout_query(tmp_path):
    runs = tmp_path / "runs"
    # group-stage day: R_Bot's epitaph record
    _write_staged_run(runs, "2026-06-20", "group", "R_Bot",
                      {"home_goals": 2, "away_goals": 0},
                      {"home_goals": 2, "away_goals": 0, "result": "home_win"})
    # knockout day: U_Bot's fresh record
    _write_staged_run(runs, "2026-07-01", "knockout", "U_Bot",
                      {"home_goals": 1, "away_goals": 0},
                      {"home_goals": 1, "away_goals": 0, "result": "home_win"})

    knockout = build_track_records(runs, stage="knockout")
    assert "U_Bot" in knockout
    assert "R_Bot" not in knockout  # group record stays frozen as the epitaph

    group = build_track_records(runs, stage="group")
    assert "R_Bot" in group
    assert "U_Bot" not in group

    alltime = build_track_records(runs)  # stage=None -> everything
    assert "R_Bot" in alltime and "U_Bot" in alltime


def test_stage_filter_defaults_unknown_day_to_group(tmp_path):
    """A day with no daily_summary defaults to 'group' so it never leaks into knockout."""
    runs = tmp_path / "runs"
    day = runs / "2026-06-21"
    day.mkdir(parents=True)
    (day / "wc_x.json").write_text(json.dumps({
        "match_string": "A vs B",
        "pundit_predictions": {"Stat_Bot": {"home_goals": 1, "away_goals": 0}},
        "actual": {"home_goals": 1, "away_goals": 0, "result": "home_win"},
    }))
    assert build_track_records(runs, stage="knockout") == {}
    assert "Stat_Bot" in build_track_records(runs, stage="group")
