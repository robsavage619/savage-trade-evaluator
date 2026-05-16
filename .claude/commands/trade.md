---
description: Show the full V1 picture of one trade event — structure, WAR window, arsenal jumps, both-sides personnel.
argument-hint: <trade_event_id>
---

Walk through the trade with id `$ARGUMENTS` using the V1 data layer. Run these commands in order and report each block:

1. **Structure** — the legs and players moving.
   ```bash
   uv run python -c "
   from savage_trade_evaluator.storage import db
   with db.connect(read_only=True) as conn:
       rows = conn.execute('''
           SELECT leg_index, date, player_name, from_team_bref, to_team_bref, description
           FROM trade_player_unified
           WHERE trade_event_id = $ARGUMENTS
           ORDER BY leg_index
       ''').fetchall()
       for r in rows:
           print(r)
   "
   ```

2. **WAR window** per player (T-1 / T / T@rcv / T+1 / T+2 / T+3).
   ```bash
   uv run python -c "
   from savage_trade_evaluator.storage import db
   with db.connect(read_only=True) as conn:
       rows = conn.execute('''
           SELECT player_name, war_t_minus_1, war_t_total, war_t_with_receiver,
                  war_t_plus_1, war_t_plus_2, war_t_plus_3
           FROM trade_player_war_window
           WHERE trade_event_id = $ARGUMENTS
           ORDER BY leg_index
       ''').fetchall()
       for r in rows:
           print(r)
   "
   ```

3. **Arsenal jumps** (pitchers only; Statcast era only).
   ```bash
   uv run python -c "
   from savage_trade_evaluator.storage import db
   with db.connect(read_only=True) as conn:
       rows = conn.execute('''
           SELECT player_name,
                  fb_velocity_t_minus_1, fb_velocity_t_plus_1,
                  fb_spin_t_minus_1, fb_spin_t_plus_1,
                  k_percent_t_minus_1, k_percent_t_plus_1,
                  whiff_percent_t_minus_1, whiff_percent_t_plus_1
           FROM trade_player_arsenal_window
           WHERE trade_event_id = $ARGUMENTS
       ''').fetchall()
       for r in rows:
           print(r)
   "
   ```

4. **Personnel** snapshot for both sides.
   ```bash
   uv run ste analyze personnel $ARGUMENTS
   ```

If the trade is the Pressly case (`371509`), call out the MVP Machine Ch 9 thesis ("stuff didn't change; pitch usage did — Strom's intake meeting") explicitly.

Report concise — one block per section, with a one-line interpretation at the end summarizing whether the trade looks like a clear win/loss for either side based on the windows.
