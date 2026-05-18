---
description: Run the Pressly MIN→HOU canonical smoke test. Compare bWAR + arsenal deltas against CLAUDE.md canonical values.
---

The Ryan Pressly MIN→HOU 2018-07-27 trade (`trade_event_id=371509`, player_id=519151) is the V1 validation reference. Run the full smoke test and compare each output against the canonical values from CLAUDE.md. Report **PASS** or **FAIL** per check, then an overall verdict.

Canonical values (CLAUDE.md, "The Pressly canonical case" section):

- **bWAR by season**: T-1 (2017) = -0.04, T@MIN (2018 MIN stint) = 0.73, T@HOU (2018 HOU stint) = 1.34, T+1 (2019) = 1.68, T+2 (2020) = 0.22, T+3 (2021) = 1.87
- **Arsenal percentiles (2017 → 2018)**: fb_spin 97 → 98, curve_spin 100 → 100, K% 65 → 94, whiff% 69 → 95
- **Personnel HOU 2018**: Luhnow (GM/POBO), Hinch (manager), Strom (pitching coach)
- **Personnel MIN 2018**: Falvey (POBO), Levine (GM), Molitor (manager), Alston (pitching coach)

Steps (run in order, stop on data error):

1. **Personnel snapshot** — run `uv run ste analyze personnel 371509`. Confirm HOU and MIN sides match the canonical names above.

2. **bWAR by season + stint** — query the DB:

   ```bash
   uv run python -c "
   from savage_trade_evaluator.storage import db
   with db.connect(read_only=True) as conn:
       print(conn.execute('''
           SELECT season, team_id, war
           FROM bwar_pitching
           WHERE player_id = 519151 AND season BETWEEN 2017 AND 2021
           ORDER BY season, team_id
       ''').fetchdf().to_string(index=False))
   "
   ```

   Compare each row against canonical bWAR values. Tolerance: ±0.05.

3. **Arsenal percentile shift** — query `statcast_pitcher_percentile_ranks` for player_id 519151, years 2017 and 2018. Check fb_spin, curve_spin, K%, whiff% columns. Tolerance: ±2 percentile points.

4. **Verdict** — if all three checks pass, end with `✅ Pressly smoke test PASS`. If any check fails, end with `❌ Pressly smoke test FAIL — <which checks>` and surface the deltas.

Anti-pattern reminder: if the smoke test fails, do not "fix" by adjusting canonical values. The canonical numbers are the ground truth — a failure means the data layer regressed or the query is wrong.
