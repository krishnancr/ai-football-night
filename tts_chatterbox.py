#!/usr/bin/env python3
"""
Chatterbox TTS for AI Football Night reels — natural, expressive alternative to Kokoro.

MUST run with the isolated venv (chatterbox lives there, not in global site-packages):
    .venv-tts/bin/python tts_chatterbox.py runs/<date>/<slug>_reel.json

Each bot maps to a zero-shot voice-clone reference WAV; bots without one use
Chatterbox's default voice. Reuses the spoken-form normalization from tts_kokoro.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from tts_kokoro import normalize_for_speech

GAP_SEC = 0.45  # silence between shots when stitching

# Per-bot zero-shot clone reference (a short, clean WAV of the target voice).
# K_Bot reuses the Veo-generated sample we already have. Add references for the
# others to give each a distinct natural voice; None -> Chatterbox default voice.
VOICE_REF_BY_BOT = {
    "K_Bot":    "assets/bots/kbot_line_5s.wav",
    "Stat_Bot": None,
    "G_Bot":    None,
    "R_Bot":    None,
}
# Per-bot expressiveness (Chatterbox `exaggeration` knob; neutral = 0.5).
EXAGGERATION_BY_BOT = {"K_Bot": 0.5, "Stat_Bot": 0.4, "G_Bot": 0.7, "R_Bot": 0.6}

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from chatterbox.tts import ChatterboxTTS
        _MODEL = ChatterboxTTS.from_pretrained(device="cuda")
    return _MODEL


def synth_line(text, ref_wav=None, exaggeration=0.5, cfg_weight=0.5):
    """Synthesize one line -> (float32 mono numpy, sample_rate)."""
    m = _model()
    kw = {"exaggeration": exaggeration, "cfg_weight": cfg_weight}
    if ref_wav:
        kw["audio_prompt_path"] = ref_wav
    wav = m.generate(normalize_for_speech(text), **kw)
    a = wav.detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav)
    return np.squeeze(a).astype(np.float32), m.sr


def synth_reel(reel, out_wav, clips_dir=None):
    parts, sr = [], None
    for shot in reel["shots"]:
        ref = VOICE_REF_BY_BOT.get(shot["speaker"])
        exag = EXAGGERATION_BY_BOT.get(shot["speaker"], 0.5)
        audio, sr = synth_line(shot["line"], ref_wav=ref, exaggeration=exag)
        refname = "default" if not ref else Path(ref).name
        print(f"  [{shot['n']}] {shot['speaker']:<9} {refname:<18} {len(audio)/sr:4.1f}s  {shot['line'][:42]}")
        if clips_dir:
            Path(clips_dir).mkdir(parents=True, exist_ok=True)
            sf.write(Path(clips_dir) / f"shot{shot['n']}_{shot['speaker']}.wav", audio, sr)
        if parts:
            parts.append(np.zeros(int(GAP_SEC * sr), dtype=np.float32))
        parts.append(audio)
    stitched = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    sf.write(out_wav, stitched, sr)
    print(f"\nStitched {len(reel['shots'])} shots -> {out_wav}  ({len(stitched)/sr:.1f}s @ {sr}Hz)")
    return out_wav


def main(argv=None):
    ap = argparse.ArgumentParser(description="Chatterbox TTS for a director _reel.json")
    ap.add_argument("reel_path")
    ap.add_argument("--out", default=None)
    ap.add_argument("--clips-dir", default=None)
    args = ap.parse_args(argv)
    reel = json.loads(Path(args.reel_path).read_text())
    out_wav = args.out or str(Path(args.reel_path).with_name(Path(args.reel_path).stem + "_chatterbox.wav"))
    print(f"Voicing {len(reel['shots'])} shots (Chatterbox) from {args.reel_path}")
    synth_reel(reel, out_wav, clips_dir=args.clips_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
