"""R-27: Regime-control reruns of R-12/13/17 and R-22 findings.

Per D-28, the V2 architectural fix is clustering on (team, GM-regime) instead
of just team. R-25 showed 90% of within-team variance is regime-driven; the
clean LAD-vs-HOU/CLE pairwise from R-17 and the credible k_trajectory finding
from R-22 may both partly reflect specific regime overlaps.

This script reruns the origin-org system-tax test using regime_id as the
cluster on three outcome variables (WAR, xwOBA, K%) and reports both
per-regime intercepts AND pairwise probabilities for the regimes Rob cares
about most:
  - Friedman LAD (2015+)
  - Luhnow HOU (2012-2019)
  - Click HOU (2020-2022)
  - Antonetti CLE (2016+)
  - Shapiro CLE (2010-2015)

Plain-English question: which of our prior findings survive regime control?
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
MIN_N_PER_REGIME = 6


HIGHLIGHT_REGIMES = (
    "LAD_Andrew Friedman",
    "LAD_Ned Colletti",
    "HOU_Jeff Luhnow",
    "HOU_James Click",
    "HOU_Dana Brown",
    "CLE_Chris Antonetti",
    "CLE_Mark Shapiro",
    "TBR_Andrew Friedman",  # if anywhere
    "SDP_A. J. Preller",
    "OAK_Billy Beane",
    "STL_John Mozeliak",
    "BOS_Theo Epstein",
    "BOS_Ben Cherington",
    "BOS_Chaim Bloom",
)


@dataclass(frozen=True, slots=True)
class OutcomeSpec:
    """One Y-variable specification for the regime-control rerun."""

    label: str
    sql: str


OUTCOMES: tuple[OutcomeSpec, ...] = (
    OutcomeSpec(
        "WAR",
        """
        SELECT tpu.from_team_bref AS origin_team,
               tra.regime_id AS origin_regime,
               tpu.trade_season,
               w.war_t_minus_1 AS pre,
               (w.war_t_plus_1 - w.war_t_minus_1) AS delta
        FROM trade_player_war_window w
        JOIN trade_player_unified tpu
            ON tpu.trade_event_id = w.trade_event_id
            AND tpu.leg_index = w.leg_index
        JOIN team_regime_assignments tra
            ON tra.bref_code = tpu.from_team_bref
            AND tra.season = tpu.trade_season
        WHERE w.war_t_minus_1 IS NOT NULL
          AND w.war_t_plus_1 IS NOT NULL
          AND tra.regime_id IS NOT NULL
        """,
    ),
    OutcomeSpec(
        "xwOBA",
        """
        SELECT w.from_team_bref AS origin_team,
               tra.regime_id AS origin_regime,
               w.trade_season,
               w.xwoba_t_minus_1 AS pre,
               (w.xwoba_t_plus_1 - w.xwoba_t_minus_1) AS delta
        FROM trade_player_xwoba_window w
        JOIN team_regime_assignments tra
            ON tra.bref_code = w.from_team_bref
            AND tra.season = w.trade_season
        WHERE w.xwoba_t_minus_1 IS NOT NULL
          AND w.xwoba_t_plus_1 IS NOT NULL
        """,
    ),
    OutcomeSpec(
        "K%",
        """
        SELECT w.from_team_bref AS origin_team,
               tra.regime_id AS origin_regime,
               w.trade_season,
               w.k_percent_t_minus_1 AS pre,
               (w.k_percent_t_plus_1 - w.k_percent_t_minus_1) AS delta
        FROM trade_player_arsenal_window w
        JOIN team_regime_assignments tra
            ON tra.bref_code = w.from_team_bref
            AND tra.season = w.trade_season
        WHERE w.k_percent_t_minus_1 IS NOT NULL
          AND w.k_percent_t_plus_1 IS NOT NULL
        """,
    ),
)


def load(spec: OutcomeSpec) -> pd.DataFrame:
    """Load and apply MIN_N filter to one outcome."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(spec.sql).df()
    counts = df.groupby("origin_regime").size()
    keep = counts[counts >= MIN_N_PER_REGIME].index
    return df[df["origin_regime"].isin(keep)].reset_index(drop=True)


def fit(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Fit multilevel model with regime cluster. Return alpha_regime samples + regime list."""
    regimes = sorted(df["origin_regime"].unique())
    r2i = {r: i for i, r in enumerate(regimes)}
    r_idx = np.array([r2i[r] for r in df["origin_regime"]])

    pre_z = (df["pre"] - df["pre"].mean()) / df["pre"].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    y = df["delta"].to_numpy(dtype=float)
    y_scale = float(y.std()) or 1.0

    with pm.Model(coords={"regime": regimes}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=y_scale)
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=y_scale * 2)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=y_scale)
        tau = pm.HalfNormal("tau_regime", sigma=y_scale)
        alpha_regime = pm.Normal("alpha_regime", mu=0.0, sigma=tau, dims="regime")
        sigma = pm.HalfNormal("sigma", sigma=y_scale * 2)
        mu = (
            alpha
            + alpha_regime[r_idx]
            + beta_pre * pre_z.to_numpy(dtype=float)
            + beta_season * season_z.to_numpy(dtype=float)
        )
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y)
        trace = pm.sample(
            draws=2000,
            tune=2000,
            chains=4,
            random_seed=SEED,
            progressbar=False,
            target_accept=0.97,
        )

    ar = trace.posterior["alpha_regime"].values.reshape(-1, len(regimes))
    return ar, regimes


def report_regimes(label: str, df: pd.DataFrame, ar: np.ndarray, regimes: list[str]) -> None:
    """Print per-regime intercepts for highlight regimes."""
    print(f"\n=== {label} — per-regime intercepts (highlight set) ===")
    print(f"  outcome scale: {df['delta'].std():.4f}, n={len(df)}, regimes={len(regimes)}")
    print(f"  {'regime':<35} {'n':>4} {'mean':>9} {'90% CI':>22} {'P(<0)':>7}")
    for hl in HIGHLIGHT_REGIMES:
        if hl in regimes:
            i = regimes.index(hl)
            samples = ar[:, i]
            n = int((df["origin_regime"] == hl).sum())
            print(
                f"  {hl:<35} {n:>4} {samples.mean():>+9.4f}  "
                f"[{np.percentile(samples, 5):>+7.4f}, {np.percentile(samples, 95):>+7.4f}]  "
                f"{(samples < 0).mean():>6.1%}"
            )


def report_pairwise(label: str, ar: np.ndarray, regimes: list[str]) -> None:
    """Print Friedman-LAD-vs-other pairwise probabilities."""
    print(f"\n=== {label} — Friedman-LAD vs other regimes pairwise ===")
    anchor = "LAD_Andrew Friedman"
    if anchor not in regimes:
        print(f"  {anchor} not in {label} sample")
        return
    a_samples = ar[:, regimes.index(anchor)]
    for hl in HIGHLIGHT_REGIMES:
        if hl == anchor or hl not in regimes:
            continue
        diff = a_samples - ar[:, regimes.index(hl)]
        print(
            f"  Friedman-LAD vs {hl:<32}  P(LAD < other) = {(diff < 0).mean():>5.1%}  "
            f"diff mean={diff.mean():+.4f}"
        )


def main() -> None:
    """Run regime-control rerun across three outcomes."""
    for spec in OUTCOMES:
        df = load(spec)
        if len(df) < 100:
            print(f"\nSKIPPING {spec.label}: n={len(df)} too small")
            continue
        print(f"\nFitting {spec.label} (n={len(df)}, {df['origin_regime'].nunique()} regimes)...")
        ar, regimes = fit(df)
        report_regimes(spec.label, df, ar, regimes)
        report_pairwise(spec.label, ar, regimes)


if __name__ == "__main__":
    main()
