#!/usr/bin/env python3
"""
Director — turn a finished match run JSON into a 5-shot reel shot-script.

One LLM call casts the reel (select & tighten lines, assign speaker/shot/duration);
deterministic code enforces the beat skeleton, shot-grammar, dynamism rules, and
composes each LTX-2.3-compliant prompt. A deterministic fallback guarantees a valid
reel even when the LLM output is unusable. No paid video spend lives here.

Spec: docs/superpowers/specs/2026-06-16-director-design.md
"""
import argparse
import json
import os
import re
from pathlib import Path

VALID_SPEAKERS = {"Stat_Bot", "G_Bot", "R_Bot", "K_Bot"}
PUNDITS = ["Stat_Bot", "G_Bot", "R_Bot"]  # canonical fill order for beats 2-4
VALID_DURATIONS = {6, 8, 10}
MIN_STATIC = 2
DEFAULT_MODEL = "deepseek/deepseek-chat-v3-0324"
STUDIO_LIGHT = "Cool neon studio key light with a magenta rim"

# Each shot = a framing x an LTX-supported camera treatment. `static` marks shots with
# no (or imperceptible) camera move; these are the calm baseline (>= MIN_STATIC per reel).
SHOT_GRAMMAR = {
    "HOST_ANCHOR":   {"framing": "Medium broadcast shot, eye level, framed from the hips up",
                      "camera": "the camera holds a steady static frame",
                      "static": True, "default_duration": 6},
    "PUNDIT_STATIC": {"framing": "Medium shot, framed from the hips up",
                      "camera": "the camera holds a steady static frame",
                      "static": True, "default_duration": 6},
    "PUSH_IN":       {"framing": "Medium-close shot",
                      "camera": "the camera slowly pushes in, ending tighter on the face while keeping it centered and frontal",
                      "static": False, "default_duration": 6},
    "PULL_BACK":     {"framing": "Shot starting close and easing to a medium",
                      "camera": "the camera slowly pulls back to reveal the studio desk, keeping the face centered",
                      "static": False, "default_duration": 6},
    "LATERAL_TRACK": {"framing": "Medium shot",
                      "camera": "the camera slowly pans across, settling with the face centered and frontal",
                      "static": False, "default_duration": 6},
    "LOW_ANGLE":     {"framing": "Medium shot from a slight low angle",
                      "camera": "the camera holds nearly static with a barely perceptible push in",
                      "static": True, "default_duration": 6},
}

# Short identity anchor + voice. Per LTX image-to-video rule we do NOT re-describe the
# portrait (the first-frame image carries the look) — just enough to keep identity + a voice.
BOT_PROFILES = {
    "K_Bot":    {"identity": "The android host K_Bot",
                 "voice": "Her voice is warm, confident and crisp with a British broadcast accent"},
    "Stat_Bot": {"identity": "The android analyst Stat_Bot",
                 "voice": "His voice is precise and clipped, faintly synthetic"},
    "G_Bot":    {"identity": "The android tactician G_Bot",
                 "voice": "His voice is animated and emphatic"},
    "R_Bot":    {"identity": "The old-school android pundit R_Bot",
                 "voice": "His voice is gruff, blunt and gravelly"},
}

# Fixed 5-beat arc (host-bookended). `sources` lists run fields the line may be drawn from,
# in preference order. `default_shot` is the affinity used when the LLM pick is invalid.
BEATS = [
    {"beat": "cold_open",  "speaker": "K_Bot", "sources": ["host_intro", "match_headline", "tweet_hook"], "default_shot": "PUSH_IN"},
    {"beat": "claim",      "speaker": None,    "sources": ["stat_bot_highlight", "group_chat"],            "default_shot": "PUNDIT_STATIC"},
    {"beat": "counter",    "speaker": None,    "sources": ["group_chat", "tweet_hook"],                    "default_shot": "LATERAL_TRACK"},
    {"beat": "escalation", "speaker": None,    "sources": ["most_outrageous_take", "group_chat"],          "default_shot": "LOW_ANGLE"},
    {"beat": "verdict",    "speaker": "K_Bot", "sources": ["rationale", "decision"],                       "default_shot": "PULL_BACK"},
]

GROUP_CHAT_CAP = 14  # keep the prompt small; first N messages carry the spiciest exchange


def condense_run(run: dict) -> dict:
    """Pull only the fields the casting LLM needs into a compact dict."""
    decision = run.get("decision") or {}
    chat = [
        {"role": m.get("role"), "text": str(m.get("text") or "").strip()}
        for m in (run.get("group_chat") or [])
        if m.get("role") in VALID_SPEAKERS and str(m.get("text") or "").strip()
    ][:GROUP_CHAT_CAP]
    return {
        "match": run.get("match_string", ""),
        "slug": run.get("match_slug", ""),
        "home_goals": decision.get("home_goals", "?"),
        "away_goals": decision.get("away_goals", "?"),
        "host_intro": str(decision.get("host_intro") or ""),
        "match_headline": str(decision.get("match_headline") or ""),
        "tweet_hook": str(decision.get("tweet_hook") or ""),
        "stat_bot_highlight": str(decision.get("stat_bot_highlight") or ""),
        "most_outrageous_take": str(decision.get("most_outrageous_take") or ""),
        "rationale": str(decision.get("rationale") or ""),
        "group_chat": chat,
    }


def _word_cap(duration: int) -> int:
    """Hard ceiling on spoken words for a shot. OUR heuristic (~3 words/sec), not an
    official LTX figure — tune after the first real renders."""
    return int(duration) * 3


def _source_text(condensed: dict, beat: str) -> str:
    """Best available run text for a beat, in the beat's source-preference order."""
    chat = condensed.get("group_chat") or []
    if beat == "cold_open":
        return condensed["host_intro"] or condensed["match_headline"] or condensed["tweet_hook"]
    if beat == "claim":
        return condensed["stat_bot_highlight"] or (chat[0]["text"] if chat else "")
    if beat == "counter":
        return (chat[1]["text"] if len(chat) > 1 else "") or condensed["tweet_hook"]
    if beat == "escalation":
        return condensed["most_outrageous_take"] or (chat[2]["text"] if len(chat) > 2 else "")
    if beat == "verdict":
        return condensed["rationale"] or f'{condensed["home_goals"]}-{condensed["away_goals"]}'
    return ""


def _source_name(beat: str) -> str:
    """Canonical provenance label used when code fills a line."""
    return {"cold_open": "host_intro", "claim": "stat_bot_highlight", "counter": "group_chat",
            "escalation": "most_outrageous_take", "verdict": "rationale"}[beat]


_PROMPT_TEMPLATE = """You are the Director of "AI Football Night", cutting a finished pundit debate into a {n_shots}-shot vertical talk-show reel (~30s). Four android pundits: K_Bot (host), Stat_Bot (data), G_Bot (tactics), R_Bot (old-school contrarian).

THE MATCH: {match}  (predicted final score {home_goals}-{away_goals})

MATERIAL YOU MAY CUT FROM (select the best, tighten — do NOT invent new claims or stats):
- host_intro: {host_intro}
- match_headline: {match_headline}
- tweet_hook: {tweet_hook}
- stat_bot_highlight: {stat_bot_highlight}
- most_outrageous_take: {most_outrageous_take}
- rationale: {rationale}
- group_chat:
{group_chat}

PRODUCE EXACTLY {n_shots} SHOTS following this fixed arc (the cut must FLOW — the claim, counter and escalation must actually answer each other, not be three disconnected takes):
1. cold_open  — K_Bot frames the match and stakes.
2. claim      — one pundit plants a strong, specific assertion.
3. counter    — a DIFFERENT pundit directly rebuts shot 2.
4. escalation — the remaining pundit raises the stakes / spiciest angle.
5. verdict    — K_Bot delivers the {home_goals}-{away_goals} scoreline and signs off.

Each spoken line: tighten to ~{soft_words} words (a single short, punchy sentence). Beats 2-4 must be three DIFFERENT pundits from: Stat_Bot, G_Bot, R_Bot.

Pick a shot_type for each shot from this list (vary them so it isn't visually monotonous; at least two should be static): {shot_types}.
Give one PHYSICAL performance cue per shot (e.g. "leans in, raises an eyebrow") — physical action, never an emotion word.

Return ONLY this JSON object, no prose, no markdown fences:
{{"match": "{match}", "reel_title": "<short label, not shown on screen>", "shots": [
  {{"n": 1, "beat": "cold_open", "speaker": "K_Bot", "line": "<tightened spoken line>", "source": "<which field above this line came from>", "shot_type": "<one of the list>", "duration": 6, "performance": "<one physical cue>"}}
]}}"""


def build_director_prompt(condensed: dict, n_shots: int = 5) -> str:
    chat = "\n".join(f'  {m["role"]}: {m["text"]}' for m in condensed["group_chat"]) or "  (none)"
    return _PROMPT_TEMPLATE.format(
        n_shots=n_shots,
        match=condensed["match"],
        home_goals=condensed["home_goals"], away_goals=condensed["away_goals"],
        host_intro=condensed["host_intro"], match_headline=condensed["match_headline"],
        tweet_hook=condensed["tweet_hook"], stat_bot_highlight=condensed["stat_bot_highlight"],
        most_outrageous_take=condensed["most_outrageous_take"], rationale=condensed["rationale"],
        group_chat=chat, soft_words=14, shot_types=", ".join(SHOT_GRAMMAR),
    )
