# AI Football Night

Four AI pundits debate every WC 2026 match daily via GitHub Actions (7am UTC) and publish predictions, banter, and a track-record leaderboard to GitHub Pages.

Key constraint: X/Twitter auto-posting is **deliberately disabled** (X API write tier costs money). CI generates post packs in `runs/`; posting is manual. Do not re-wire `distribute.py` into CI without asking.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
