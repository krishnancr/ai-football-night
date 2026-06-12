from unittest.mock import patch, MagicMock


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
