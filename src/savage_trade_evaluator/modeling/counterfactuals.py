"""C1a: Org-adjusted Marcel counterfactual for traded players.

For each historical trade, estimates the counterfactual WAR the acquired
player would have produced if they had *stayed* with the sending team:

    cf_war_stay = marcel_projected_war * org_retention_factor(sending_team, position_group, season)

``org_retention_factor`` is calibrated from players who did stay — the median
actual/Marcel-expected WAR ratio for each org x position group x 5-year window.
Shrunk toward 1.0 with a 5-observation Bayesian prior so thin cells don't
over-steer.

The counterfactual treatment-effect outcome is then:

    war_delta_cf = war_delta - (cf_war_window - war_t1_anchor)

where the subtracted term is the expected WAR gain the player would have had
*staying*, not trading. This isolates the org-context component from the
player's natural aging trajectory — a closer approximation of the ATT (D-10).

**Phase assignment:** C1a (Phase 2). Full synthetic-control donor pool is C1b
(Phase 3 — only if C1a credible-feature count stalls at the R-60 baseline of 9).
**Validation gate:** run `scripts/r61_counterfactual_validation.py` after building;
pass = credible features in `war_delta_cf` >= 9 (current `war_delta_residual` baseline).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.marcel import (
    REPLACEMENT_WAR,
    _age_adjustment,
    _marcel_projection,
)
from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

# Org-factor Bayesian prior: shrink toward 1.0 with this many virtual observations.
# Higher → more pooling, less org-specific signal. 5 is moderate — a single outlier
# season doesn't dominate, but a persistent org trend comes through.
ORG_FACTOR_PRIOR_N: float = 5.0
ORG_FACTOR_PRIOR_MEAN: float = 1.0

# Rolling window half-width (seasons). Actual window = [S - HALF, S + HALF].
ORG_FACTOR_HALF_WINDOW: int = 2  # 5-year centered window

# Use Marcel data only where base season is recent enough to be meaningful.
ORG_CALIBRATION_START: int = 2005

# Binary position group for MVP — SP/RP sub-split is Phase 3.
# Anything in bwar_pitching with gs > 0 is a starter; gs == 0 is a reliever.
# Anything exclusively in bwar_batting (is_pitcher=False) is a hitter.
POS_SP = "SP"
POS_RP = "RP"
POS_HIT = "HIT"


def build_org_retention_factors() -> pd.DataFrame:
    """Compute org retention factors for all (team, position_group, season) cells.

    Retention factor = shrunk median(actual_T1 / Marcel_expected_T1) over a
    5-year centered window around each season.

    Returns:
        DataFrame with columns: team_bref, position_group, season,
        retention_factor, sample_n, rolling_window.
    """
    with db.connect(read_only=True) as conn:
        raw = conn.execute(
            f"""
            WITH bwar_annual AS (
                -- Sum all stints into one WAR figure per (player, season, team).
                SELECT mlb_id, year_id, team_id AS team_bref, SUM(war) AS war
                FROM (
                    SELECT mlb_id, year_id, team_id, war
                    FROM bwar_batting
                    WHERE is_pitcher IS NOT TRUE
                    UNION ALL
                    SELECT mlb_id, year_id, team_id, war
                    FROM bwar_pitching
                ) all_war
                GROUP BY mlb_id, year_id, team_id
            ),
            -- Position group per (player, season): pitcher if any bwar_pitching row exists.
            -- Starter if gs > 0 in that season; reliever if gs = 0.
            pos_group AS (
                SELECT mlb_id, year_id,
                    CASE
                        WHEN gs > 0  THEN '{POS_SP}'
                        ELSE              '{POS_RP}'
                    END AS position_group
                FROM (
                    SELECT mlb_id, year_id, SUM(gs) AS gs
                    FROM bwar_pitching
                    GROUP BY mlb_id, year_id
                )
                UNION ALL
                SELECT DISTINCT mlb_id, year_id, '{POS_HIT}' AS position_group
                FROM bwar_batting
                WHERE is_pitcher IS NOT TRUE
            ),
            -- Staying player-seasons: player was at same team in T and T+1.
            staying AS (
                SELECT
                    a.mlb_id,
                    a.year_id         AS season_t,
                    a.team_bref,
                    a.war             AS war_t0,
                    b.war             AS war_t1_actual,
                    tm1.war           AS war_tm1,
                    tm2.war           AS war_tm2,
                    -- Age at season T (approximate — calendar year diff)
                    (a.year_id - cr.birth_year)::DOUBLE AS age_t0,
                    pg.position_group
                FROM bwar_annual a
                -- T+1: same player, same team, next year
                JOIN bwar_annual b
                    ON b.mlb_id = a.mlb_id
                   AND b.year_id = a.year_id + 1
                   AND b.team_bref = a.team_bref
                -- T-1 and T-2: any team (Marcel uses career history)
                LEFT JOIN bwar_annual tm1
                    ON tm1.mlb_id = a.mlb_id AND tm1.year_id = a.year_id - 1
                LEFT JOIN bwar_annual tm2
                    ON tm2.mlb_id = a.mlb_id AND tm2.year_id = a.year_id - 2
                -- Birth year for age curve
                LEFT JOIN chadwick_register cr
                    ON cr.mlb_player_id = a.mlb_id
                -- Position group: use T-season assignment
                LEFT JOIN pos_group pg
                    ON pg.mlb_id = a.mlb_id AND pg.year_id = a.year_id
                WHERE a.year_id BETWEEN {ORG_CALIBRATION_START} AND 2024
            )
            SELECT
                mlb_id, season_t, team_bref, position_group,
                war_t0, war_t1_actual, war_tm1, war_tm2, age_t0
            FROM staying
            WHERE position_group IS NOT NULL
            """
        ).df()

    if raw.empty:
        logger.warning("build_org_retention_factors: no staying player-seasons found")
        return pd.DataFrame(
            columns=["team_bref", "position_group", "season", "retention_factor", "sample_n"]
        )

    logger.info("build_org_retention_factors: %d staying player-seasons loaded", len(raw))

    # Compute Marcel expected WAR for T+1 per player-season.
    def _expected(row: pd.Series) -> float:
        age = float(row["age_t0"]) if not pd.isna(row["age_t0"]) else 28.0
        base = _marcel_projection(
            war_t1=row["war_t0"] if not pd.isna(row["war_t0"]) else None,
            war_t2=row["war_tm1"] if not pd.isna(row["war_tm1"]) else None,
            war_t3=row["war_tm2"] if not pd.isna(row["war_tm2"]) else None,
        )
        age_adj = _age_adjustment(age, 1)
        return base + age_adj

    raw["expected_t1"] = raw.apply(_expected, axis=1)

    # Ratio = actual / expected. Clip expected to ±0.2 to avoid division by near-zero.
    # Capped ratio at [0.1, 5.0] to prevent extreme outliers (injuries, etc.) from skewing.
    expected_clipped = raw["expected_t1"].clip(lower=0.2)
    raw["ratio"] = (raw["war_t1_actual"] / expected_clipped).clip(0.1, 5.0)

    # Build retention-factor table: for each (team, position_group, season),
    # aggregate all rows within [season - HALF, season + HALF] and apply shrinkage.
    seasons = sorted(raw["season_t"].unique())
    records = []
    for season in seasons:
        window = raw[
            (raw["season_t"] >= season - ORG_FACTOR_HALF_WINDOW)
            & (raw["season_t"] <= season + ORG_FACTOR_HALF_WINDOW)
        ]
        for (team, pos), group in window.groupby(["team_bref", "position_group"]):
            ratios = group["ratio"].dropna().values
            n = len(ratios)
            if n == 0:
                continue
            sum_r = float(np.sum(ratios))
            shrunk = (sum_r + ORG_FACTOR_PRIOR_N * ORG_FACTOR_PRIOR_MEAN) / (n + ORG_FACTOR_PRIOR_N)
            records.append(
                {
                    "team_bref": team,
                    "position_group": pos,
                    "season": int(season),
                    "retention_factor": round(shrunk, 4),
                    "sample_n": n,
                    "rolling_window": 2 * ORG_FACTOR_HALF_WINDOW + 1,
                }
            )

    result = pd.DataFrame(records)
    logger.info("build_org_retention_factors: %d (team, pos, season) cells", len(result))
    return result


def _position_group_for_player(mlb_id: int, trade_season: int, conn: object) -> str:
    """Determine position group for a player in the trade season.

    Uses bwar_pitching presence as the pitcher/hitter discriminator.
    """
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT SUM(gs) FROM bwar_pitching WHERE mlb_id = ? AND year_id = ?",
        [mlb_id, trade_season],
    ).fetchone()
    if row and row[0] is not None:
        return POS_SP if int(row[0]) > 0 else POS_RP
    return POS_HIT


def build_counterfactual_residuals(
    war_window_start: int = 2,
    war_window_end: int = 5,
    org_factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute org-adjusted counterfactual residual for each trade event.

    Extends the Marcel residual (``build_marcel_residuals()``) by multiplying
    the Marcel projection by the sending-team's org retention factor. The result
    ``expected_war_delta_cf`` is the expected WAR delta *had the player stayed*.
    ``war_delta_cf = war_delta - (expected_war_delta_cf - expected_war_delta_marcel)``
    represents the receiving-team treatment effect after controlling for both
    aging and sending-team development context.

    Args:
        war_window_start: First year of the post-trade WAR window (default 2).
        war_window_end: Last year inclusive (default 5).
        org_factors: Pre-built org retention factor DataFrame. Built internally
            if None (slow: scans full bWAR history).

    Returns:
        DataFrame keyed on (trade_event_id, receiver_bref, trade_season) with:
        - ``expected_war_delta_cf``: Org-adjusted counterfactual WAR delta.
        - ``war_delta_cf``: war_delta minus expected_war_delta_cf.
    """
    if org_factors is None:
        org_factors = build_org_retention_factors()

    # Build a lookup: (team_bref, position_group, season) → retention_factor
    factor_lookup: dict[tuple[str, str, int], float] = {
        (row.team_bref, row.position_group, row.season): row.retention_factor
        for row in org_factors.itertuples(index=False)
    }

    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            WITH bwar_annual AS (
                SELECT mlb_id, year_id, SUM(war) AS war
                FROM (
                    SELECT mlb_id, year_id, war FROM bwar_batting
                    UNION ALL
                    SELECT mlb_id, year_id, war FROM bwar_pitching
                ) all_war
                GROUP BY mlb_id, year_id
            ),
            player_age AS (
                SELECT mlb_player_id, birth_year
                FROM chadwick_register
                WHERE birth_year IS NOT NULL
            ),
            distinct_players AS (
                SELECT DISTINCT trade_event_id, trade_season,
                    to_team_bref AS receiver_bref,
                    from_team_bref AS sending_team,
                    mlb_player_id
                FROM trade_player_unified
                WHERE mlb_player_id IS NOT NULL
            )
            SELECT
                dp.trade_event_id,
                dp.trade_season,
                dp.receiver_bref,
                dp.sending_team,
                dp.mlb_player_id,
                pa.birth_year,
                b1.war AS war_tm1,
                b2.war AS war_tm2,
                b3.war AS war_tm3
            FROM distinct_players dp
            LEFT JOIN player_age pa ON pa.mlb_player_id = dp.mlb_player_id
            LEFT JOIN bwar_annual b1
                ON b1.mlb_id = dp.mlb_player_id AND b1.year_id = dp.trade_season - 1
            LEFT JOIN bwar_annual b2
                ON b2.mlb_id = dp.mlb_player_id AND b2.year_id = dp.trade_season - 2
            LEFT JOIN bwar_annual b3
                ON b3.mlb_id = dp.mlb_player_id AND b3.year_id = dp.trade_season - 3
            """
        ).df()

        # Fetch position groups per player-season in bulk.
        pit_rows = conn.execute(
            "SELECT mlb_id, year_id, SUM(gs) AS total_gs"
            " FROM bwar_pitching"
            " WHERE mlb_id IS NOT NULL AND year_id IS NOT NULL"
            " GROUP BY mlb_id, year_id"
        ).df()

    logger.info("build_counterfactual_residuals: %d player-trade rows loaded", len(df))

    # Build position-group lookup: (mlb_id, year) → pos_group
    pit_lookup: dict[tuple[int, int], str] = {}
    for row in pit_rows.itertuples(index=False):
        if pd.isna(row.mlb_id) or pd.isna(row.year_id):
            continue
        pg = POS_SP if (row.total_gs or 0) > 0 else POS_RP
        pit_lookup[(int(row.mlb_id), int(row.year_id))] = pg

    df["age_at_trade"] = df["trade_season"] - df["birth_year"].astype("Float64")

    def _row_cf_expected(row: pd.Series) -> float:
        age = float(row["age_at_trade"]) if not pd.isna(row["age_at_trade"]) else 28.0
        w1 = row["war_tm1"] if not pd.isna(row["war_tm1"]) else None
        w2 = row["war_tm2"] if not pd.isna(row["war_tm2"]) else None
        w3 = row["war_tm3"] if not pd.isna(row["war_tm3"]) else None

        # Marcel base projection for T+1
        base_t1 = _marcel_projection(w1, w2, w3)

        # Org retention factor for sending team
        mlb_id = int(row["mlb_player_id"])
        trade_season = int(row["trade_season"])
        pos = pit_lookup.get((mlb_id, trade_season - 1), POS_HIT)
        sending = str(row["sending_team"])

        # Try exact season first, then fall back to nearest available season
        for season_try in [trade_season, trade_season - 1, trade_season + 1]:
            factor = factor_lookup.get((sending, pos, season_try))
            if factor is not None:
                break
        if factor is None:
            factor = ORG_FACTOR_PRIOR_MEAN  # no data → assume league-average org

        # Project cumulative WAR over [window_start, window_end], org-adjusted
        total_cf = 0.0
        w1_anchor = float(w1) if w1 is not None else REPLACEMENT_WAR
        for offset in range(war_window_start, war_window_end + 1):
            age_adj = sum(_age_adjustment(age, k) for k in range(1, offset + 1))
            expected_year = (base_t1 + age_adj) * factor
            total_cf += expected_year

        return total_cf - w1_anchor

    df["expected_war_delta_cf_player"] = df.apply(_row_cf_expected, axis=1)

    agg = (
        df.groupby(["trade_event_id", "receiver_bref", "trade_season"], as_index=False)[
            "expected_war_delta_cf_player"
        ]
        .sum()
        .rename(columns={"expected_war_delta_cf_player": "expected_war_delta_cf"})
    )
    logger.info(
        "build_counterfactual_residuals: aggregated to %d (trade, team, season) rows", len(agg)
    )
    return agg
