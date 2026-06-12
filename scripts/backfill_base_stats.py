# scripts/backfill_base_stats.py
"""One-time: add a team-strength `stats_home`/`stats_away` block to every
runs/base/*.json. Team-strength data ONLY (FIFA rank, World Football Elo,
qualifying record) — pre-match xG does not exist. Edit TEAM_STATS below with
real values from fifa.com/fifa-world-ranking and eloratings.net, then run.
Idempotent: re-running overwrites the two stats blocks, nothing else.
"""
import json
from pathlib import Path
import teams

# canonical FIFA name -> strength stats. Fill from FIFA ranking + eloratings.net.
# TODO(human): populate all 48 World Cup 2026 teams before running.
TEAM_STATS = {
    # "Korea Republic": {"fifa_rank": 23, "elo": 1789, "qual": {"P": 10, "W": 7, "D": 2, "L": 1, "GF": 22, "GA": 8}},
}

def main():
    base_dir = Path("runs/base")
    files = sorted(base_dir.glob("wc_*_base.json"))
    patched, missing = 0, set()
    for f in files:
        data = json.loads(f.read_text())
        for side in ("home_team", "away_team"):
            name = teams.canonical(data.get(side, ""))
            key = "stats_home" if side == "home_team" else "stats_away"
            if name in TEAM_STATS:
                data[key] = TEAM_STATS[name]
            else:
                missing.add(name)
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        patched += 1
    print(f"Patched {patched} base files.")
    if missing:
        print(f"⚠️  No stats for {len(missing)} teams: {sorted(missing)}")

if __name__ == "__main__":
    main()
