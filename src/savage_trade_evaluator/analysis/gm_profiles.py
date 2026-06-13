"""GM behavioral profiles — per-regime trade behavior metrics.

Computes a behavioral fingerprint for each GM's tenure at a club:
player quality bias (buy WAR vs. sell WAR), age bias, prospect-hugging ratio,
deadline concentration, and pitching focus.

Profiles feed ``modeling/gm_archetypes.py`` for cluster labeling, and are
surfaced in War Room scenario cards to contextualize each trade with the
receiving GM's historical pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

MIN_TRADES = 5


def _build_profile_sql() -> str:
    return f"""
    WITH pitcher_ids AS (
        SELECT DISTINCT mlb_id AS pid FROM bwar_pitching
    ),
    receiver_legs AS (
        SELECT
            ra.regime_id,
            ra.decision_maker,
            ra.bref_code,
            MIN(ra.season) OVER (PARTITION BY ra.regime_id) AS regime_start,
            MAX(ra.season) OVER (PARTITION BY ra.regime_id) AS regime_end,
            tp.trade_event_id,
            tp.mlb_player_id,
            tp.date,
            COALESCE(w.war_t_minus_1, 0.0)            AS war_pre,
            CAST(tp.trade_season AS INT)
                - COALESCE(cr.birth_year, 1990)        AS age_at_trade,
            CASE WHEN pi.pid IS NOT NULL THEN 1 ELSE 0 END AS is_pitcher,
            CASE WHEN EXTRACT(month FROM tp.date) IN (7, 8) THEN 1 ELSE 0 END
                                                       AS is_deadline,
            COALESCE(pr.fv, 0.0)                       AS prospect_fv
        FROM trade_player_unified tp
        JOIN team_regime_assignments ra
            ON ra.bref_code = tp.to_team_bref
           AND ra.season     = tp.trade_season
        LEFT JOIN trade_player_war_window w
            ON  w.trade_event_id = tp.trade_event_id
            AND w.mlb_player_id  = tp.mlb_player_id
        LEFT JOIN chadwick_register cr ON cr.mlb_player_id = tp.mlb_player_id
        LEFT JOIN pitcher_ids pi ON pi.pid = tp.mlb_player_id
        LEFT JOIN prospect_rankings pr
            ON  pr.fangraphs_player_id = cr.fangraphs_id
            AND pr.rank_year = tp.trade_season - 1
        WHERE tp.mlb_player_id IS NOT NULL
          AND tp.trade_season BETWEEN 2010 AND 2024
    ),
    sender_legs AS (
        SELECT
            ra.regime_id,
            COALESCE(w.war_t_minus_1, 0.0) AS war_pre,
            COALESCE(pr.fv, 0.0)           AS prospect_fv
        FROM trade_player_unified tp
        JOIN team_regime_assignments ra
            ON ra.bref_code = tp.from_team_bref
           AND ra.season     = tp.trade_season
        LEFT JOIN trade_player_war_window w
            ON  w.trade_event_id = tp.trade_event_id
            AND w.mlb_player_id  = tp.mlb_player_id
        LEFT JOIN chadwick_register cr ON cr.mlb_player_id = tp.mlb_player_id
        LEFT JOIN prospect_rankings pr
            ON  pr.fangraphs_player_id = cr.fangraphs_id
            AND pr.rank_year = tp.trade_season - 1
        WHERE tp.mlb_player_id IS NOT NULL
          AND tp.trade_season BETWEEN 2010 AND 2024
    ),
    rcv_agg AS (
        SELECT
            regime_id, decision_maker, bref_code, regime_start, regime_end,
            COUNT(DISTINCT trade_event_id)             AS n_trades,
            AVG(war_pre)                               AS avg_war_received,
            AVG(age_at_trade)                          AS avg_age_received,
            AVG(CAST(is_pitcher AS DOUBLE))            AS pct_pitchers_received,
            AVG(CAST(is_deadline AS DOUBLE))           AS deadline_pct,
            AVG(CASE WHEN prospect_fv > 0 THEN prospect_fv END) AS fv_received_avg
        FROM receiver_legs
        GROUP BY regime_id, decision_maker, bref_code, regime_start, regime_end
    ),
    snd_agg AS (
        SELECT
            regime_id,
            AVG(war_pre)                               AS avg_war_sent,
            AVG(CASE WHEN prospect_fv > 0 THEN prospect_fv END) AS fv_sent_avg
        FROM sender_legs
        GROUP BY regime_id
    )
    SELECT
        r.regime_id,
        r.decision_maker,
        r.bref_code,
        r.regime_start,
        r.regime_end,
        (r.regime_end - r.regime_start + 1)            AS tenure_seasons,
        r.n_trades,
        r.n_trades::DOUBLE /
            NULLIF(r.regime_end - r.regime_start + 1, 0) AS trades_per_season,
        r.avg_war_received,
        COALESCE(s.avg_war_sent, 0.0)                  AS avg_war_sent,
        r.avg_war_received - COALESCE(s.avg_war_sent, 0.0) AS war_buyer_bias,
        r.avg_age_received,
        r.pct_pitchers_received,
        r.deadline_pct,
        COALESCE(r.fv_received_avg, 0.0)               AS fv_received_avg,
        COALESCE(s.fv_sent_avg, 0.0)                   AS fv_sent_avg,
        CASE
            WHEN COALESCE(s.fv_sent_avg, 0.0) > 0
            THEN COALESCE(r.fv_received_avg, 0.0) / s.fv_sent_avg
            ELSE NULL
        END                                            AS prospect_hugging_ratio
    FROM rcv_agg r
    LEFT JOIN snd_agg s USING (regime_id)
    WHERE r.n_trades >= {MIN_TRADES}
    ORDER BY r.n_trades DESC
    """


def build_gm_profiles() -> pd.DataFrame:
    """Compute behavioral profiles for all qualifying GM regimes.

    A regime qualifies if the GM made at least ``MIN_TRADES`` trades as
    receiving team over the 2010-2024 backtester window.

    Returns:
        DataFrame with one row per qualifying regime.
    """
    sql = _build_profile_sql()
    with db.connect(read_only=True) as conn:
        df = conn.execute(sql).fetchdf()

    logger.info("built %d GM behavioral profiles", len(df))
    return df


def persist_profiles(df: pd.DataFrame) -> None:
    """Write profiles to ``gm_behavioral_profiles`` table.

    Args:
        df: Result of ``build_gm_profiles()``.
    """
    with db.connect() as conn:
        schemas.initialize(conn)
        conn.execute("DELETE FROM gm_behavioral_profiles")
        conn.register("_gm_profiles", df)
        try:
            conn.execute(
                """
                INSERT INTO gm_behavioral_profiles
                    (regime_id, decision_maker, bref_code, regime_start, regime_end,
                     tenure_seasons, n_trades, trades_per_season, avg_war_received,
                     avg_war_sent, war_buyer_bias, avg_age_received,
                     pct_pitchers_received, deadline_pct,
                     fv_received_avg, fv_sent_avg, prospect_hugging_ratio)
                SELECT regime_id, decision_maker, bref_code, regime_start, regime_end,
                       tenure_seasons, n_trades, trades_per_season, avg_war_received,
                       avg_war_sent, war_buyer_bias, avg_age_received,
                       pct_pitchers_received, deadline_pct,
                       fv_received_avg, fv_sent_avg, prospect_hugging_ratio
                FROM _gm_profiles
                """
            )
        finally:
            conn.unregister("_gm_profiles")
    logger.info("persisted %d GM profiles", len(df))
