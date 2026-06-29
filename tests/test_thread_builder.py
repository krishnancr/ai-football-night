import json
from pathlib import Path

import pytest

import thread_builder as tb


def _run(slug, match_string, hg, ag, conf, preds, hook="A hook.", headline="A headline."):
    return {
        "match_slug": slug,
        "match_string": match_string,
        "pundit_predictions": preds,
        "decision": {
            "home_goals": hg, "away_goals": ag, "confidence": conf,
            "tweet_hook": hook, "match_headline": headline,
            "most_outrageous_take": "An outrageous take.",
        },
    }


@pytest.fixture
def day(tmp_path):
    d = tmp_path / "2026-06-14"
    d.mkdir()
    (d / "wc_germany-curaçao.json").write_text(json.dumps(_run(
        "germany-curaçao", "Germany vs Curaçao", 3, 0, 0.82,
        {"Stat_Bot": {"home_goals": 3, "away_goals": 0},
         "G_Bot": {"home_goals": 3, "away_goals": 0},
         "U_Bot": {"home_goals": 1, "away_goals": 1}})))
    (d / "wc_netherlands-japan.json").write_text(json.dumps(_run(
        "netherlands-japan", "Netherlands vs Japan", 2, 1, 0.65,
        {"Stat_Bot": {"home_goals": 2, "away_goals": 1},
         "G_Bot": {"home_goals": 2, "away_goals": 1},
         "U_Bot": {"home_goals": 0, "away_goals": 1}})))
    # sidecars that must be ignored by the day loader
    (d / "wc_germany-curaçao_thread.json").write_text("[]")
    (d / "wc_germany-curaçao_context.json").write_text("{}")
    return tmp_path


def test_fifa_code_uses_official_trigrams():
    assert tb.match_hashtag("Netherlands", "Japan") == "#NEDJPN"
    assert tb.match_hashtag("Ivory Coast", "Ecuador") == "#CIVECU"  # alias → Côte d'Ivoire
    assert tb.match_hashtag("Germany", "Curaçao") == "#GERCUW"


def test_flag_emoji_resolves_via_alias():
    assert tb.flag_emoji("Germany") == "🇩🇪"
    assert tb.flag_emoji("Ivory Coast") == "🇨🇮"   # English exonym still resolves
    assert tb.flag_emoji("Curaçao") == "🇨🇼"       # newly added to FLAG
    assert tb.flag_emoji("Nowhereland") == ""       # unknown degrades to no flag


def test_highest_confidence_leads(day):
    md = tb.build_thread_md("2026-06-14", runs_root=day)
    lead_idx = md.index("Germany 3–0 Curaçao")
    other_idx = md.index("Netherlands vs Japan")
    assert lead_idx < other_idx          # 82% match leads the 65% one
    assert "Post 1/3 — LEAD" in md       # 2 games + finale = 3 posts


def test_outlier_called_out(day):
    md = tb.build_thread_md("2026-06-14", runs_root=day)
    assert "U_Bot is the outlier." in md


def test_sidecars_excluded(day):
    runs = tb._load_day_runs(day / "2026-06-14")
    assert len(runs) == 2                # the _thread/_context json are skipped


def test_empty_when_no_runs(tmp_path):
    (tmp_path / "2026-06-14").mkdir()
    assert tb.build_thread_md("2026-06-14", runs_root=tmp_path) == ""
    assert tb.write_thread_md("2026-06-14", runs_root=tmp_path) is None


def test_write_creates_thread_md(day):
    path = tb.write_thread_md("2026-06-14", runs_root=day)
    assert path == day / "2026-06-14" / "THREAD.md"
    assert path.read_text().startswith("# Daily thread —")
