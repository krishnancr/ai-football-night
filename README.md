# AI Football Night ⚽📺

**Four AI pundits. One studio. Every World Cup 2026 match.**

Stat_Bot has the spreadsheets. G_Bot has the touchscreen. R_Bot has the vibes. K_Bot hosts, referees the egos, and calls the final scoreline. Every match day they research the fixtures, argue across three debate rounds, and publish a prediction — then get confronted with their own track record before the next show.

Built on a general multi-model debate engine — works for any decision, not just football.

## How it works

```
schedule.json → daily_runner.py (7am UTC, GitHub Actions)
                    │
                    ├── research.py        Tavily search + LLM synthesis → match context
                    ├── council_cli.py     3-round debate between 4 OSS models (OpenRouter)
                    ├── track_record.py    each pundit sees their past record before debating
                    ├── group_chat.py      debate → group-chat highlight reel
                    ├── format_content.py  Twitter thread + newsletter draft
                    └── generate_site.py   static site → GitHub Pages
```

Predictions, full debates, and the pundit leaderboard: **see the GitHub Pages site for this repo**.

## Quick Start

### Prerequisites
- Python 3.11+
- [OpenRouter](https://openrouter.ai) API key (or local Ollama)
- [Tavily](https://tavily.com) API key (free tier: 1000 searches/month)

### Install

```bash
git clone https://github.com/krishnancr/ai-football-night
cd ai-football-night
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

### Run a match

```bash
# Full pipeline (research → debate → group chat → format), no posting
python run_matchday.py "Brazil vs Croatia" --dry-run

# After the match: record the actual score (feeds the pundits' track records)
python update_result.py runs/wc_brazil-croatia_20260613.json 2 1

# Rebuild the site
python generate_site.py
```

### Run any decision

The debate engine is generic — define a persona set and ask it anything:

```bash
python council_cli.py --persona my_set --decision "Should I take the startup offer?" --context context.txt
```

Add persona sets in `personas.json`: each role needs a `model` (any OpenAI-compatible model string) and a `system` prompt; the `Judge` must return JSON.

## Architecture

```
daily_runner.py     Daily orchestrator — today's matches from schedule.json
run_matchday.py     Single match: research → debate → group chat → format
research.py         Tavily web search + LLM synthesis → match context JSON
council_cli.py      Multi-model debate engine (persona-driven)
track_record.py     Per-pundit prediction tracking + prompt injection
group_chat.py       Debate → group-chat transcript (one LLM call)
personas.json       The panel: Stat_Bot, G_Bot, R_Bot, K_Bot
format_content.py   Newsletter draft + Twitter thread
distribute.py       Tweepy auto-post
update_result.py    Record actual scores
generate_site.py    Static GitHub Pages site from runs/
schedule.json       Full WC2026 fixture list
```

Inference backend is swappable via `.env` — OpenRouter (default, ~$0.02–0.05/debate), local Ollama, or any OpenAI-compatible endpoint.

## License

MIT
