import json


def _personas():
    return json.load(open("personas.json"))["world_cup"]


def test_every_pundit_has_reasoning_effort():
    p = _personas()
    for role in ("Stat_Bot", "G_Bot", "U_Bot", "K_Bot"):
        assert "reasoning_effort" in p[role], f"{role} missing reasoning_effort"
    assert p["K_Bot"]["reasoning_effort"] == "high"


def test_no_fabrication_rule_present():
    p = _personas()
    for role in ("Stat_Bot", "G_Bot", "U_Bot"):
        assert "never invent" in p[role]["system"].lower() or "only" in p[role]["system"].lower()


def test_stat_bot_references_stats_block_not_xg_fabrication():
    p = _personas()
    sys = p["Stat_Bot"]["system"].lower()
    assert "fifa" in sys or "elo" in sys or "qualifying" in sys


# ----- CHANGE 1: R_Bot sacked, U_Bot the giant-killer -----

def test_u_bot_replaces_r_bot():
    p = _personas()
    assert "U_Bot" in p
    assert "R_Bot" not in p


def test_u_bot_is_the_giant_killer():
    sys = _personas()["U_Bot"]["system"].lower()
    assert "giant-killer" in sys or "giant killer" in sys
    # calibrated, grounded-in-a-specific-detail upset specialist (not indiscriminate)
    assert "upset" in sys
    assert "calibrated" in sys


def test_cross_references_point_to_u_bot_not_r_bot():
    p = _personas()
    for role in ("Stat_Bot", "G_Bot", "K_Bot"):
        sys = p[role]["system"]
        assert "R_Bot" not in sys, f"{role} still references R_Bot"
    assert "U_Bot" in p["G_Bot"]["system"]
    assert "U_Bot" in p["K_Bot"]["system"]


# ----- CHANGE 2: knockout ADVANCES format -----

def test_pundits_instruct_both_prediction_and_advances():
    p = _personas()
    for role in ("Stat_Bot", "G_Bot", "U_Bot"):
        sys = p[role]["system"]
        assert "PREDICTION:" in sys, f"{role} missing PREDICTION instruction"
        assert "ADVANCES:" in sys, f"{role} missing ADVANCES instruction"


def test_judge_schema_has_advances_and_u_bot_role_enum():
    sys = _personas()["K_Bot"]["system"]
    assert '"advances"' in sys
    # studio_banter_quote role enum lists the three current pundits
    assert "Stat_Bot|G_Bot|U_Bot" in sys
