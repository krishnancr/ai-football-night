import json
import pytest
from pathlib import Path
from daily_runner import get_today_matches, detect_stage, KNOCKOUT_GROUPS, GROUP_LETTERS

FIXTURE_SCHEDULE = Path(__file__).parent / "fixtures" / "sample_schedule.json"


def test_get_today_matches_returns_correct_matches():
    matches = get_today_matches("2026-06-13", FIXTURE_SCHEDULE)
    assert len(matches) == 2
    assert matches[0]["match_string"] == "Brazil vs Morocco"
    assert matches[1]["match_string"] == "Haiti vs Scotland"


def test_get_today_matches_empty_when_no_matches():
    matches = get_today_matches("2026-01-01", FIXTURE_SCHEDULE)
    assert matches == []


def test_detect_stage_returns_group_for_group_matches():
    matches = [{"group": "C"}, {"group": "E"}]
    assert detect_stage(matches) == "group"


def test_detect_stage_returns_knockout_for_knockout_matches():
    matches = [{"group": "QF"}]
    assert detect_stage(matches) == "knockout"


def test_detect_stage_returns_knockout_if_any_match_is_knockout():
    matches = [{"group": "C"}, {"group": "R32"}]
    assert detect_stage(matches) == "knockout"


def test_knockout_groups_does_not_include_letters():
    assert "A" not in KNOCKOUT_GROUPS
    assert "L" not in KNOCKOUT_GROUPS


def test_group_letters_does_not_include_knockout():
    assert "QF" not in GROUP_LETTERS
    assert "R32" not in GROUP_LETTERS


import subprocess
from unittest.mock import patch, MagicMock
from daily_runner import run_match, write_daily_summary, fetch_match_result


def test_run_match_returns_true_on_success(tmp_path):
    with patch("daily_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        success, run_file, thread_file = run_match("Brazil vs Morocco")
    assert success is True
    assert "wc_brazil-morocco.json" in run_file
    assert "_thread.json" in thread_file


def test_run_match_returns_false_on_failure(tmp_path):
    with patch("daily_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        success, run_file, thread_file = run_match("Brazil vs Morocco")
    assert success is False


def test_run_match_passes_no_tweet_flag():
    with patch("daily_runner.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        run_match("Brazil vs Morocco")
    call_args = mock_run.call_args[0][0]
    assert "--no-tweet" in call_args


def test_write_daily_summary_creates_file(tmp_path):
    with patch("daily_runner.RUNS_DIR", tmp_path):
        results = [{"match_string": "Brazil vs Morocco", "run_file": "runs/wc_brazil-morocco_20260613.json", "thread_file": "runs/wc_brazil-morocco_20260613_thread.json", "success": True}]
        path = write_daily_summary("2026-06-13", "group", results)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["date"] == "2026-06-13"
    assert data["stage"] == "group"
    assert len(data["matches"]) == 1


def test_write_daily_summary_filename_format(tmp_path):
    with patch("daily_runner.RUNS_DIR", tmp_path):
        path = write_daily_summary("2026-06-13", "group", [])
    assert path.name == "daily_summary.json"
    assert path.parent.name == "2026-06-13"


def test_fetch_match_result_returns_none_without_tavily_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = fetch_match_result("Brazil vs Morocco")
    assert result is None


def test_fetch_match_result_returns_tuple_on_high_confidence(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    mock_search_result = {"results": [{"title": "Brazil 2-1 Morocco", "content": "Brazil beat Morocco 2-1 in World Cup 2026 group stage match."}]}
    mock_llm_response = MagicMock()
    mock_llm_response.choices[0].message.content = '{"home_goals": 2, "away_goals": 1, "confidence": "high"}'

    with patch("daily_runner.TavilyClient") as MockTavily, \
         patch("daily_runner.OpenAI") as MockOpenAI:
        MockTavily.return_value.search.return_value = mock_search_result
        MockOpenAI.return_value.chat.completions.create.return_value = mock_llm_response
        result = fetch_match_result("Brazil vs Morocco")

    assert result == (2, 1)


def test_fetch_match_result_returns_none_on_low_confidence(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    mock_search_result = {"results": [{"title": "Brazil vs Morocco preview", "content": "Match preview for upcoming World Cup game."}]}
    mock_llm_response = MagicMock()
    mock_llm_response.choices[0].message.content = '{"home_goals": null, "away_goals": null, "confidence": "low"}'

    with patch("daily_runner.TavilyClient") as MockTavily, \
         patch("daily_runner.OpenAI") as MockOpenAI:
        MockTavily.return_value.search.return_value = mock_search_result
        MockOpenAI.return_value.chat.completions.create.return_value = mock_llm_response
        result = fetch_match_result("Brazil vs Morocco")

    assert result is None


from daily_runner import distribute_today, update_yesterday_results


def test_distribute_today_skips_missing_summary(tmp_path, capsys):
    with patch("daily_runner.RUNS_DIR", tmp_path):
        result = distribute_today("2026-06-13")
    assert result == 0
    captured = capsys.readouterr()
    assert "No summary found" in captured.out


def test_distribute_today_skips_failed_matches(tmp_path):
    summary = {
        "date": "2026-06-13", "stage": "group",
        "matches": [{"match_string": "Brazil vs Morocco", "thread_file": "runs/x_thread.json", "success": False}]
    }
    summary_dir = tmp_path / "2026-06-13"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "daily_summary.json").write_text(json.dumps(summary))
    with patch("daily_runner.RUNS_DIR", tmp_path):
        result = distribute_today("2026-06-13")
    assert result == 0


def test_distribute_today_posts_successful_matches(tmp_path):
    thread_file = tmp_path / "2026-06-13" / "wc_brazil-morocco_thread.json"
    thread_file.parent.mkdir(parents=True, exist_ok=True)
    thread_file.write_text(json.dumps(["tweet 1", "tweet 2"]))
    summary = {
        "date": "2026-06-13", "stage": "group",
        "matches": [{"match_string": "Brazil vs Morocco", "thread_file": str(thread_file), "success": True}]
    }
    (tmp_path / "2026-06-13" / "daily_summary.json").write_text(json.dumps(summary))
    with patch("daily_runner.RUNS_DIR", tmp_path), \
         patch("daily_runner.post_twitter_thread") as mock_post:
        result = distribute_today("2026-06-13")
    assert result == 1
    mock_post.assert_called_once_with(["tweet 1", "tweet 2"])


def test_update_yesterday_results_no_previous_files(tmp_path, capsys):
    with patch("daily_runner.RUNS_DIR", tmp_path):
        result = update_yesterday_results("2026-06-13")
    assert result == 0
    captured = capsys.readouterr()
    assert "No previous match days found" in captured.out


def test_update_yesterday_results_skips_already_recorded(tmp_path):
    runs = tmp_path
    run_data = {"match_string": "Brazil vs Morocco", "actual": {"home_goals": 2, "away_goals": 1}}
    (runs / "2026-06-12").mkdir(parents=True, exist_ok=True)
    (runs / "2026-06-12" / "wc_brazil-morocco.json").write_text(json.dumps(run_data))
    with patch("daily_runner.RUNS_DIR", runs):
        result = update_yesterday_results("2026-06-13")
    assert result == 0


def test_update_yesterday_results_records_new_result(tmp_path):
    runs = tmp_path
    run_data = {"match_string": "Brazil vs Morocco", "decision": {"home_goals": 2, "away_goals": 0, "result": "home_win"}}
    (runs / "2026-06-12").mkdir(parents=True, exist_ok=True)
    (runs / "2026-06-12" / "wc_brazil-morocco.json").write_text(json.dumps(run_data))
    with patch("daily_runner.RUNS_DIR", runs), \
         patch("daily_runner.fetch_match_result", return_value=(2, 1)) as mock_fetch, \
         patch("daily_runner.update_result_fn") as mock_record:
        result = update_yesterday_results("2026-06-13")
    assert result == 1
    mock_fetch.assert_called_once_with("Brazil vs Morocco")


def test_result_query_uses_teams_search_name():
    import daily_runner, teams
    # daily_runner must delegate to teams.search, not a private map
    assert not hasattr(daily_runner, "_SEARCH_NAME")
    assert teams.search("Korea Republic") == "South Korea"
