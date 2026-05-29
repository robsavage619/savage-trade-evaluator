"""Role-adjusted value: strip deployment inflation from post-trade pitcher value.

A traded pitcher's post-trade WAR change is largely a function of the role his
new team assigns him — innings volume and leverage — not skill the team acquired
(see ``frontend/src/data/model/reliever_role_decomposition.json``: role explains
~18-22% of reliever WAR change, underlying skill <1%). This module provides a
post-hoc confound control: it partials the deployment change out of a realized
value outcome, leaving the role-adjusted (skill-attributable) residual.

IMPORTANT — explanatory use only. The deployment deltas are computed from the
post-trade season (``t+1``), so they are NOT admissible as predictors in the
pre-trade V3 forecasting model (that would be target leakage). Use this strictly
for attribution: e.g. re-ranking GMs by role-adjusted acquired-pitcher value, or
auditing how much of a trade's apparent value is role inflation.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

# Post-trade deployment-change columns partialled out by default.
DEPLOYMENT_COLS: tuple[str, ...] = ("bf_delta", "lev_delta")


def build_pitcher_deployment_deltas() -> pd.DataFrame:
    """Assemble per-traded-pitcher deployment change, WAR change, and receiver GM.

    Deployment comes from Retrosheet play-by-play (``retrosheet_game_appearances``),
    bridged to MLBAM ids via ``chadwick_register``. Pre window is the season before
    the trade (``t-1``) with the origin team; post is the season after (``t+1``)
    with the receiver. WAR change is player-level from ``trade_player_war_window``.

    Returns:
        DataFrame with one row per traded pitcher-leg that has complete pre/post
        deployment and WAR. Columns: ``mlb_player_id``, ``trade_season``,
        ``to_team_bref``, ``gm``, ``war_delta``, ``bf_delta`` (change in batters
        faced), ``lev_delta`` (change in batters-faced-weighted avg leverage index),
        and ``reliever_frac_pre`` (pre-trade reliever-appearance fraction).
    """
    with db.connect(read_only=True) as conn:
        dep = conn.execute(
            """
            SELECT r.pitcher_id, r.season,
                   sum(r.n_batters_faced)                                   AS bf,
                   sum(r.n_batters_faced * r.avg_li)
                       / nullif(sum(r.n_batters_faced), 0)                  AS w_avg_li,
                   avg(CASE WHEN r.is_reliever THEN 1.0 ELSE 0.0 END)       AS reliever_frac
            FROM retrosheet_game_appearances r
            GROUP BY r.pitcher_id, r.season
            """
        ).df()
        bridge = conn.execute(
            """
            SELECT retro_id, mlb_player_id
            FROM chadwick_register
            WHERE retro_id IS NOT NULL AND mlb_player_id IS NOT NULL
            """
        ).df()
        war = conn.execute(
            """
            SELECT mlb_player_id, trade_season, to_team_bref,
                   war_t_minus_1, war_t_plus_1
            FROM trade_player_war_window
            WHERE mlb_player_id IS NOT NULL
            """
        ).df()
        gm = conn.execute(
            """
            SELECT bref_code, season, person_name AS gm
            FROM front_office
            WHERE role = 'General Manager'
            """
        ).df()

    dep = dep.merge(bridge, left_on="pitcher_id", right_on="retro_id", how="inner")
    dep["mlb_player_id"] = dep["mlb_player_id"].astype("Int64")
    war["mlb_player_id"] = war["mlb_player_id"].astype("Int64")
    gm = gm.groupby(["bref_code", "season"], as_index=False).first()

    pre = dep.add_suffix("_pre").rename(columns={"mlb_player_id_pre": "mlb_player_id"})
    post = dep.add_suffix("_post").rename(columns={"mlb_player_id_post": "mlb_player_id"})

    out = war.merge(
        pre[["mlb_player_id", "season_pre", "bf_pre", "w_avg_li_pre", "reliever_frac_pre"]],
        on="mlb_player_id",
        how="left",
    )
    out = out.loc[out["season_pre"] == out["trade_season"] - 1]
    out = out.merge(
        post[["mlb_player_id", "season_post", "bf_post", "w_avg_li_post"]],
        on="mlb_player_id",
        how="left",
    )
    out = out.loc[out["season_post"] == out["trade_season"] + 1]

    out["war_delta"] = out["war_t_plus_1"] - out["war_t_minus_1"]
    out["bf_delta"] = out["bf_post"] - out["bf_pre"]
    out["lev_delta"] = out["w_avg_li_post"] - out["w_avg_li_pre"]
    out = out.dropna(subset=["war_delta", "bf_delta", "lev_delta"]).reset_index(drop=True)

    out = out.merge(
        gm, left_on=["to_team_bref", "trade_season"], right_on=["bref_code", "season"], how="left"
    )
    return out[
        [
            "mlb_player_id",
            "trade_season",
            "to_team_bref",
            "gm",
            "war_delta",
            "bf_delta",
            "lev_delta",
            "reliever_frac_pre",
        ]
    ].reset_index(drop=True)


def role_adjust(
    frame: pd.DataFrame,
    value_col: str = "war_delta",
    deployment_cols: tuple[str, ...] = DEPLOYMENT_COLS,
) -> pd.Series:
    """Partial deployment change out of a value outcome (role-adjusted residual).

    Fits an OLS of ``value_col`` on the deployment-change columns and returns the
    residuals re-centered to the original mean, so the result stays on the same
    scale as the input value. The residual is the portion of value NOT explained
    by the role (innings + leverage) the receiving team assigned.

    Args:
        frame: DataFrame containing ``value_col`` and ``deployment_cols``.
        value_col: Realized value outcome to adjust (e.g. ``war_delta``).
        deployment_cols: Post-trade deployment-change columns to partial out.

    Returns:
        Role-adjusted value as a Series aligned to ``frame``'s index.

    Raises:
        ValueError: If required columns are missing or fewer than 10 complete rows.
    """
    missing = [c for c in (value_col, *deployment_cols) if c not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing required columns: {missing}")

    sub = frame[[value_col, *deployment_cols]].dropna()
    if len(sub) < 10:
        raise ValueError(f"need >=10 complete rows to fit, got {len(sub)}")

    # Ordinary least squares via numpy — keeps the dependency footprint minimal.
    y = np.asarray(sub[value_col], dtype=float)
    design = np.column_stack(
        [np.ones(len(sub)), np.asarray(sub[list(deployment_cols)], dtype=float)]
    )
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum(resid**2)) / ss_tot if ss_tot > 0 else 0.0
    logger.info(
        "role_adjust: partialled %s out of %s (R^2=%.3f, n=%d)",
        deployment_cols,
        value_col,
        r2,
        len(sub),
    )
    adjusted = pd.Series(resid + y.mean(), index=sub.index)
    return adjusted.reindex(frame.index)
