#!/usr/bin/env python3
"""L0 before/after evaluation.

Quantifies whether grounding + reasoning changed the output, comparing the
pre-L0 baseline (the degraded, always-2-1 runs) against a new post-L0 run over
a fresh slate.

  BASELINE = runs/2026-06-11 + runs/2026-06-12  (committed, pre-L0)
  NEW      = the dir passed as argv[1] (default runs/2026-06-13), produced by
             running the next matchday through the new pipeline AFTER approval.

Metrics (all read-only, no API calls):
  - prediction diversity: distinct scorelines across pundits (baseline clustered at 2-1)
  - grounding: research_quality distribution (baseline was degraded/partial)
  - fabrication proxy: matches where Stat_Bot's text cites xG/PPDA (none exists in data)
  - cost: tokens + calls per slate, from the `cost` block run_matchday now writes
"""
import json
import glob
import sys
from collections import Counter


def load(globpats):
    out = {}
    for pat in globpats:
        for f in glob.glob(pat):
            if f.endswith(("_context.json", "_thread.json", "_reasoning.json")):
                continue
            try:
                out[f] = json.load(open(f))
            except Exception:
                pass
    return out


def _stat_bot_text(d):
    """All of Stat_Bot's debate text, across rounds (lives under full_debate)."""
    fd = d.get("full_debate") or {}
    parts = []
    for section in ("proposals", "cross_critiques", "rebuttals"):
        parts.append((fd.get(section) or {}).get("Stat_Bot") or "")
    return " ".join(parts).lower()


def _research_quality(path):
    """research_quality lives in the sibling *_context.json, not the run JSON."""
    ctx_path = path.replace(".json", "_context.json")
    try:
        return json.load(open(ctx_path)).get("research_quality", "unknown")
    except Exception:
        return "unknown"


def metrics(runs, label):
    scorelines, qualities = Counter(), Counter()
    fabrication, cost_in, cost_out, calls, n = 0, 0, 0, 0, 0
    for path, d in runs.items():
        n += 1
        for pred in (d.get("pundit_predictions") or {}).values():
            scorelines[f"{pred['home_goals']}-{pred['away_goals']}"] += 1
        qualities[_research_quality(path)] += 1
        stat_text = _stat_bot_text(d)
        if "xg" in stat_text or "ppda" in stat_text:
            fabrication += 1
        c = d.get("cost") or {}
        cost_in += c.get("prompt_tokens", 0)
        cost_out += c.get("completion_tokens", 0)
        calls += c.get("calls", 0)
    print(f"\n=== {label} ({n} matches) ===")
    print(f"  scoreline distribution : {dict(scorelines)}")
    print(f"  DISTINCT scorelines    : {len(scorelines)}   (higher = less monoculture)")
    print(f"  research_quality       : {dict(qualities)}")
    print(f"  Stat_Bot cited xG/PPDA : {fabrication}/{n} matches   (fabrication proxy; target 0)")
    if calls:
        print(f"  tokens in/out, calls   : {cost_in}/{cost_out}, {calls}")


if __name__ == "__main__":
    new_dir = sys.argv[1] if len(sys.argv) > 1 else "runs/2026-06-13"
    base = load(["runs/2026-06-11/wc_*.json", "runs/2026-06-12/wc_*.json"])
    new = load([f"{new_dir}/wc_*.json"])
    metrics(base, "BASELINE (pre-L0)")
    if new:
        metrics(new, f"NEW (post-L0: {new_dir})")
    else:
        print(f"\n(no NEW runs found in {new_dir} yet — run the slate through the "
              f"new pipeline first, then re-run this script.)")
