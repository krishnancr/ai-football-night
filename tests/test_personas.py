import json


def _personas():
    return json.load(open("personas.json"))["world_cup"]


def test_every_pundit_has_reasoning_effort():
    p = _personas()
    for role in ("Stat_Bot", "G_Bot", "R_Bot", "K_Bot"):
        assert "reasoning_effort" in p[role], f"{role} missing reasoning_effort"
    assert p["K_Bot"]["reasoning_effort"] == "high"


def test_no_fabrication_rule_present():
    p = _personas()
    for role in ("Stat_Bot", "G_Bot", "R_Bot"):
        assert "never invent" in p[role]["system"].lower() or "only" in p[role]["system"].lower()


def test_stat_bot_references_stats_block_not_xg_fabrication():
    p = _personas()
    sys = p["Stat_Bot"]["system"].lower()
    assert "fifa" in sys or "elo" in sys or "qualifying" in sys
