import json
import pytest
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_run(tmp_path):
    """Copy sample_run.json to a temp file for mutation."""
    run = json.loads((FIXTURES / "sample_run.json").read_text())
    run_path = tmp_path / "wc_test_20260611.json"
    run_path.write_text(json.dumps(run, indent=2))
    return run_path


def test_correct_scoreline(tmp_run):
    from update_result import update_result
    actual = update_result(tmp_run, home_goals=2, away_goals=1)
    assert actual["correct_scoreline"] is True
    assert actual["correct_result"] is True
    assert actual["home_goals"] == 2
    assert actual["away_goals"] == 1


def test_wrong_scoreline_correct_result(tmp_run):
    from update_result import update_result
    # Predicted 2-1 (home_win), actual 3-0 (still home_win)
    actual = update_result(tmp_run, home_goals=3, away_goals=0)
    assert actual["correct_scoreline"] is False
    assert actual["correct_result"] is True


def test_wrong_result(tmp_run):
    from update_result import update_result
    # Predicted 2-1 (home_win), actual 1-2 (away_win)
    actual = update_result(tmp_run, home_goals=1, away_goals=2)
    assert actual["correct_scoreline"] is False
    assert actual["correct_result"] is False
    assert actual["result"] == "away_win"


def test_draw_result(tmp_run):
    from update_result import update_result
    actual = update_result(tmp_run, home_goals=1, away_goals=1)
    assert actual["result"] == "draw"
    assert actual["correct_result"] is False  # predicted home_win


def test_result_written_to_file(tmp_run):
    from update_result import update_result
    update_result(tmp_run, home_goals=2, away_goals=1)
    updated = json.loads(tmp_run.read_text())
    assert "actual" in updated
    assert updated["actual"]["home_goals"] == 2


def test_accuracy_summary(tmp_run, capsys):
    from update_result import update_result
    update_result(tmp_run, home_goals=2, away_goals=1)
    captured = capsys.readouterr()
    assert "correct" in captured.out.lower() or "accuracy" in captured.out.lower()
