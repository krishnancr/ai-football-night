"""Tests for scripts/compose_r32_base.py — NO network calls.

Reuses real repo data (runs/base, runs/, schedule.json) read-only for the
deterministic tests; monkeypatches env so fetch_h2h degrades without a call.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import compose_r32_base as crb  # noqa: E402
import teams  # noqa: E402

BASE_DIR = REPO_ROOT / "runs" / "base"
RUNS_DIR = REPO_ROOT / "runs"
SCHEDULE = REPO_ROOT / "schedule.json"

# All 20 keys an existing base file carries.
BASE_SCHEMA_KEYS = {
    "home_team", "away_team", "group", "match_date", "venue",
    "h2h_summary", "h2h_record", "group_context",
    "form_home", "form_away",
    "key_players_home", "key_players_away",
    "team_style_home", "team_style_away",
    "wc_history_home", "wc_history_away",
    "strengths_home", "strengths_away",
    "stats_home", "stats_away",
}


def _r32_fixtures():
    schedule = json.loads(SCHEDULE.read_text())
    return [m for m in schedule if m.get("group") == "R32"]


def test_latest_base_for_team_returns_per_team_block_shape():
    block = crb.latest_base_for_team("Argentina", base_dir=BASE_DIR)
    assert block is not None
    assert set(block.keys()) == set(crb.PER_TEAM_KEYS)
    # The block should carry real per-team facts, not pairing-level keys.
    assert isinstance(block["key_players"], list) and block["key_players"]
    assert isinstance(block["strengths"], list)
    assert isinstance(block["stats"], dict)
    assert "home_team" not in block


def test_latest_base_for_team_unknown_returns_none():
    assert crb.latest_base_for_team("Atlantis", base_dir=BASE_DIR) is None


def test_group_form_for_team_only_wdl_letters():
    form = crb.group_form_for_team("Argentina", runs_dir=RUNS_DIR)
    assert all(letter in {"W", "D", "L"} for letter in form)
    # Argentina played its full group stage (3 matches) before the R32.
    assert len(form) == 3


def test_group_form_for_team_unknown_is_empty():
    assert crb.group_form_for_team("Atlantis", runs_dir=RUNS_DIR) == []


def test_compose_base_has_all_schema_keys_and_r32():
    fixture = {
        "date": "2026-07-03", "home": "Argentina", "away": "Cabo Verde",
        "group": "R32", "venue": "Hard Rock Stadium, Miami Gardens, USA",
        "match_string": "Argentina vs Cabo Verde",
    }
    base = crb.compose_base(fixture, h2h={}, base_dir=BASE_DIR, runs_dir=RUNS_DIR)
    assert set(base.keys()) == BASE_SCHEMA_KEYS
    assert base["group"] == "R32"
    assert base["home_team"] == "Argentina"
    assert base["away_team"] == "Cabo Verde"
    assert base["match_date"] == "2026-07-03"
    assert "knockout" in base["group_context"].lower()


def test_compose_base_empty_safe_h2h_when_none_given():
    fixture = {
        "date": "2026-07-03", "home": "Argentina", "away": "Cabo Verde",
        "group": "R32", "venue": "x", "match_string": "Argentina vs Cabo Verde",
    }
    base = crb.compose_base(fixture, h2h=None, base_dir=BASE_DIR, runs_dir=RUNS_DIR)
    assert base["h2h_summary"] is None
    assert base["h2h_record"] == {
        "home_wins": 0, "draws": 0, "away_wins": 0, "notable_results": [],
    }


def test_compose_base_prefers_group_form_over_base_form():
    fixture = {
        "date": "2026-07-03", "home": "Argentina", "away": "Cabo Verde",
        "group": "R32", "venue": "x", "match_string": "Argentina vs Cabo Verde",
    }
    base = crb.compose_base(fixture, h2h={}, base_dir=BASE_DIR, runs_dir=RUNS_DIR)
    expected = crb.group_form_for_team("Argentina", runs_dir=RUNS_DIR)[-5:]
    assert expected, "Argentina should have derived tournament form"
    assert base["form_home"] == expected


def test_compose_base_canonicalizes_alias_names():
    # 'Ivory Coast' is an alias for the FIFA-canonical "Côte d'Ivoire".
    fixture = {
        "date": "2026-06-30", "home": "Ivory Coast", "away": "Norway",
        "group": "R32", "venue": "x", "match_string": "Ivory Coast vs Norway",
    }
    base = crb.compose_base(fixture, h2h={}, base_dir=BASE_DIR, runs_dir=RUNS_DIR)
    assert base["home_team"] == teams.canonical("Ivory Coast")
    assert base["home_team"] == "Côte d'Ivoire"
    # Per-team block still resolves via slug despite the alias input.
    assert base["key_players_home"]


def test_fetch_h2h_degrades_without_key_and_no_call(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    # Hard guard: if any client were constructed, fail loudly.
    def _boom(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("fetch_h2h made a network/client call without a key")

    monkeypatch.setattr("tavily.TavilyClient", _boom, raising=False)

    result = crb.fetch_h2h("Brazil", "Japan")
    assert result == crb._empty_h2h()
    assert result["h2h_summary"] is None
    assert result["h2h_record"]["home_wins"] == 0


def test_compose_all_returns_16_schema_complete_fixtures():
    composed = crb.compose_all(
        write=False, fetch=False,
        base_dir=BASE_DIR, runs_dir=RUNS_DIR, schedule_path=SCHEDULE,
    )
    assert len(composed) == 16
    for base in composed:
        assert set(base.keys()) == BASE_SCHEMA_KEYS
        assert base["group"] == "R32"


def test_compose_all_no_write_does_not_touch_disk(tmp_path):
    # Writing into a tmp base_dir with write=False must create nothing.
    composed = crb.compose_all(
        write=False, fetch=False,
        base_dir=tmp_path, runs_dir=RUNS_DIR, schedule_path=SCHEDULE,
    )
    assert len(composed) == 16
    assert list(tmp_path.iterdir()) == []
