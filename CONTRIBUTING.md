# Contributing

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python council_cli.py --list-personas  # verify setup
```

For local Ollama instead of OpenRouter:
```
COUNCIL_BASE_URL=http://localhost:11434/v1
COUNCIL_API_KEY=ollama
```

## Adding a new persona set

1. Add your set to `personas.json` following the existing structure
2. Each role needs `model` (any OpenAI-compatible model string) and `system` (system prompt)
3. The `Judge` role must return valid JSON with at minimum: `decision`, `rationale`, `confidence`
4. Test with `python council_cli.py --persona your_set --decision "test question"`

## Running tests

```bash
pytest tests/ -v
```

## Twitter/X setup

Twitter Elevated Access is required for posting. Apply at [developer.twitter.com](https://developer.twitter.com). Approval can take days — apply early. If rejected, copy thread from `runs/*_thread.json` and post manually.
