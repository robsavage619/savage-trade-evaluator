"""R-63: why are 43% of holdout trade sides exactly zero on war_delta?

Buckets every 2018-2021 trade leg by the reason its T+2..T+5 window WAR is or is
not zero, then shows how much post-trade WAR was earned for the receiving club
versus elsewhere. Read-only.

Run:
  uv run python scripts/r63_zero_outcome_audit.py
"""

from __future__ import annotations

from savage_trade_evaluator.storage import db

_LEGS = """
    SELECT t.trade_event_id, t.leg_index, t.mlb_player_id, t.trade_season, t.to_team_bref,
           w.war_t_plus_2, w.war_t_plus_3, w.war_t_plus_4, w.war_t_plus_5,
           (SELECT MIN(year_id) FROM bwar_player_seasons b WHERE b.mlb_id = t.mlb_player_id)
               AS first_bwar,
           (SELECT MAX(year_id) FROM bwar_player_seasons b WHERE b.mlb_id = t.mlb_player_id)
               AS last_bwar
    FROM trade_player_unified t
    LEFT JOIN trade_player_war_window w USING (trade_event_id, leg_index)
    WHERE t.to_team_bref IS NOT NULL AND t.trade_season BETWEEN 2018 AND 2021
"""

_BUCKETS = f"""
WITH legs AS ({_LEGS})
SELECT CASE
    WHEN mlb_player_id IS NULL THEN '0 no player id'
    WHEN COALESCE(war_t_plus_2, war_t_plus_3, war_t_plus_4, war_t_plus_5) IS NOT NULL
         AND COALESCE(war_t_plus_2, 0) + COALESCE(war_t_plus_3, 0)
           + COALESCE(war_t_plus_4, 0) + COALESCE(war_t_plus_5, 0) <> 0
        THEN '1 nonzero WAR in window'
    WHEN COALESCE(war_t_plus_2, war_t_plus_3, war_t_plus_4, war_t_plus_5) IS NOT NULL
        THEN '2 played in window, WAR sums to 0'
    WHEN first_bwar IS NULL THEN '3 never reached MLB'
    WHEN last_bwar < trade_season + 2 THEN '4 MLB career ended before window'
    WHEN first_bwar > trade_season + 5 THEN '5 debuted after window'
    ELSE '6 absent inside window only' END AS bucket,
    COUNT(*) AS legs
FROM legs GROUP BY 1 ORDER BY 1
"""

_RECEIVER_SHARE = f"""
WITH legs AS ({_LEGS})
SELECT b.year_id - l.trade_season AS years_after_trade,
       ROUND(SUM(b.war), 1) AS war_any_team,
       ROUND(SUM(b.war) FILTER (
           WHERE CASE WHEN b.team_id = 'ATH' THEN 'OAK' ELSE b.team_id END = l.to_team_bref
       ), 1) AS war_with_receiver
FROM legs l
JOIN bwar_player_seasons b
  ON b.mlb_id = l.mlb_player_id
 AND b.year_id BETWEEN l.trade_season AND l.trade_season + 5
GROUP BY 1 ORDER BY 1
"""


def main() -> None:
    with db.connect(read_only=True) as conn:
        buckets = conn.execute(_BUCKETS).df()
        share = conn.execute(_RECEIVER_SHARE).df()
    share["receiver_share"] = (share["war_with_receiver"] / share["war_any_team"]).round(2)
    print(buckets.to_string(index=False))
    print()
    print(share.to_string(index=False))


if __name__ == "__main__":
    main()
