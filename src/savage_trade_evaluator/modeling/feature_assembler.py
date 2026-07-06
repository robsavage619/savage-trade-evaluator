"""C3: Hypothetical trade feature assembly for scenario scoring.

Builds the ALL_FEATURES vector for a trade that hasn't happened yet (or any
arbitrary player list + receiving team combination), enabling the production
model to score hypothetical trades the same way it scores historical ones.

Primary entry point::

    from savage_trade_evaluator.modeling.feature_assembler import assemble_hypothetical
    row = assemble_hypothetical(
        receiver_bref="HOU",
        sender_bref="NYY",
        player_mlb_ids=[592518, 605483],
        trade_season=2025,
    )
    # row is a 1-row pd.DataFrame with all ALL_FEATURES columns; NaN where data
    # is unavailable (filled from fit.feature_means at score time).

    from savage_trade_evaluator.modeling.scenario_engine import score_hypothetical
    result = score_hypothetical(row)  # posterior dict per outcome

Design notes:
- Queries replicate the logic from trade_acquired_* views but via UNNEST CTEs
  so no trade_event_id is required.
- Each helper function returns a dict[str, float | None]; None means no data.
- Output columns match ALL_FEATURES exactly so the result can be passed
  directly to ``production_fit.get_fit()`` → ``predict()``.
- Phase 3 only — do not call in the main ingest path.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v2.features import ALL_FEATURES
from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

# Confirmed features from R-60 (in order of fold credibility).
# These are prioritised in assembly; NaN on others is acceptable.
PRIORITY_FEATURES = frozenset(
    {
        "receiver_acquired_player_quality",
        "receiver_acquired_player_avg_war_trajectory",
        "receiver_avg_age_at_trade",
        "receiver_pct_pitchers",
        "receiver_acquired_milb_hit_quality",
        "receiver_acquired_milb_pitch_quality",
        "receiver_acquired_milb_age_advantage",
        "receiver_pct_international_born",
        "receiver_acquired_avg_prior_awards",
    }
)


# ---------------------------------------------------------------------------
# Component helpers — each takes an open conn + inputs, returns dict
# ---------------------------------------------------------------------------


def _receiver_team_features(
    receiver_bref: str,
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Pull receiver org context from existing DB tables."""
    row = conn.execute(
        """
        SELECT
            tsf.prior_year_war             AS receiver_prior_year_war,
            tsf.org_dev_fit_pitching       AS receiver_dev_fit_pitching,
            tsf.org_dev_fit_hitting        AS receiver_dev_fit_hitting,
            tsf.prior_year_pyth_pct        AS receiver_prior_year_pyth_pct,
            tsf.org_pitcher_k_jump_3yr     AS receiver_org_pitcher_k_jump_3yr,
            tsf.org_hitter_xwoba_jump_3yr  AS receiver_org_hitter_xwoba_jump_3yr,
            tsf.tech_adoption_lead_years   AS receiver_tech_adoption_lead_years,
            tsf.alumni_network_score       AS receiver_alumni_network_score,
            tsf.org_pitcher_k_jump_recency_bias AS receiver_org_pitcher_k_jump_recency_bias,
            tsf.platoon_woba_diff          AS receiver_platoon_woba_diff,
            stp.total_payroll              AS receiver_total_payroll,
            tspc.payroll_pct_of_cap        AS receiver_payroll_pct_of_cap,
            tspc.payroll_trend_3yr         AS receiver_payroll_trend_3yr
        FROM team_season_features tsf
        LEFT JOIN spotrac_team_payroll stp
            ON stp.team_bref = tsf.bref_code AND stp.season = tsf.season
        LEFT JOIN team_season_payroll_context tspc
            ON tspc.team_bref = tsf.bref_code AND tspc.season = tsf.season
        WHERE tsf.bref_code = ? AND tsf.season = ?
        """,
        [receiver_bref, trade_season],
    ).fetchone()

    if row is None:
        logger.warning("no team_season_features for %s / %d", receiver_bref, trade_season)
        return {}

    col_names = [
        "receiver_prior_year_war",
        "receiver_dev_fit_pitching",
        "receiver_dev_fit_hitting",
        "receiver_prior_year_pyth_pct",
        "receiver_org_pitcher_k_jump_3yr",
        "receiver_org_hitter_xwoba_jump_3yr",
        "receiver_tech_adoption_lead_years",
        "receiver_alumni_network_score",
        "receiver_org_pitcher_k_jump_recency_bias",
        "receiver_platoon_woba_diff",
        "receiver_total_payroll",
        "receiver_payroll_pct_of_cap",
        "receiver_payroll_trend_3yr",
    ]
    features: dict[str, float | None] = dict(
        zip(
            col_names,
            [float(v) if v is not None else None for v in row],
            strict=True,
        )
    )

    pyth = features.get("receiver_prior_year_pyth_pct")
    cap_pct = features.get("receiver_payroll_pct_of_cap")
    if pyth is not None and cap_pct is not None:
        features["receiver_contention_window_score"] = pyth * max(0.0, 1.0 - cap_pct)

    return features


def _sender_features(
    sender_bref: str,
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Pull origin-team features (sending org's dev cluster + sunk cost)."""
    row = conn.execute(
        """
        SELECT
            tsf.origin_sunk_cost_pressure,
            -- Dev cluster proxy: origin org's dev_fit composite as a signal of
            -- what kind of pipeline the acquired player emerged from.
            (tsf.org_dev_fit_pitching + tsf.org_dev_fit_hitting) / 2.0
                AS receiver_acquired_from_dev_cluster_score
        FROM team_season_features tsf
        WHERE tsf.bref_code = ? AND tsf.season = ?
        """,
        [sender_bref, trade_season],
    ).fetchone()

    if row is None:
        return {}

    return {
        "origin_sunk_cost_pressure": float(row[0]) if row[0] is not None else None,
        "receiver_acquired_from_dev_cluster_score": (float(row[1]) if row[1] is not None else None),
    }


def _player_demographics(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Demographic mix for the acquired player group."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    row = conn.execute(
        f"""
        SELECT
            AVG(? - COALESCE(cr.birth_year, 1990))               AS avg_age_at_trade,
            AVG(CASE WHEN mp.bat_side = 'L' THEN 1.0 ELSE 0.0 END) AS pct_left_handed_bat,
            AVG(CASE
                    WHEN COALESCE(mp.birth_country, 'USA') NOT IN ('USA', 'Puerto Rico')
                    THEN 1.0 ELSE 0.0 END)                       AS pct_international_born,
            SUM(CASE WHEN bp.mlb_id IS NOT NULL THEN 1 ELSE 0 END)::DOUBLE
                / COUNT(*)                                        AS pct_pitchers
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN chadwick_register cr ON cr.mlb_player_id = p.mlb_player_id
        LEFT JOIN mlb_people mp ON mp.mlb_player_id = p.mlb_player_id
        LEFT JOIN (
            SELECT DISTINCT mlb_id
            FROM bwar_pitching
            WHERE year_id BETWEEN ? - 3 AND ?
        ) bp ON bp.mlb_id = p.mlb_player_id
        """,
        [trade_season, trade_season, trade_season],
    ).fetchone()

    if row is None:
        return {}

    return {
        "receiver_avg_age_at_trade": float(row[0]) if row[0] is not None else None,
        "receiver_pct_left_handed_bat": float(row[1]) if row[1] is not None else None,
        "receiver_pct_international_born": float(row[2]) if row[2] is not None else None,
        "receiver_pct_pitchers": float(row[3]) if row[3] is not None else None,
    }


def _player_war_quality(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Acquired player quality and WAR trajectory from bWAR."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    row = conn.execute(
        f"""
        WITH bwar_annual AS (
            SELECT mlb_id, year_id, SUM(war) AS war
            FROM (
                SELECT mlb_id, year_id, war FROM bwar_batting
                UNION ALL
                SELECT mlb_id, year_id, war FROM bwar_pitching
            ) all_war
            GROUP BY mlb_id, year_id
        ),
        player_seasons AS (
            SELECT
                p.mlb_player_id,
                b1.war AS war_tm1,
                b2.war AS war_tm2,
                b3.war AS war_tm3
            FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
            LEFT JOIN bwar_annual b1 ON b1.mlb_id = p.mlb_player_id AND b1.year_id = ? - 1
            LEFT JOIN bwar_annual b2 ON b2.mlb_id = p.mlb_player_id AND b2.year_id = ? - 2
            LEFT JOIN bwar_annual b3 ON b3.mlb_id = p.mlb_player_id AND b3.year_id = ? - 3
        ),
        player_quality AS (
            SELECT
                mlb_player_id,
                -- 3:2:1 Marcel-style weighted average as proxy for player quality
                (3.0 * COALESCE(war_tm1, 0) + 2.0 * COALESCE(war_tm2, 0)
                    + 1.0 * COALESCE(war_tm3, 0)) / 6.0         AS weighted_war,
                -- Trajectory: T-1 minus T-3 (positive = improving)
                COALESCE(war_tm1, 0) - COALESCE(war_tm3, 0)     AS war_trajectory
            FROM player_seasons
            WHERE war_tm1 IS NOT NULL OR war_tm2 IS NOT NULL OR war_tm3 IS NOT NULL
        )
        SELECT AVG(weighted_war), AVG(war_trajectory)
        FROM player_quality
        """,
        [trade_season, trade_season, trade_season],
    ).fetchone()

    if row is None:
        return {}

    return {
        "receiver_acquired_player_quality": (float(row[0]) if row[0] is not None else None),
        "receiver_acquired_player_avg_war_trajectory": (
            float(row[1]) if row[1] is not None else None
        ),
    }


def _player_milb_quality(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """MiLB quality metrics — replicates trade_acquired_milb_quality logic."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    row = conn.execute(
        f"""
        WITH leveled AS (
            SELECT
                p.mlb_player_id,
                a.top_sport_id,
                a.pa, a.ip,
                a.ops_pa_weighted,
                a.era_ip_weighted,
                a.age,
                CASE
                    WHEN a.top_sport_id = 11 THEN 1.00
                    WHEN a.top_sport_id = 12 THEN 0.85
                    WHEN a.top_sport_id = 13 THEN 0.70
                    WHEN a.top_sport_id = 14 THEN 0.55
                    ELSE 0.40
                END AS level_mult,
                CASE
                    WHEN a.top_sport_id = 11 THEN 25
                    WHEN a.top_sport_id = 12 THEN 23
                    WHEN a.top_sport_id = 13 THEN 21
                    WHEN a.top_sport_id = 14 THEN 20
                    ELSE 22
                END AS expected_age
            FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
            LEFT JOIN milb_player_season_aggregate a
                ON a.mlb_player_id = p.mlb_player_id AND a.season = ? - 1
        ),
        per_player AS (
            SELECT
                mlb_player_id,
                CASE WHEN pa >= 50   THEN ops_pa_weighted * level_mult   ELSE NULL END
                    AS hit_quality,
                CASE WHEN ip >= 20 AND era_ip_weighted > 0
                     THEN (5.0 / era_ip_weighted) * level_mult            ELSE NULL END
                    AS pitch_quality,
                CASE WHEN COALESCE(pa, ip) IS NOT NULL
                     THEN expected_age - age                              ELSE NULL END
                    AS age_advantage
            FROM leveled
        )
        SELECT
            AVG(hit_quality)   AS receiver_acquired_milb_hit_quality,
            AVG(pitch_quality) AS receiver_acquired_milb_pitch_quality,
            AVG(age_advantage) AS receiver_acquired_milb_age_advantage
        FROM per_player
        """,
        [trade_season],
    ).fetchone()

    if row is None:
        return {}

    return {
        "receiver_acquired_milb_hit_quality": (float(row[0]) if row[0] is not None else None),
        "receiver_acquired_milb_pitch_quality": (float(row[1]) if row[1] is not None else None),
        "receiver_acquired_milb_age_advantage": (float(row[2]) if row[2] is not None else None),
    }


def _player_pedigree(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Award pedigree for acquired players (pre-trade)."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    row = conn.execute(
        f"""
        WITH players AS (SELECT unnest([{ids_sql}]) AS mlb_player_id),
        award_counts AS (
            SELECT
                p.mlb_player_id,
                COUNT(a.award_id) AS prior_awards
            FROM players p
            LEFT JOIN mlb_awards a
                ON a.player_id = p.mlb_player_id AND a.season < ?
               AND a.award_id IN ('ALMVP','NLMVP','ALCY','NLCY','ALROY','NLROY',
                                   'ALGG','NLGG','ALSS','NLSS','WSMVP','MLBHOF')
            GROUP BY p.mlb_player_id
        )
        SELECT
            AVG(prior_awards)                                 AS avg_prior_awards,
            AVG(CASE WHEN prior_awards > 0 THEN 1.0 ELSE 0.0 END) AS pct_awarded
        FROM award_counts
        """,
        [trade_season],
    ).fetchone()

    if row is None:
        return {}

    return {
        "receiver_acquired_avg_prior_awards": (float(row[0]) if row[0] is not None else None),
        "receiver_acquired_pct_awarded": (float(row[1]) if row[1] is not None else None),
    }


def _player_statcast(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Statcast quality signals from the year before the trade."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    features: dict[str, float | None] = {}
    prev = trade_season - 1

    # Exit velocity + barrel rate
    row = conn.execute(
        f"""
        SELECT AVG(ev.avg_hit_speed), AVG(ev.brl_percent)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN statcast_batter_exitvelo_barrels ev
            ON ev.player_id = p.mlb_player_id AND ev.year = ?
        WHERE ev.avg_hit_speed IS NOT NULL
        """,
        [prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_avg_exit_speed"] = float(row[0])
        features["receiver_acquired_barrel_rate"] = float(row[1]) if row[1] is not None else None

    # Sprint speed
    row = conn.execute(
        f"""
        SELECT AVG(ss.sprint_speed)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN statcast_sprint_speed ss
            ON ss.player_id = p.mlb_player_id AND ss.year = ?
        WHERE ss.sprint_speed IS NOT NULL
        """,
        [prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_sprint_speed"] = float(row[0])

    # Catcher pop-time
    row = conn.execute(
        f"""
        SELECT AVG(cp.pop_2b_sba_count)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN statcast_catcher_poptime cp
            ON cp.player_id = p.mlb_player_id AND cp.year = ?
        WHERE cp.pop_2b_sba_count IS NOT NULL
        """,
        [prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_catcher_poptime"] = float(row[0])

    # Outfielder OAA
    row = conn.execute(
        f"""
        SELECT SUM(oa.oaa)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN statcast_outs_above_average oa
            ON oa.player_id = p.mlb_player_id AND oa.year = ?
        WHERE oa.oaa IS NOT NULL
        """,
        [prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_outfielder_oaa"] = float(row[0])

    return features


def _player_pitcher_quality(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Pitcher-specific quality signals (K trajectory + arsenal volatility)."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    features: dict[str, float | None] = {}
    prev = trade_season - 1

    # K-rate trajectory — weighted avg k_percent per player-season from arsenal stats
    row = conn.execute(
        f"""
        WITH season_k AS (
            SELECT pa.player_id AS mlb_player_id,
                   pa.year,
                   SUM(pa.k_percent * pa.pitches) / NULLIF(SUM(pa.pitches), 0) AS k_pct
            FROM statcast_pitcher_arsenal_stats pa
            WHERE pa.player_id IN ({ids_sql}) AND pa.year BETWEEN ? - 2 AND ?
            GROUP BY pa.player_id, pa.year
        ),
        krates AS (
            SELECT mlb_player_id,
                   AVG(CASE WHEN year = ? THEN k_pct END)     AS k_now,
                   AVG(CASE WHEN year = ? - 2 THEN k_pct END) AS k_prev
            FROM season_k GROUP BY mlb_player_id
        )
        SELECT AVG(k_now - k_prev)
        FROM krates
        WHERE k_now IS NOT NULL AND k_prev IS NOT NULL
        """,
        [prev, prev, prev, prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_pitcher_k_trajectory"] = float(row[0])

    # Arsenal volatility (number of distinct pitch types)
    row = conn.execute(
        f"""
        SELECT AVG(n_pitches)
        FROM (
            SELECT pa.player_id AS mlb_player_id,
                   COUNT(DISTINCT pa.pitch_type) AS n_pitches
            FROM statcast_pitcher_arsenal_stats pa
            WHERE pa.player_id IN ({ids_sql}) AND pa.year = ?
            GROUP BY pa.player_id
        ) t
        WHERE n_pitches > 0
        """,
        [prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_pitcher_arsenal_volatility"] = float(row[0])

    return features


def _player_prospect_fv(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """FV grades from FanGraphs prospect_rankings via chadwick bridge."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    row = conn.execute(
        f"""
        SELECT AVG(pr.fv), MAX(pr.fv)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        JOIN chadwick_register cr ON cr.mlb_player_id = p.mlb_player_id
        JOIN prospect_rankings pr
            ON pr.fangraphs_player_id = cr.fangraphs_id
           AND pr.rank_year = ? - 1
        WHERE pr.fv IS NOT NULL
        """,
        [trade_season],
    ).fetchone()

    features: dict[str, float | None] = {}
    if row and row[0] is not None:
        features["receiver_acquired_avg_fv"] = float(row[0])
        features["receiver_acquired_max_fv"] = float(row[1]) if row[1] is not None else None

    # TJStats / MLB Pipeline consensus FV (current-year snapshots — no year filter)
    row_tj = conn.execute(
        f"""
        SELECT AVG(tj.fv)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN tjstats_prospect_rankings tj ON tj.player_id = p.mlb_player_id
        WHERE tj.fv IS NOT NULL
        """,
    ).fetchone()
    row_pipe = conn.execute(
        f"""
        SELECT AVG(pi.overall_grade)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN mlb_pipeline_prospects pi ON pi.mlbam_id = p.mlb_player_id
        WHERE pi.overall_grade IS NOT NULL
        """,
    ).fetchone()

    tj_fv = float(row_tj[0]) if row_tj and row_tj[0] is not None else None
    pipe_fv = float(row_pipe[0]) if row_pipe and row_pipe[0] is not None else None
    if tj_fv is not None and pipe_fv is not None:
        features["receiver_acquired_consensus_fv"] = (tj_fv + pipe_fv) / 2.0
        features["receiver_acquired_fv_divergence"] = abs(tj_fv - pipe_fv)
    elif tj_fv is not None:
        features["receiver_acquired_consensus_fv"] = tj_fv
    elif pipe_fv is not None:
        features["receiver_acquired_consensus_fv"] = pipe_fv

    return features


def _player_misc(
    player_mlb_ids: list[int],
    trade_season: int,
    conn: Any,
) -> dict[str, float | None]:
    """Miscellaneous player features: TJStats tjbat+, WAR acceleration, origin YTD WAR."""
    ids_sql = ", ".join(str(i) for i in player_mlb_ids)
    features: dict[str, float | None] = {}
    prev = trade_season - 1

    # TJStats tjbat+ (MiLB contact quality)
    row = conn.execute(
        f"""
        SELECT AVG(tj.tjbat_plus)
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN tjstats_tjbat tj
            ON tj.player_id = p.mlb_player_id AND tj.season = ?
        WHERE tj.tjbat_plus IS NOT NULL
        """,
        [prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_milb_tjbat_plus"] = float(row[0])

    # WAR acceleration (second derivative — T-1 vs T-2 change)
    row = conn.execute(
        f"""
        WITH bwar_annual AS (
            SELECT mlb_id, year_id, SUM(war) AS war
            FROM (
                SELECT mlb_id, year_id, war FROM bwar_batting
                UNION ALL
                SELECT mlb_id, year_id, war FROM bwar_pitching
            ) a GROUP BY mlb_id, year_id
        )
        SELECT AVG((b1.war - b2.war) - (b2.war - b3.war))
        FROM (SELECT unnest([{ids_sql}]) AS mlb_player_id) p
        LEFT JOIN bwar_annual b1 ON b1.mlb_id = p.mlb_player_id AND b1.year_id = ?
        LEFT JOIN bwar_annual b2 ON b2.mlb_id = p.mlb_player_id AND b2.year_id = ? - 1
        LEFT JOIN bwar_annual b3 ON b3.mlb_id = p.mlb_player_id AND b3.year_id = ? - 2
        WHERE b1.war IS NOT NULL AND b2.war IS NOT NULL AND b3.war IS NOT NULL
        """,
        [prev, prev, prev],
    ).fetchone()
    if row and row[0] is not None:
        features["receiver_acquired_war_acceleration"] = float(row[0])

    return features


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assemble_hypothetical(
    receiver_bref: str,
    sender_bref: str,
    player_mlb_ids: list[int],
    trade_season: int,
) -> pd.DataFrame:
    """Assemble a 1-row feature DataFrame for a hypothetical trade.

    Queries all relevant tables for the given receiver team context and
    player list. Missing features are left as NaN (``production_fit.get_fit()``
    → ``scenario_engine._score_df()`` fills them from training-set means).

    Args:
        receiver_bref: Baseball Reference code for the acquiring team.
        sender_bref: Baseball Reference code for the sending team.
        player_mlb_ids: MLBAM integer player IDs of players being acquired.
        trade_season: Season of the hypothetical trade (e.g. 2025).

    Returns:
        Single-row DataFrame with columns matching ALL_FEATURES.
    """
    if not player_mlb_ids:
        raise ValueError("player_mlb_ids must not be empty")

    features: dict[str, Any] = {}

    with db.connect(read_only=True) as conn:
        features.update(_receiver_team_features(receiver_bref, trade_season, conn))
        features.update(_sender_features(sender_bref, trade_season, conn))
        features.update(_player_demographics(player_mlb_ids, trade_season, conn))
        features.update(_player_war_quality(player_mlb_ids, trade_season, conn))
        features.update(_player_milb_quality(player_mlb_ids, trade_season, conn))
        features.update(_player_pedigree(player_mlb_ids, trade_season, conn))
        features.update(_player_statcast(player_mlb_ids, trade_season, conn))
        features.update(_player_pitcher_quality(player_mlb_ids, trade_season, conn))
        features.update(_player_prospect_fv(player_mlb_ids, trade_season, conn))
        features.update(_player_misc(player_mlb_ids, trade_season, conn))

    # Derived interaction terms
    avg_age = features.get("receiver_avg_age_at_trade")
    dev_hit = features.get("receiver_dev_fit_hitting")
    if avg_age is not None and dev_hit is not None:
        peak_gate = max(0.0, 32.0 - avg_age)
        features["receiver_devfit_x_peak_age"] = dev_hit * peak_gate

    features["post_2015_era"] = float(trade_season >= 2015)

    # Build a row aligned to ALL_FEATURES (NaN for missing)
    row = {col: features.get(col, np.nan) for col in ALL_FEATURES}

    def _is_nan(v: object) -> bool:
        return v is None or (isinstance(v, float) and np.isnan(v))

    n_populated = sum(1 for v in row.values() if not _is_nan(v))
    n_priority = sum(1 for k in PRIORITY_FEATURES if k in row and not _is_nan(row[k]))
    logger.info(
        "assembled %d/%d total features (%d/%d priority) for %s ← %s [%d players]",
        n_populated,
        len(ALL_FEATURES),
        n_priority,
        len(PRIORITY_FEATURES),
        receiver_bref,
        sender_bref,
        len(player_mlb_ids),
    )
    if n_priority < 5:
        logger.warning(
            "only %d/%d priority features populated — "
            "posterior will rely heavily on training-set means",
            n_priority,
            len(PRIORITY_FEATURES),
        )

    df = pd.DataFrame([row])
    df.attrs["n_populated"] = n_populated
    df.attrs["n_priority"] = n_priority
    return df
