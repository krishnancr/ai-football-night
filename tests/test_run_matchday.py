import json
from pathlib import Path


def _completed_run(tmp_path):
    p = tmp_path / "wc_a-b_20260611.json"
    p.write_text(json.dumps({"decision": {"home_goals": 2, "away_goals": 1}}))
    return p


def test_should_skip_completed_run(tmp_path):
    from run_matchday import should_skip_run
    assert should_skip_run(_completed_run(tmp_path)) is True


def test_should_not_skip_missing_run(tmp_path):
    from run_matchday import should_skip_run
    assert should_skip_run(tmp_path / "nope.json") is False


def test_force_overrides_skip(tmp_path):
    from run_matchday import should_skip_run
    assert should_skip_run(_completed_run(tmp_path), force=True) is False


def test_should_not_skip_parse_error_run(tmp_path):
    from run_matchday import should_skip_run
    p = tmp_path / "wc_a-b_20260611.json"
    p.write_text(json.dumps({"decision": {"parse_error": True}}))
    assert should_skip_run(p) is False


def test_should_not_skip_corrupt_json(tmp_path):
    from run_matchday import should_skip_run
    p = tmp_path / "wc_a-b_20260611.json"
    p.write_text("{not json")
    assert should_skip_run(p) is False
