#!/usr/bin/env python3
"""
Kokoro TTS for AI Football Night reels.

Turn a director `_reel.json` into spoken audio: each shot's `line` is synthesized
in its bot's voice and stitched (in shot order) into one WAV so we can audition the
whole reel before any video spend. Per-shot WAVs are also written — those become the
audio inputs for the LTX lipsync step later.

Setup: pip install "kokoro>=0.9.4" soundfile
       (espeak-ng comes bundled via the espeakng-loader dependency; a system
        `apt-get install espeak-ng` is the fallback if phonemization fails.)
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf
from num2words import num2words

SAMPLE_RATE = 24000  # Kokoro output rate
GAP_SEC = 0.45       # silence inserted between shots when stitching the full reel

# Per-bot Kokoro voice. First letter of the voice id = accent (a=American, b=British),
# second = gender (f/m). Audition G_Bot / R_Bot by ear; bf_emma + bm_george are safe.
VOICE_BY_BOT = {
    "K_Bot":    "bf_emma",    # warm, confident British female host
    "Stat_Bot": "bm_george",  # precise, measured British male
    "G_Bot":    "am_puck",    # animated, lively American male
    "R_Bot":    "am_fenrir",  # higher-grade male (am_onyx was C/D — most synthetic)
}
DEFAULT_VOICE = "af_heart"

# Spoken-form fixes: numbers, percentages, ratios and football shorthand otherwise read
# as digit-by-digit garble ("zero point two G A per game"), a big part of the robotic feel.
# Expand them into words before synthesis.
_ABBREV = [
    (r"\bvs\.?\b", "versus"),
    (r"\bGA/game\b", "goals against per game"),
    (r"\bGA\b", "goals against"),
    (r"\bxG\b", "expected goals"),
    (r"\bPPDA\b", "passes per defensive action"),
    (r"/game\b", " per game"),
    (r"%", " percent"),
]


def _spell_digit_groups(match):
    return " ".join(num2words(int(p)) for p in match.group(0).split("-"))


def normalize_for_speech(text: str) -> str:
    """Rewrite numbers/percentages/formations/abbreviations into spoken words."""
    s = text
    for pat, repl in _ABBREV:
        s = re.sub(pat, repl, s)
    s = re.sub(r"\b\d+(?:-\d+)+\b", _spell_digit_groups, s)                  # 4-2-3-1, 2-1
    s = re.sub(r"\b\d+\.\d+\b", lambda m: num2words(float(m.group(0))), s)   # 73.8, 0.2
    s = re.sub(r"\b\d+\b", lambda m: num2words(int(m.group(0))), s)          # plain ints
    return re.sub(r"\s{2,}", " ", s).strip()


_PIPELINES = {}


def _pipeline(lang_code):
    """Lazily build + cache a KPipeline per accent ('a' American, 'b' British)."""
    from kokoro import KPipeline
    if lang_code not in _PIPELINES:
        _PIPELINES[lang_code] = KPipeline(lang_code=lang_code)
    return _PIPELINES[lang_code]


def synth_line(text, voice=DEFAULT_VOICE, speed=1.0):
    """Synthesize one line into a float32 mono numpy array at 24 kHz."""
    text = normalize_for_speech(text)
    pipe = _pipeline(voice[0])
    chunks = []
    for _, _, audio in pipe(text, voice=voice, speed=speed):
        a = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
        chunks.append(a.astype(np.float32))
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def synth_reel(reel, out_wav, clips_dir=None, speed=1.0):
    """Synthesize every shot line in its bot voice, stitch into one WAV (shot order)."""
    gap = np.zeros(int(GAP_SEC * SAMPLE_RATE), dtype=np.float32)
    parts = []
    for shot in reel["shots"]:
        voice = VOICE_BY_BOT.get(shot["speaker"], DEFAULT_VOICE)
        audio = synth_line(shot["line"], voice=voice, speed=speed)
        print(f"  [{shot['n']}] {shot['speaker']:<9} {voice:<9} {len(audio)/SAMPLE_RATE:4.1f}s  {shot['line'][:50]}")
        if clips_dir:
            Path(clips_dir).mkdir(parents=True, exist_ok=True)
            sf.write(Path(clips_dir) / f"shot{shot['n']}_{shot['speaker']}.wav", audio, SAMPLE_RATE)
        if parts:
            parts.append(gap)
        parts.append(audio)
    stitched = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    sf.write(out_wav, stitched, SAMPLE_RATE)
    print(f"\nStitched {len(reel['shots'])} shots -> {out_wav}  ({len(stitched)/SAMPLE_RATE:.1f}s total)")
    return out_wav


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kokoro TTS for a director _reel.json")
    ap.add_argument("reel_path", help="path to a _reel.json")
    ap.add_argument("--out", default=None, help="stitched WAV (default: <reel>_voiced.wav)")
    ap.add_argument("--clips-dir", default=None, help="also write per-shot WAVs here")
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args(argv)

    reel = json.loads(Path(args.reel_path).read_text())
    out_wav = args.out or str(Path(args.reel_path).with_name(Path(args.reel_path).stem + "_voiced.wav"))
    print(f"Voicing {len(reel['shots'])} shots from {args.reel_path}")
    synth_reel(reel, out_wav, clips_dir=args.clips_dir, speed=args.speed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
