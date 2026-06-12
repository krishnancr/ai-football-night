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
