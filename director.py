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


def parse_shot_script(raw):
    """Extract the JSON object from the LLM reply. Returns the dict, or None if unusable."""
    raw = raw or ""
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        obj = re.search(r"\{.*\}", raw, re.DOTALL)
        candidate = obj.group(0) if obj else None
    if candidate is None:
        return None
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("shots"), list):
        return None
    return data


def _repair_dynamism(shots):
    """Enforce the calm-first dynamism rules, deterministically:
       (1) no two adjacent identical MOVING shot_types,
       (2) >= MIN_STATIC static shots,
       (3) >= 2 distinct shot_types overall.
    Pundit beats (2-4) are the adjustable ones; host bookends keep their complementary feel."""
    def is_static(t):
        return SHOT_GRAMMAR[t]["static"]

    # (1) Break adjacent identical MOVING repeats by falling back to the later beat's default,
    #     then to the first non-conflicting type.
    for i in range(1, len(shots)):
        cur = shots[i]["shot_type"]
        if cur == shots[i - 1]["shot_type"] and not is_static(cur):
            default = BEATS[i]["default_shot"]
            choice = default if default != shots[i - 1]["shot_type"] else None
            if choice is None:
                choice = next((t for t in SHOT_GRAMMAR if t != shots[i - 1]["shot_type"]), cur)
            shots[i]["shot_type"] = choice

    # (2) Top up statics, converting pundit beats (2-4) to PUNDIT_STATIC, latest first.
    pundit_idx = [i for i, s in enumerate(shots) if not BEATS[i]["speaker"]]
    for i in reversed(pundit_idx):
        if sum(1 for s in shots if is_static(s["shot_type"])) >= MIN_STATIC:
            break
        shots[i]["shot_type"] = "PUNDIT_STATIC"

    # (3) Guarantee variety: if everything collapsed to one type, set complementary bookends.
    if len({s["shot_type"] for s in shots}) < 2 and len(shots) >= 2:
        shots[0]["shot_type"] = "PUSH_IN"
        shots[-1]["shot_type"] = "PULL_BACK"
    return shots


def _clean_str(value) -> str:
    return str(value or "").strip()


def validate_and_repair(script: dict, condensed: dict, n_shots: int = 5) -> dict:
    """Coerce raw casting into a valid shot list: fixed beats, host bookends, three distinct
    pundits, grounded non-empty lines, legal durations/shot_types. Repairs in place, never raises."""
    raw_shots = script.get("shots") or []
    by_beat = {}
    for s in raw_shots:
        if isinstance(s, dict) and s.get("beat"):
            by_beat.setdefault(s["beat"], s)  # keep the first shot offered per beat

    shots = []
    for i, beat_def in enumerate(BEATS[:n_shots]):
        beat = beat_def["beat"]
        src = by_beat.get(beat, {}) if isinstance(by_beat.get(beat), dict) else {}
        duration = src.get("duration") if src.get("duration") in VALID_DURATIONS else 6
        shot_type = src.get("shot_type") if src.get("shot_type") in SHOT_GRAMMAR else beat_def["default_shot"]
        line = _clean_str(src.get("line"))
        source = _clean_str(src.get("source"))
        if not line:
            line = _clean_str(_source_text(condensed, beat))
            source = _source_name(beat)
        if not source:
            source = _source_name(beat)
        line = " ".join(line.split()[:_word_cap(duration)])
        performance = _clean_str(src.get("performance")) or "looks directly at the camera"
        speaker = beat_def["speaker"] if beat_def["speaker"] else _clean_str(src.get("speaker"))
        shots.append({"n": i + 1, "beat": beat, "speaker": speaker, "line": line,
                      "source": source, "shot_type": shot_type, "duration": duration,
                      "performance": performance})

    # Beats 2-4 must be three distinct pundits; fill invalid/duplicate slots from PUNDITS in order.
    pundit_idx = [i for i, s in enumerate(shots) if not BEATS[i]["speaker"]]
    used = []
    for i in pundit_idx:
        sp = shots[i]["speaker"]
        if sp in PUNDITS and sp not in used:
            used.append(sp)
        else:
            shots[i]["speaker"] = None  # mark for fill
    leftovers = [p for p in PUNDITS if p not in used]
    for i in pundit_idx:
        if shots[i]["speaker"] is None:
            shots[i]["speaker"] = leftovers.pop(0)

    shots = _repair_dynamism(shots)
    return {"match": script.get("match") or condensed.get("match", ""),
            "reel_title": _clean_str(script.get("reel_title")) or condensed.get("match", ""),
            "shots": shots}


def compose_ltx_prompt(shot: dict) -> str:
    """Render one shot into a single present-tense LTX-2.3 paragraph.
    Focuses on motion + speech (the first-frame portrait already carries the look)."""
    g = SHOT_GRAMMAR[shot["shot_type"]]
    p = BOT_PROFILES[shot["speaker"]]
    return (
        f'{g["framing"]}. '
        f'{STUDIO_LIGHT}. '
        f'{p["identity"]} {shot["performance"]}, speaking directly to camera: "{shot["line"]}". '
        f'Then {g["camera"]}. '
        f'{p["voice"]}, with soft studio room tone underneath.'
    )


def fallback_shot_script(condensed: dict, n_shots: int = 5) -> dict:
    """Deterministic Approach-C reel: map run fields straight onto the beats. No LLM."""
    pundits = iter(PUNDITS)
    raw = []
    for i, beat_def in enumerate(BEATS[:n_shots]):
        beat = beat_def["beat"]
        speaker = beat_def["speaker"] or next(pundits)
        raw.append({
            "n": i + 1, "beat": beat, "speaker": speaker,
            "line": _source_text(condensed, beat), "source": _source_name(beat),
            "shot_type": beat_def["default_shot"], "duration": 6,
            "performance": "looks directly at the camera",
        })
    return validate_and_repair({"match": condensed.get("match", ""), "reel_title": condensed.get("match", ""), "shots": raw},
                               condensed, n_shots=n_shots)


def build_shot_script(run: dict, *, n_shots: int = 5, model: str | None = None) -> dict:
    """Run JSON -> validated, LTX-prompted shot script. One cheap LLM call (with one retry);
    deterministic fallback if the reply is unusable. No video spend."""
    import council_cli
    condensed = condense_run(run)
    model = model or os.getenv("DIRECTOR_MODEL") or run.get("persona_set", {}).get("K_Bot") or DEFAULT_MODEL
    system = "You are the director of a sports talk show. You output only valid JSON objects."
    prompt = build_director_prompt(condensed, n_shots)

    script = None
    for attempt in (1, 2):
        try:
            raw = council_cli.call_llm(system, prompt, temperature=0.6, model=model)
        except Exception as e:
            print(f"  director LLM call failed: {e}")
            break
        parsed = parse_shot_script(raw)
        if parsed:
            script = validate_and_repair(parsed, condensed, n_shots)
            break
        prompt = prompt + "\n\nReturn ONLY the JSON object — no prose, no fences."

    if script is None:
        print("  director: LLM output unusable, using deterministic fallback")
        script = fallback_shot_script(condensed, n_shots)

    for shot in script["shots"]:
        shot["ltx_prompt"] = compose_ltx_prompt(shot)
    return script
