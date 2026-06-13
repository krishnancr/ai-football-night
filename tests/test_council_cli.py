import json

from unittest.mock import patch, MagicMock


def test_call_llm_retries_on_json_decode_error():
    """A non-JSON provider body (the Haiti vs Scotland crash) must retry, not kill the run."""
    import council_cli
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content="ok"))]
    err = json.JSONDecodeError("Expecting value", "", 0)
    with patch.object(council_cli.client.chat.completions, "create",
                      side_effect=[err, fake]) as create, \
            patch("council_cli.time.sleep"):
        out = council_cli.call_llm("sys", "usr", model="x")
    assert out == "ok"
    assert create.call_count == 2


def test_call_llm_raises_after_max_attempts():
    """After exhausting retries, the original error propagates so the match is marked failed."""
    import council_cli
    err = json.JSONDecodeError("Expecting value", "", 0)
    with patch.object(council_cli.client.chat.completions, "create",
                      side_effect=err) as create, \
            patch("council_cli.time.sleep"), \
            patch.object(council_cli, "MAX_LLM_ATTEMPTS", 3):
        try:
            council_cli.call_llm("sys", "usr", model="x")
            assert False, "expected JSONDecodeError to propagate"
        except json.JSONDecodeError:
            pass
    assert create.call_count == 3


def test_call_llm_passes_reasoning_effort_in_extra_body():
    import council_cli
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content="ok"))]
    with patch.object(council_cli.client.chat.completions, "create", return_value=fake) as create:
        council_cli.call_llm("sys", "usr", model="x", reasoning_effort="medium")
    kwargs = create.call_args.kwargs
    assert kwargs["extra_body"]["reasoning"] == {"effort": "medium"}


def test_call_llm_merges_reasoning_with_model_fallback():
    import council_cli
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content="ok"))]
    with patch.object(council_cli.client.chat.completions, "create", return_value=fake) as create:
        council_cli.call_llm("sys", "usr", model="x", model_fallback="y", reasoning_effort="high")
    extra = create.call_args.kwargs["extra_body"]
    assert extra["models"] == ["x", "y"]
    assert extra["reasoning"] == {"effort": "high"}


def test_call_llm_omits_reasoning_when_none():
    import council_cli
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content="ok"))]
    with patch.object(council_cli.client.chat.completions, "create", return_value=fake) as create:
        council_cli.call_llm("sys", "usr", model="x")
    assert "reasoning" not in create.call_args.kwargs.get("extra_body", {})


def test_call_llm_records_usage_tokens():
    import council_cli
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content="ok"))]
    fake.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
    council_cli.LAST_USAGE.clear()
    council_cli.LAST_USAGE.update({"prompt_tokens": 0, "completion_tokens": 0, "calls": 0})
    with patch.object(council_cli.client.chat.completions, "create", return_value=fake):
        council_cli.call_llm("sys", "usr", model="x")
    assert council_cli.LAST_USAGE["prompt_tokens"] == 100
    assert council_cli.LAST_USAGE["completion_tokens"] == 200
    assert council_cli.LAST_USAGE["calls"] == 1


def test_call_llm_captures_reasoning_trace():
    import council_cli
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content="ok", reasoning="step1: home advantage. step2: 2-1."))]
    with patch.object(council_cli.client.chat.completions, "create", return_value=fake):
        council_cli.call_llm("sys", "usr", model="x", reasoning_effort="medium")
    assert council_cli.LAST_REASONING["text"] == "step1: home advantage. step2: 2-1."


def test_call_llm_reasoning_none_when_absent():
    import council_cli
    fake = MagicMock()
    msg = MagicMock(content="ok")
    # simulate a message with NO reasoning attribute
    del msg.reasoning
    fake.choices = [MagicMock(message=msg)]
    with patch.object(council_cli.client.chat.completions, "create", return_value=fake):
        council_cli.call_llm("sys", "usr", model="x")
    assert council_cli.LAST_REASONING["text"] is None
