#!/usr/bin/env python3
"""
3-shot reel bake-off harness — WaveSpeedAI.

Pulls one short example of each shot-type through the model picked for its
strength, so we can eyeball whether the multi-model approach is "natural enough"
before building any director routing. Throwaway spike, not wired into CI.

Shots (all on the WAVESPEED_API_KEY, one poll/download pattern):
  1. close   -> Kling V2 AI Avatar Standard  (kwaivgi/kling-v2-ai-avatar-standard)
                still portrait + audio -> talking close-up. ~$0.28/run (5s min).
  2. two     -> InfiniteTalk Multi          (wavespeed-ai/infinitetalk/multi)
                2-person still + left/right audio + speaking order. ~$0.15/5s @480p.
  3. wide    -> Seedance 2.0 image-to-video (bytedance/seedance-2.0/image-to-video)
                wide panel still + motion prompt, NO lipsync. $0.60/5s @480p.

SAFETY / COST (same contract as scripts/wavespeed_spike.py):
  - default  : DRY RUN. Prints each request body + cost estimate, no submit, $0 spent.
  - --yes    : actually submit (spends). Aborts if total estimate > --max-cost.

INPUTS MUST BE PUBLIC HTTPS URLs (WaveSpeed fetches them) — no local paths,
no base64. Push the test assets to the branch and pass --base-url, e.g.
  https://raw.githubusercontent.com/<user>/<repo>/<branch>
so that <base-url>/assets/bots/kbot.png etc. resolve. Override any single input
with the per-shot --*-url flags.

Docs: https://wavespeed.ai/docs/rest-api
"""
import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.wavespeed.ai/api/v3"

# Per-shot model + cost floor. Costs are the cheap-settings estimate used for the
# --max-cost gate; actual charge scales with length/resolution (see WaveSpeed).
SHOTS = {
    "close": {
        "model": "kwaivgi/kling-v2-ai-avatar-standard",
        "est": 0.28,  # 5s minimum charge
        "desc": "Kling AI Avatar close-up (portrait + audio)",
    },
    "two": {
        "model": "wavespeed-ai/infinitetalk/multi",
        "est": 0.30,  # ~10s @480p ($0.15/5s)
        "desc": "InfiniteTalk Multi two-shot (2-person + L/R audio, turn-taking)",
    },
    "wide": {
        "model": "bytedance/seedance-2.0/image-to-video",
        "est": 0.60,  # 5s @480p, no audio
        "desc": "Seedance i2v establishing wide (motion only, no lipsync)",
    },
}


def _key() -> str:
    key = os.getenv("WAVESPEED_API_KEY")
    if not key:
        sys.exit("ERROR: WAVESPEED_API_KEY not in env/.env")
    return key


def _req(method, url, key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, {"_raw": txt}


def build_body(shot, a):
    """Return the WaveSpeed request body for one shot (per the model's schema)."""
    if shot == "close":
        # Tuned per Kling AI Avatar prompt guide: 1-3 sentences; subject + expression
        # + movement + style preservation; SUBTLE for realistic portraits; let the
        # audio drive emotion (prompt matches tone, doesn't fight it).
        return {
            "image": a.close_image_url,
            "audio": a.close_audio_url,
            "prompt": "Confident female football pundit on a TV broadcast set, "
                      "delivering match analysis directly to camera. Subtle, natural "
                      "micro-expressions and controlled head movements that follow the "
                      "tone and rhythm of her speech, with steady eye contact toward the "
                      "viewer. Preserve photorealistic skin texture and natural eye "
                      "movement; keep any gestures minimal and believable.",
        }
    if shot == "two":
        # Tuned per InfiniteTalk/MultiTalk guide: prompt is a HIGH-LEVEL steer
        # (scene, interaction, listener reaction) — audio drives lips/expression.
        # Keep it concrete (place + lighting) and short (~2 sentences).
        return {
            "image": a.two_image_url,
            "left_audio": a.two_left_audio_url,
            "right_audio": a.two_right_audio_url,
            "order": a.order,
            "resolution": a.resolution,
            "prompt": "Two football pundits side by side at a broadcast desk in a "
                      "bright TV studio; the left presenter speaks while the right one "
                      "listens and nods, then they swap as the right presenter "
                      "responds. Calm, natural head movements and cinematic broadcast "
                      "lighting.",
        }
    if shot == "wide":
        return {
            "image": a.wide_image_url,
            "prompt": "Wide static shot of a sports TV studio panel of four "
                      "presenters seated at a desk. Subtle natural motion: slow "
                      "camera push-in, presenters breathe and make small idle "
                      "movements, background screens and stadium crowd flicker "
                      "softly. No one speaks. Cinematic broadcast lighting.",
            "duration": 5,
            "aspect_ratio": "16:9",
            "resolution": a.resolution,
            "generate_audio": False,
        }
    raise ValueError(shot)


def _ffprobe_dur(path, stream):
    """Duration (s) of the first audio/video stream, or 0.0 if absent/unreadable."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", stream,
             "-show_entries", "stream=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True).stdout.strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0


def trim_to_audio(raw_path, final_path):
    """Trim trailing video that runs past the audio. Audio-driven avatar models pad
    the tail with degraded idle motion (the 'melty hand' artifact). No audio stream
    or no overrun -> just move the file. Returns trimmed seconds, or None."""
    adur = _ffprobe_dur(raw_path, "a:0")
    vdur = _ffprobe_dur(raw_path, "v:0")
    if adur <= 0 or vdur <= adur + 0.15:
        os.replace(raw_path, final_path)
        return None
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", raw_path, "-t", f"{adur:.3f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", final_path],
        check=True)
    os.remove(raw_path)
    return round(vdur - adur, 2)


def run_shot(shot, body, key, out_dir, poll_secs, max_polls):
    model = SHOTS[shot]["model"]
    status, sub = _req("POST", f"{BASE}/{model}", key, body=body)
    if status not in (200, 201) or "data" not in sub:
        print(f"  SUBMIT FAILED ({status}): {json.dumps(sub)[:400]}")
        return None
    job = sub["data"]
    job_id = job.get("id")
    poll_url = job.get("urls", {}).get("get") or f"{BASE}/predictions/{job_id}/result"
    print(f"  job id: {job_id}  (Kling avatar can take ~15-20 min)")
    for i in range(max_polls):
        time.sleep(poll_secs)
        _, st = _req("GET", poll_url, key)
        data = st.get("data", st)
        sv = data.get("status")
        print(f"    [{i+1}/{max_polls}] status={sv}")
        if sv in ("completed", "succeeded"):
            outs = data.get("outputs") or []
            if not outs:
                print("    completed but no outputs:", json.dumps(data)[:300])
                return None
            raw_path = out_dir / f"{shot}_raw.mp4"
            raw_path.write_bytes(urllib.request.urlopen(outs[0]).read())
            out_path = out_dir / f"{shot}.mp4"
            trimmed = trim_to_audio(str(raw_path), str(out_path))
            msg = f"    saved {out_path} ({out_path.stat().st_size} bytes)"
            if trimmed:
                msg += f"  [trimmed {trimmed}s silent tail to match audio]"
            print(msg)
            return job_id
        if sv in ("failed", "error"):
            print(f"    generation {sv}: {json.dumps(data)[:400]}")
            return None
    print(f"    timed out after {max_polls} polls")
    return None


def main():
    ap = argparse.ArgumentParser(description="3-shot reel bake-off (WaveSpeed)")
    ap.add_argument("--base-url", default=os.getenv("ASSET_BASE_URL", ""),
                    help="public prefix for assets, e.g. raw.githubusercontent.com/<u>/<r>/<branch>")
    # per-input overrides (default to <base-url>/<repo-path>)
    ap.add_argument("--close-image-url", default=None)
    ap.add_argument("--close-audio-url", default=None)
    ap.add_argument("--two-image-url", default=None)
    ap.add_argument("--two-left-audio-url", default=None)
    ap.add_argument("--two-right-audio-url", default=None)
    ap.add_argument("--wide-image-url", default=None)
    ap.add_argument("--order", default="left to right",
                    choices=["left to right", "right to left", "meanwhile"])
    ap.add_argument("--resolution", default="480p", choices=["480p", "720p", "1080p"])
    ap.add_argument("--shots", default="close,two,wide",
                    help="comma list of shots to run (close,two,wide)")
    ap.add_argument("--max-cost", type=float, default=2.00, help="abort if total estimate exceeds this")
    ap.add_argument("--out-dir", default=None, help="default runs/<utc-date>/bakeoff/")
    ap.add_argument("--poll-secs", type=int, default=15)
    ap.add_argument("--max-polls", type=int, default=120)  # up to ~30 min (Kling avatar is slow)
    ap.add_argument("--yes", action="store_true", help="REQUIRED to actually submit (spends)")
    a = ap.parse_args()

    def asset(path, override):
        if override:
            return override
        if not a.base_url:
            return f"<SET --base-url>/{path}"
        return f"{a.base_url.rstrip('/')}/{path}"

    # default input URLs (repo-relative paths)
    a.close_image_url = asset("assets/bots/kbot_closeup.png", a.close_image_url)
    a.close_audio_url = asset("assets/bots/kbot_line_5s.wav", a.close_audio_url)
    a.two_image_url = asset("assets/twoshot_left2.png", a.two_image_url)
    a.two_left_audio_url = asset("assets/bots/kbot_line_5s.wav", a.two_left_audio_url)
    a.two_right_audio_url = asset("assets/twoshot_right_line.wav", a.two_right_audio_url)
    a.wide_image_url = asset("assets/AIPanel.png", a.wide_image_url)

    shots = [s.strip() for s in a.shots.split(",") if s.strip()]
    total = sum(SHOTS[s]["est"] for s in shots)

    print("=== 3-shot reel bake-off (WaveSpeed) ===")
    for s in shots:
        print(f"\n[{s}] {SHOTS[s]['desc']}")
        print(f"  model: {SHOTS[s]['model']}   est: ~${SHOTS[s]['est']}")
        print("  body : " + json.dumps(build_body(s, a)))
    print(f"\nTotal estimate : ~${round(total, 2)}   (--max-cost ${a.max_cost})")

    missing = [s for s in shots if "<SET --base-url>" in json.dumps(build_body(s, a))]
    if missing:
        print(f"\n  NOTE: inputs for {missing} have no public URL yet — set --base-url "
              "(push assets) or pass --*-url overrides before running with --yes.")

    if total > a.max_cost:
        sys.exit(f"\nABORT: estimate ${round(total,2)} exceeds --max-cost ${a.max_cost}")

    if not a.yes:
        print("\nDRY RUN (no --yes): no submit, nothing spent. Re-run with --yes to generate.")
        return
    if missing:
        sys.exit("\nABORT: refusing to spend with unresolved input URLs (see NOTE above).")

    key = _key()
    out_dir = (Path(a.out_dir) if a.out_dir
               else Path("runs") / datetime.now(timezone.utc).strftime("%Y-%m-%d") / "bakeoff")
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = Path("runs") / "_spend_ledger.jsonl"
    for s in shots:
        print(f"\n[{s}] submitting...")
        job_id = run_shot(s, build_body(s, a), key, out_dir, a.poll_secs, a.max_polls)
        if job_id:
            with ledger.open("a") as f:
                f.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "label": f"reel_3shot:{s}", "model": SHOTS[s]["model"],
                    "est_cost": SHOTS[s]["est"], "job_id": job_id,
                }) + "\n")
    print(f"\nDone. Clips in {out_dir}/  (close.mp4 / two.mp4 / wide.mp4)")


if __name__ == "__main__":
    main()
