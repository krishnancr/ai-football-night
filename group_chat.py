#!/usr/bin/env python3
"""
Compress a full debate run into a short group-chat transcript via one LLM call.

Output: list of {"role": <persona key>, "text": <=220 chars>} dicts stored as
run["group_chat"]. The site renders this as the main match-page content; if
generation fails the site falls back to the full-debate card layout.
"""
import json
import os
import re

VALID_ROLES = {"Stat_Bot", "G_Bot", "R_Bot", "K_Bot"}
MAX_MESSAGE_LEN = 220
MIN_MESSAGES = 6
DEFAULT_MODEL = "deepseek/deepseek-chat-v3-0324"

_PROMPT_TEMPLATE = """You are the producer of "AI Football Night", cutting a full pundit debate down to the spiciest group-chat highlight reel.

THE DEBATE (3 rounds):
{debate}

THE VERDICT:
{verdict}

Rewrite this as a group chat of 14-20 short messages between Stat_Bot (data-obsessed, quotes xG at people), G_Bot (touchscreen tactics nerd, condescending), R_Bot (old-school, hates analytics, all vibes and passion) and K_Bot (witty host, sarcastic about the others' egos).

Rules:
- Each message under 200 characters. Punchy, conversational, like texting.
- Keep the pundits' ACTUAL arguments and numbers from the debate — compress, don't invent stats.
- They interrupt and mock each other. Escalate the disagreement.
- K_Bot sends the final 2 messages: one roasting the panel, one delivering the verdict with the scoreline {home_goals}-{away_goals}.
- Return ONLY a JSON array, no prose, no markdown fences:
[{{"role": "Stat_Bot", "text": "..."}}, {{"role": "R_Bot", "text": "..."}}]
- role must be exactly one of: Stat_Bot, G_Bot, R_Bot, K_Bot."""


def _truncate(text, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


def build_group_chat_prompt(run: dict) -> str:
    debate = run.get("full_debate", {})
    decision = run.get("decision", {})
    sections = []
    for label, key, limit in [
        ("ROUND 1 — OPENING POSITIONS", "proposals", 1500),
        ("ROUND 2 — CRITIQUES", "cross_critiques", 900),
        ("ROUND 3 — REBUTTALS", "rebuttals", 900),
    ]:
        round_data = debate.get(key, {})
        if round_data:
            body = "\n".join(f"{role}: {_truncate(text, limit)}" for role, text in round_data.items())
            sections.append(f"{label}:\n{body}")
    return _PROMPT_TEMPLATE.format(
        debate="\n\n".join(sections),
        verdict=json.dumps({k: decision.get(k) for k in ("home_goals", "away_goals", "confidence", "rationale")}),
        home_goals=decision.get("home_goals", "?"),
        away_goals=decision.get("away_goals", "?"),
    )


def parse_group_chat(raw) -> list:
    """Extract and validate the JSON message array. Returns [] if unusable."""
    raw = raw or ""
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        arr = re.search(r"\[.*\]", raw, re.DOTALL)
        candidate = arr.group(0) if arr else None
    if candidate is None:
        return []
    try:
        messages = json.loads(candidate)
    except Exception:
        return []
    if not isinstance(messages, list):
        return []
    cleaned = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        text = str(msg.get("text") or "").strip()
        if role in VALID_ROLES and text:
            cleaned.append({"role": role, "text": text[:MAX_MESSAGE_LEN]})
    return cleaned if len(cleaned) >= MIN_MESSAGES else []


def generate_group_chat(run: dict, model: str | None = None) -> list:
    """One LLM call → validated group-chat list. Returns [] on any failure."""
    import council_cli
    model = model or os.getenv("GROUP_CHAT_MODEL") or run.get("persona_set", {}).get("K_Bot") or DEFAULT_MODEL
    prompt = build_group_chat_prompt(run)
    system = "You convert sports debate transcripts into punchy group-chat JSON. You output only valid JSON arrays."
    try:
        raw = council_cli.call_llm(system, prompt, temperature=0.7, model=model)
    except Exception as e:
        print(f"  group chat generation failed: {e}")
        return []
    return parse_group_chat(raw)
