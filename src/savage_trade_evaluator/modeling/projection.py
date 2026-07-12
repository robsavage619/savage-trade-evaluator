"""Sample-size-aware WAR projection.

The production surface valued players by extrapolating whatever WAR they had
accumulated — including partial in-progress seasons and tiny hot samples. That
is exactly the naive-extrapolation error the project exists to beat: a starter
with 2.4 WAR in 10 starts is not a 7-WAR pitcher, and a closer with 1.2 WAR at
the season's midpoint has not declined.

This module produces a regressed, playing-time-weighted true-talent projection
using an empirical-Bayes shrinkage of the Marcel form:

    projected_full_season_rate =
        ( Σ war_i · recency_i  +  baseline · regression_pt )
        ────────────────────────────────────────────────────
        ( Σ pt_i  · recency_i  +  regression_pt )

where ``pt_i`` is a season's playing time as a fraction of a full season for the
role (so a 10-start sample carries a third of a full season's weight), and the
prior is ``regression_pt`` full seasons of a role ``baseline``. Small or partial
samples are pulled toward the baseline; full, repeated seasons dominate their
own projection.

``regression_pt`` is the shrinkage strength — the number of phantom
league-baseline seasons mixed in. The default is Marcel-like; it should be tuned
against backtest calibration before this feeds production valuation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# Full-season appearance anchors (BIP medians 2021-25 → ~474 SP / ~161 RP BIP;
# appearances are used instead of BIP because BIP is biased against high-K arms).
FULL_SEASON_STARTS: int = 32
FULL_SEASON_RELIEF_APP: int = 62

# Role true-talent anchors for regression (league-ish full-season WAR).
STARTER_BASELINE_WAR: float = 1.6
RELIEVER_BASELINE_WAR: float = 0.7

# Shrinkage strength: phantom full-baseline-seasons mixed in. Calibrated against
# 2841 pitcher Y->Y+1 pairs (scripts/calibrate_projection.py): ~21% MAE improvement
# over naive last-season WAR, at the elbow of the curve (both roles' MAE flattens
# past ~3; larger values overfit the tail). The residual downward bias is mostly a
# selection artifact of the eval (targets condition on a full next season). A
# playing-time-informed baseline is the follow-up to remove the rest.
DEFAULT_REGRESSION_PT: float = 3.0

# Marcel recency weights for the 3 most recent seasons (most recent first).
RECENCY_WEIGHTS: tuple[float, float, float] = (3.0, 2.0, 1.0)


@dataclass(frozen=True, slots=True)
class SeasonWar:
    """One season of WAR with its playing-time fraction.

    Attributes:
        season: Calendar season.
        war: WAR accumulated that season (may be a partial-season total).
        pt_fraction: Playing time as a fraction of a full season for the role
            (e.g. 10 of 32 starts → 0.31). May exceed 1.0 for a heavy workload.
        is_reliever: Whether the season was pitched in relief.
    """

    season: int
    war: float
    pt_fraction: float
    is_reliever: bool


@dataclass(frozen=True, slots=True)
class ProjectedWar:
    """Result of a true-talent projection.

    Attributes:
        full_season_war: Regressed full-season WAR rate.
        is_reliever: Role used for the baseline/leverage decision.
        seasons_used: Number of prior seasons that fed the projection.
        note: Human-readable note (e.g. flagged partial/small samples).
    """

    full_season_war: float
    is_reliever: bool
    seasons_used: int
    note: str


def playing_time_fraction(g: int, gs: int, *, is_reliever: bool) -> float:
    """Playing time as a fraction of a full season for the role.

    Args:
        g: Games (appearances) that season.
        gs: Games started that season.
        is_reliever: Whether to measure against a full relief workload.

    Returns:
        Fraction of a full season, using ``gs / 32`` for starters and
        ``g / 62`` for relievers.
    """
    if is_reliever:
        return g / FULL_SEASON_RELIEF_APP
    return gs / FULL_SEASON_STARTS


def project_war(
    seasons: list[SeasonWar],
    baseline: float,
    *,
    regression_pt: float = DEFAULT_REGRESSION_PT,
    recency_weights: tuple[float, ...] = RECENCY_WEIGHTS,
) -> float:
    """Empirical-Bayes true-talent WAR projection (pure; no DB).

    Args:
        seasons: Recent seasons, most-recent-first (up to ``len(recency_weights)``
            are used).
        baseline: Role true-talent anchor to regress toward.
        regression_pt: Shrinkage strength in phantom full-baseline-seasons.
        recency_weights: Recency multipliers applied most-recent-first.

    Returns:
        Regressed full-season WAR rate. Returns ``baseline`` when no seasons are
        supplied.
    """
    if not seasons:
        return baseline

    num = baseline * regression_pt
    den = regression_pt
    for season_war, weight in zip(seasons, recency_weights, strict=False):
        num += season_war.war * weight
        den += season_war.pt_fraction * weight

    if den <= 0:
        return baseline
    return num / den


def project_player(
    mlb_player_id: int,
    season: int,
    *,
    regression_pt: float = DEFAULT_REGRESSION_PT,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> ProjectedWar:
    """Project a pitcher's full-season true-talent WAR from the 3 latest seasons.

    Pulls ``season``, ``season-1``, ``season-2`` from ``bwar_pitching`` (summing
    stints), classifies each season's role from starts vs appearances, computes
    playing-time fractions, and regresses. The ``season`` row may be a partial
    in-progress total — its low playing-time fraction down-weights it correctly.

    Args:
        mlb_player_id: MLBAM player id.
        season: Season of the decision point (its in-progress total is used).
        regression_pt: Shrinkage strength in phantom full-baseline-seasons.
        conn: Optional open read-only connection.

    Returns:
        A :class:`ProjectedWar`.
    """
    if conn is None:
        with db.connect(read_only=True) as opened:
            return project_player(mlb_player_id, season, regression_pt=regression_pt, conn=opened)

    rows = conn.execute(
        """
        SELECT year_id, SUM(g) AS g, SUM(gs) AS gs, SUM(war) AS war
        FROM bwar_pitching
        WHERE mlb_id = ? AND year_id BETWEEN ? AND ?
        GROUP BY year_id
        ORDER BY year_id DESC
        """,
        [mlb_player_id, season - 2, season],
    ).fetchall()

    if not rows:
        return ProjectedWar(
            full_season_war=RELIEVER_BASELINE_WAR,
            is_reliever=True,
            seasons_used=0,
            note="no bwar_pitching rows — returned reliever baseline",
        )

    seasons: list[SeasonWar] = []
    total_g = 0
    total_gs = 0
    partial_flags: list[str] = []
    for year_id, g, gs, war in rows:
        g_i = int(g or 0)
        gs_i = int(gs or 0)
        war_f = float(war or 0.0)
        season_reliever = gs_i < g_i / 2
        pt = playing_time_fraction(g_i, gs_i, is_reliever=season_reliever)
        seasons.append(
            SeasonWar(season=int(year_id), war=war_f, pt_fraction=pt, is_reliever=season_reliever)
        )
        total_g += g_i
        total_gs += gs_i
        if pt < 0.5:
            partial_flags.append(f"{int(year_id)} ({pt:.2f} season)")

    is_reliever = total_gs < total_g / 2
    baseline = RELIEVER_BASELINE_WAR if is_reliever else STARTER_BASELINE_WAR
    projected = project_war(seasons, baseline, regression_pt=regression_pt)

    note = ""
    if partial_flags:
        note = "regressed partial/small samples: " + ", ".join(partial_flags)

    return ProjectedWar(
        full_season_war=projected,
        is_reliever=is_reliever,
        seasons_used=len(seasons),
        note=note,
    )
