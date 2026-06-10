import json
from unittest.mock import patch

from group_chat import build_group_chat_prompt, parse_group_chat, generate_group_chat, MIN_MESSAGES


SAMPLE_RUN = {
    "decision": {"home_goals": 2, "away_goals": 1, "confidence": 0.7, "rationale": "Midfield control."},
    "full_debate": {
        "proposals": {"Stat_Bot": "xG says 2-1. " * 200, "R_Bot": "Vibes say upset."},
        "cross_critiques": {"Stat_Bot": "G_Bot ignores the data."},
        "rebuttals": {"Stat_Bot": "I stand by 2-1."},
    },
    "persona_set": {"K_Bot": "deepseek/deepseek-chat-v3-0324"},
}

VALID_CHAT = [{"role": "Stat_Bot", "text": f"message {i}"} for i in range(4)] + [
    {"role": "R_Bot", "text": "vibes"},
    {"role": "K_Bot", "text": "verdict: 2-1"},
]


def test_prompt_contains_debate_and_scoreline():
    prompt = build_group_chat_prompt(SAMPLE_RUN)
    assert "Vibes say upset." in prompt
    assert "2-1" in prompt or ('"home_goals": 2' in prompt)


def test_prompt_truncates_long_rounds():
    prompt = build_group_chat_prompt(SAMPLE_RUN)
    assert len(prompt) < 8000


def test_parse_valid_json_array():
    assert parse_group_chat(json.dumps(VALID_CHAT)) == VALID_CHAT


def test_parse_strips_markdown_fences():
    raw = "```json\n" + json.dumps(VALID_CHAT) + "\n```"
    assert parse_group_chat(raw) == VALID_CHAT


def test_parse_extracts_array_from_prose():
    raw = "Here is your chat:\n" + json.dumps(VALID_CHAT) + "\nEnjoy!"
    assert parse_group_chat(raw) == VALID_CHAT


def test_parse_drops_invalid_roles_and_empty_text():
    messy = VALID_CHAT + [{"role": "Intruder", "text": "hi"}, {"role": "Stat_Bot", "text": ""}]
    assert parse_group_chat(json.dumps(messy)) == VALID_CHAT


def test_parse_rejects_too_few_messages():
    assert parse_group_chat(json.dumps(VALID_CHAT[: MIN_MESSAGES - 1])) == []


def test_parse_rejects_garbage():
    assert parse_group_chat("the model rambled with no JSON") == []
    assert parse_group_chat(None) == []


def test_parse_caps_message_length():
    chat = [{"role": "Stat_Bot", "text": "x" * 1000}] * MIN_MESSAGES
    out = parse_group_chat(json.dumps(chat))
    assert all(len(m["text"]) <= 220 for m in out)


def test_generate_returns_parsed_chat():
    with patch("council_cli.call_llm", return_value=json.dumps(VALID_CHAT)) as mock_llm:
        out = generate_group_chat(SAMPLE_RUN)
    assert out == VALID_CHAT
    assert mock_llm.call_args.kwargs["model"] == "deepseek/deepseek-chat-v3-0324"  # K_Bot model


def test_generate_returns_empty_on_llm_failure():
    with patch("council_cli.call_llm", side_effect=RuntimeError("boom")):
        assert generate_group_chat(SAMPLE_RUN) == []
