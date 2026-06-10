import json
import pytest
from pathlib import Path
from generate_site import load_run_pairs, is_knockout_match, accuracy_stats, generate_index_html


def _write_pair(tmp_path, slug, date_str, run_extra=None, context_extra=None):
    """Write a run+context pair to tmp_path/runs/."""
    runs = tmp_path / "runs"
    runs.mkdir(exist_ok=True)
    run = {
        "match_string": "Brazil vs Croatia",
        "match_slug": slug,
        "decision": {
            "home_goals": 2, "away_goals": 1, "confidence": 0.67,
            "upset_probability": 0.23, "key_factors": ["factor1"],
            "studio_banter_quote": {"role": "R_Bot", "exchange": "Test exchange."},
            "rationale": "Test rationale.", "dissenting_views": []
        },
        "full_debate": {
            "proposals": {"Stat_Bot": "stat text", "R_Bot": "contra text"},
            "cross_critiques": {"Stat_Bot": "critique"},
            "rebuttals": {"Stat_Bot": "rebuttal"}
        }
    }
    context = {"home_team": "Brazil", "away_team": "Croatia", "match_date": f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}", "group": "D"}
    if run_extra:
        run.update(run_extra)
    if context_extra:
        context.update(context_extra)
    (runs / f"wc_{slug}_{date_str}.json").write_text(json.dumps(run))
    (runs / f"wc_{slug}_{date_str}_context.json").write_text(json.dumps(context))
    return run, context


def test_load_run_pairs_returns_run_and_context(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    assert len(pairs) == 1
    assert pairs[0]["run"]["match_string"] == "Brazil vs Croatia"
    assert pairs[0]["context"]["home_team"] == "Brazil"


def test_load_run_pairs_excludes_context_and_thread_files(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    runs = tmp_path / "runs"
    (runs / "wc_brazil-croatia_20260611_thread.json").write_text("[]")
    pairs = load_run_pairs(runs)
    assert len(pairs) == 1


def test_load_run_pairs_sorted_by_date(tmp_path):
    _write_pair(tmp_path, "germany-curacao", "20260614")
    _write_pair(tmp_path, "brazil-morocco", "20260613")
    pairs = load_run_pairs(tmp_path / "runs")
    assert pairs[0]["run"]["match_slug"] == "brazil-morocco"
    assert pairs[1]["run"]["match_slug"] == "germany-curacao"


def test_is_knockout_match_returns_false_for_group():
    assert is_knockout_match({"group": "D"}) is False
    assert is_knockout_match({"group": "A"}) is False
    assert is_knockout_match({"group": "L"}) is False


def test_is_knockout_match_returns_true_for_knockout():
    assert is_knockout_match({"group": "R32"}) is True
    assert is_knockout_match({"group": "QF"}) is True
    assert is_knockout_match({"group": "FINAL"}) is True


def test_accuracy_stats_with_no_results(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    stats = accuracy_stats(pairs)
    assert stats == {"total": 0, "correct_result": 0, "correct_scoreline": 0}


def test_accuracy_stats_counts_correctly(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611",
                run_extra={"actual_home_goals": 2, "actual_away_goals": 1, "correct_result": True, "correct_scoreline": True})
    _write_pair(tmp_path, "germany-curacao", "20260614",
                run_extra={"actual_home_goals": 3, "actual_away_goals": 0, "correct_result": True, "correct_scoreline": False})
    pairs = load_run_pairs(tmp_path / "runs")
    stats = accuracy_stats(pairs)
    assert stats["total"] == 2
    assert stats["correct_result"] == 2
    assert stats["correct_scoreline"] == 1


def test_accuracy_stats_nested_actual_format(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611",
                run_extra={"actual": {"home_goals": 2, "away_goals": 1,
                                      "correct_result": True, "correct_scoreline": True}})
    pairs = load_run_pairs(tmp_path / "runs")
    stats = accuracy_stats(pairs)
    assert stats == {"total": 1, "correct_result": 1, "correct_scoreline": 1}


def test_generate_index_html_contains_today_match(tmp_path):
    _write_pair(tmp_path, "brazil-morocco", "20260613",
                context_extra={"home_team": "Brazil", "away_team": "Morocco", "group": "C"})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_index_html(pairs, "20260613")
    assert "Brazil" in html
    assert "Morocco" in html
    assert "2–1" in html


def test_generate_index_html_contains_accuracy_tracker(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611",
                run_extra={"actual_home_goals": 2, "actual_away_goals": 1, "correct_result": True, "correct_scoreline": True})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_index_html(pairs, "20260614")
    assert "1/1" in html


def test_generate_index_html_links_to_match_page(tmp_path):
    _write_pair(tmp_path, "brazil-morocco", "20260613")
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_index_html(pairs, "20260613")
    assert "matches/brazil-morocco.html" in html


from generate_site import generate_match_html


def test_group_match_page_contains_role_cards(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "Stat_Bot" in html
    assert "R_Bot" in html
    assert "stat text" in html


def test_group_match_page_contains_verdict(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "The Verdict" in html
    assert "Test rationale" in html
    assert "2–1" in html


def test_group_match_page_shows_actual_result_when_recorded(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611",
                run_extra={"actual_home_goals": 2, "actual_away_goals": 0, "correct_result": False, "correct_scoreline": False})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "2–0" in html
    assert "❌" in html


def test_group_match_page_uses_thread_layout_not_newspaper(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "msg-card" in html
    assert "pull-quote" not in html


def test_knockout_match_page_uses_newspaper_layout(tmp_path):
    _write_pair(tmp_path, "winner-r16-89-vs-winner-r16-90", "20260709",
                context_extra={"group": "QF", "home_team": "Argentina", "away_team": "England"})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "pull-quote" in html
    assert "msg-card" not in html


def test_knockout_match_page_contains_pull_quote(tmp_path):
    _write_pair(tmp_path, "argentina-england", "20260709",
                context_extra={"group": "QF", "home_team": "Argentina", "away_team": "England"})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "Test exchange" in html
    assert "R_Bot" in html


def test_knockout_match_page_collapsible_debate(tmp_path):
    _write_pair(tmp_path, "argentina-england", "20260709",
                context_extra={"group": "QF", "home_team": "Argentina", "away_team": "England"})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "<details>" in html
    assert "<summary>" in html


from generate_site import build_site
from datetime import datetime, timezone


def test_build_site_creates_index_html(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    output_dir = tmp_path / "_site"
    build_site(output_dir, runs_dir=runs_dir)
    assert (output_dir / "index.html").exists()


def test_build_site_creates_match_html(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    output_dir = tmp_path / "_site"
    build_site(output_dir, runs_dir=tmp_path / "runs")
    assert (output_dir / "matches" / "brazil-croatia.html").exists()


def test_build_site_skips_runs_without_slug(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    run_no_slug = {"match_string": "A vs B", "decision": {"home_goals": 1, "away_goals": 0, "confidence": 0.5, "upset_probability": 0.2, "key_factors": [], "best_debate_quote": None, "rationale": "", "dissenting_views": []}, "full_debate": {"proposals": {}, "cross_critiques": {}, "rebuttals": {}}}
    (runs / "wc_a-b_20260611.json").write_text(json.dumps(run_no_slug))
    output_dir = tmp_path / "_site"
    build_site(output_dir, runs_dir=runs)
    assert (output_dir / "index.html").exists()


SAMPLE_CHAT = [
    {"role": "Statman", "text": "xG 2.1 vs 0.8. It's maths."},
    {"role": "Contrarian", "text": "Maths doesn't win tournaments, character does."},
    {"role": "TacticalAnalyst", "text": "Watch the inverted fullback, both of you."},
    {"role": "Statman", "text": "Show me one metric for 'character'."},
    {"role": "Contrarian", "text": "Come to a derby and you'll feel it."},
    {"role": "Judge", "text": "Verdict: 2-1. Someone hose these two down."},
]


def test_group_page_renders_chat_bubbles_when_present(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611", run_extra={"group_chat": SAMPLE_CHAT})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "chat-bubble" in html
    assert "It's maths." in html
    assert "Hose these two down." in html or "hose these two down." in html


def test_group_page_collapses_full_debate_when_chat_present(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611", run_extra={"group_chat": SAMPLE_CHAT})
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "Full debate transcript" in html
    assert "stat text" in html  # full debate still reachable


def test_group_page_falls_back_without_chat(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_match_html(pairs[0]["run"], pairs[0]["context"])
    assert "chat-bubble" not in html
    assert "msg-card" in html


def test_index_shows_pundit_leaderboard_when_scored(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611", run_extra={
        "pundit_predictions": {
            "Stat_Bot": {"home_goals": 2, "away_goals": 1},
            "R_Bot": {"home_goals": 1, "away_goals": 1},
        },
        "actual": {"home_goals": 1, "away_goals": 1, "result": "draw",
                   "correct_result": False, "correct_scoreline": False},
    })
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_index_html(pairs, "20260614")
    assert "Pundit table" in html
    assert "R_Bot" in html
    assert "1/1" in html  # Contrarian called the draw


def test_index_hides_leaderboard_without_scored_predictions(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_index_html(pairs, "20260614")
    assert "Pundit table" not in html


def test_landing_page_when_no_runs_shows_hero_and_pundits():
    html = generate_index_html([], "20260611")
    assert "The Panel" in html
    assert "Stat_Bot" in html
    assert "G_Bot" in html
    assert "R_Bot" in html
    assert "K_Bot" in html
    assert "Predictions for every World Cup 2026 match" in html


def test_landing_page_shows_upcoming_from_schedule():
    schedule = [
        {"date": "2026-06-11", "home": "Mexico", "away": "South Africa", "group": "A"},
        {"date": "2026-06-12", "home": "Canada", "away": "Bosnia and Herzegovina", "group": "B"},
    ]
    html = generate_index_html([], "20260611", schedule=schedule)
    assert "Mexico vs South Africa" in html
    assert "Canada vs Bosnia" in html


def test_runs_page_shows_coming_up_for_tomorrow():
    schedule = [
        {"date": "2026-06-12", "home": "Canada", "away": "Bosnia and Herzegovina", "group": "B"},
    ]
    _pairs_dummy = []
    html = generate_index_html([], "20260611", schedule=schedule)
    assert "Canada vs Bosnia" in html


def test_index_pundits_section_present_when_runs_exist(tmp_path):
    _write_pair(tmp_path, "brazil-croatia", "20260611")
    pairs = load_run_pairs(tmp_path / "runs")
    html = generate_index_html(pairs, "20260614")
    assert "The Panel" in html
    assert "Stat_Bot" in html
