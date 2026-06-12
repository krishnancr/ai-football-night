# scripts/backfill_base_stats.py
"""One-time: add a team-strength `stats_home`/`stats_away` block to every
runs/base/*.json. Team-strength data ONLY (FIFA rank, World Football Elo,
qualifying record) — pre-match xG does not exist. Edit TEAM_STATS below with
real values from fifa.com/fifa-world-ranking and eloratings.net, then run.
Idempotent: re-running overwrites the two stats blocks, nothing else.
"""
import json
import sys
from pathlib import Path

# allow running as `python3 scripts/backfill_base_stats.py` from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import teams

# canonical FIFA name -> strength stats. FIFA ranking (11 Jun 2026) + World Football
# Elo (eloratings.net, 12 Jun 2026) + 2026 WC qualifying record. Hosts (USA/Canada/
# Mexico) qualified automatically → qual=None. A few qual GF/GA are null where the
# source could not be confirmed (Qatar); a few are primary-group-stage-only (see notes
# in the original research). Good enough as grounding fuel; refine later if needed.
TEAM_STATS = {
    "Algeria": {"fifa_rank": 28, "elo": 1571, "qual": {"P": 10, "W": 8, "D": 1, "L": 1, "GF": 24, "GA": 8}},
    "Argentina": {"fifa_rank": 1, "elo": 1877, "qual": {"P": 18, "W": 12, "D": 2, "L": 4, "GF": 31, "GA": 10}},
    "Australia": {"fifa_rank": 27, "elo": 1579, "qual": {"P": 10, "W": 5, "D": 4, "L": 1, "GF": 16, "GA": 7}},
    "Austria": {"fifa_rank": 24, "elo": 1597, "qual": {"P": 8, "W": 6, "D": 1, "L": 1, "GF": 22, "GA": 4}},
    "Belgium": {"fifa_rank": 9, "elo": 1742, "qual": {"P": 8, "W": 5, "D": 3, "L": 0, "GF": 29, "GA": 7}},
    "Bosnia and Herzegovina": {"fifa_rank": 64, "elo": 1387, "qual": {"P": 8, "W": 5, "D": 2, "L": 1, "GF": 17, "GA": 7}},
    "Brazil": {"fifa_rank": 6, "elo": 1766, "qual": {"P": 18, "W": 8, "D": 4, "L": 6, "GF": 24, "GA": 17}},
    "Cabo Verde": {"fifa_rank": 67, "elo": 1371, "qual": {"P": 10, "W": 7, "D": 2, "L": 1, "GF": 16, "GA": 8}},
    "Canada": {"fifa_rank": 30, "elo": 1559, "qual": None},
    "Colombia": {"fifa_rank": 13, "elo": 1698, "qual": {"P": 18, "W": 7, "D": 7, "L": 4, "GF": 28, "GA": 18}},
    "Croatia": {"fifa_rank": 11, "elo": 1715, "qual": {"P": 8, "W": 7, "D": 1, "L": 0, "GF": 26, "GA": 4}},
    "Curaçao": {"fifa_rank": 82, "elo": 1295, "qual": {"P": 6, "W": 3, "D": 3, "L": 0, "GF": 13, "GA": 3}},
    "Czechia": {"fifa_rank": 40, "elo": 1506, "qual": {"P": 8, "W": 5, "D": 1, "L": 2, "GF": 18, "GA": 8}},
    "DR Congo": {"fifa_rank": 46, "elo": 1474, "qual": {"P": 10, "W": 7, "D": 1, "L": 2, "GF": 15, "GA": 6}},
    "Ecuador": {"fifa_rank": 23, "elo": 1599, "qual": {"P": 18, "W": 8, "D": 8, "L": 2, "GF": 14, "GA": 5}},
    "Egypt": {"fifa_rank": 29, "elo": 1562, "qual": {"P": 10, "W": 8, "D": 2, "L": 0, "GF": 20, "GA": 2}},
    "England": {"fifa_rank": 4, "elo": 1828, "qual": {"P": 8, "W": 8, "D": 0, "L": 0, "GF": 22, "GA": 0}},
    "France": {"fifa_rank": 3, "elo": 1871, "qual": {"P": 6, "W": 5, "D": 1, "L": 0, "GF": 16, "GA": 4}},
    "Germany": {"fifa_rank": 10, "elo": 1736, "qual": {"P": 6, "W": 5, "D": 0, "L": 1, "GF": 16, "GA": 3}},
    "Ghana": {"fifa_rank": 73, "elo": 1347, "qual": {"P": 10, "W": 8, "D": 1, "L": 1, "GF": 23, "GA": 6}},
    "Haiti": {"fifa_rank": 83, "elo": 1293, "qual": {"P": 6, "W": 3, "D": 2, "L": 1, "GF": 9, "GA": 6}},
    "Iran": {"fifa_rank": 20, "elo": 1620, "qual": {"P": 10, "W": 7, "D": 2, "L": 1, "GF": 19, "GA": 8}},
    "Iraq": {"fifa_rank": 57, "elo": 1446, "qual": {"P": 10, "W": 4, "D": 3, "L": 3, "GF": 9, "GA": 9}},
    "Ivory Coast": {"fifa_rank": 33, "elo": 1541, "qual": {"P": 10, "W": 8, "D": 2, "L": 0, "GF": 25, "GA": 0}},
    "Japan": {"fifa_rank": 18, "elo": 1662, "qual": {"P": 10, "W": 7, "D": 2, "L": 1, "GF": 30, "GA": 3}},
    "Jordan": {"fifa_rank": 63, "elo": 1388, "qual": {"P": 10, "W": 4, "D": 4, "L": 2, "GF": 16, "GA": 8}},
    "Korea Republic": {"fifa_rank": 25, "elo": 1592, "qual": {"P": 10, "W": 6, "D": 4, "L": 0, "GF": 20, "GA": 7}},
    "Mexico": {"fifa_rank": 14, "elo": 1687, "qual": None},
    "Morocco": {"fifa_rank": 7, "elo": 1755, "qual": {"P": 8, "W": 8, "D": 0, "L": 0, "GF": 22, "GA": 2}},
    "Netherlands": {"fifa_rank": 8, "elo": 1754, "qual": {"P": 8, "W": 6, "D": 2, "L": 0, "GF": 27, "GA": 4}},
    "New Zealand": {"fifa_rank": 85, "elo": 1276, "qual": {"P": 5, "W": 5, "D": 0, "L": 0, "GF": 29, "GA": 1}},
    "Norway": {"fifa_rank": 31, "elo": 1557, "qual": {"P": 8, "W": 8, "D": 0, "L": 0, "GF": 37, "GA": 5}},
    "Panama": {"fifa_rank": 34, "elo": 1539, "qual": {"P": 6, "W": 3, "D": 3, "L": 0, "GF": 9, "GA": 4}},
    "Paraguay": {"fifa_rank": 41, "elo": 1505, "qual": {"P": 18, "W": 7, "D": 7, "L": 4, "GF": 14, "GA": 10}},
    "Portugal": {"fifa_rank": 5, "elo": 1768, "qual": {"P": 6, "W": 4, "D": 1, "L": 1, "GF": 20, "GA": 7}},
    "Qatar": {"fifa_rank": 56, "elo": 1450, "qual": {"P": 12, "W": 5, "D": 2, "L": 5, "GF": None, "GA": None}},
    "Saudi Arabia": {"fifa_rank": 61, "elo": 1424, "qual": {"P": 12, "W": 4, "D": 5, "L": 3, "GF": 10, "GA": 10}},
    "Scotland": {"fifa_rank": 42, "elo": 1503, "qual": {"P": 6, "W": 4, "D": 1, "L": 1, "GF": 13, "GA": 7}},
    "Senegal": {"fifa_rank": 15, "elo": 1684, "qual": {"P": 10, "W": 7, "D": 3, "L": 0, "GF": 22, "GA": 3}},
    "South Africa": {"fifa_rank": 60, "elo": 1428, "qual": {"P": 10, "W": 5, "D": 3, "L": 2, "GF": 15, "GA": 9}},
    "Spain": {"fifa_rank": 2, "elo": 1875, "qual": {"P": 6, "W": 5, "D": 1, "L": 0, "GF": 21, "GA": 2}},
    "Sweden": {"fifa_rank": 38, "elo": 1510, "qual": {"P": 8, "W": 2, "D": 2, "L": 4, "GF": 10, "GA": 15}},
    "Switzerland": {"fifa_rank": 19, "elo": 1650, "qual": {"P": 6, "W": 4, "D": 2, "L": 0, "GF": 14, "GA": 2}},
    "Tunisia": {"fifa_rank": 45, "elo": 1476, "qual": {"P": 10, "W": 9, "D": 1, "L": 0, "GF": 22, "GA": 0}},
    "Türkiye": {"fifa_rank": 22, "elo": 1606, "qual": {"P": 6, "W": 4, "D": 1, "L": 1, "GF": 17, "GA": 12}},
    "United States": {"fifa_rank": 17, "elo": 1671, "qual": None},
    "Uruguay": {"fifa_rank": 16, "elo": 1673, "qual": {"P": 18, "W": 7, "D": 7, "L": 4, "GF": 22, "GA": 12}},
    "Uzbekistan": {"fifa_rank": 50, "elo": 1459, "qual": {"P": 10, "W": 6, "D": 3, "L": 1, "GF": 14, "GA": 7}},
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
