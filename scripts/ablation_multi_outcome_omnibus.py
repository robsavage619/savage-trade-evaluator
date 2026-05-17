"""R-20/21/22/23/24: omnibus ablation across four outcome variables.

Reframes the entire prior ablation program against R-19's discovery: outcomes
matter more than features at our sample size. For each outcome, fit the FULL
feature set (15 features), report all coefficients sorted by directional mass.

Outcomes tested:
  R-20  WAR-surplus (baseline; sanity check + re-analysis of WAR-null features)
  R-21  xERA-delta (pitcher rate-based; D-26 compliant)
  R-22  K%-delta (pitcher rate-based percentile; D-26 compliant)
  R-23  xwOBA-surplus (rate-based surplus baseline; new view; D-26 compliant)

R-24 (within-team pitcher arsenal features) is tested implicitly — both
receiver_acquired_pitcher_k_trajectory and receiver_acquired_pitcher_arsenal_volatility
are in FEATURE_COLUMNS and will show up in the coefficient tables.

Per D-26: coefficient credibility (90% CI excludes zero AND >=95% directional
mass) is the primary signal. CRPS movement on small test sets is secondary.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.modeling.context_aware import FEATURE_COLUMNS
from savage_trade_evaluator.storage import db

ALL_FEATURES = list(FEATURE_COLUMNS)
SEED = 137


@dataclass(frozen=True, slots=True)
class OutcomeSpec:
    """One Y-variable specification."""

    label: str
    outcome_sql: str
    join_clause: str = ""


OUTCOMES = (
    OutcomeSpec(
        label="WAR-surplus (R-20)",
        outcome_sql="twc.surplus AS outcome",
    ),
    OutcomeSpec(
        label="xERA-delta (R-21)",
        outcome_sql="tex.xera_delta_mean AS outcome",
        join_clause=(
            "JOIN trade_xera_outcome tex "
            "ON tex.trade_event_id = twc.trade_event_id "
            "AND tex.receiver_bref = twc.receiver_bref "
        ),
    ),
    OutcomeSpec(
        label="K%-delta (R-22)",
        outcome_sql="tkp.kpct_delta_mean AS outcome",
        join_clause=(
            "JOIN trade_kpct_outcome tkp "
            "ON tkp.trade_event_id = twc.trade_event_id "
            "AND tkp.receiver_bref = twc.receiver_bref "
        ),
    ),
    OutcomeSpec(
        label="xwOBA-surplus (R-23)",
        outcome_sql="txs.xwoba_surplus AS outcome",
        join_clause=(
            "JOIN trade_xwoba_surplus txs "
            "ON txs.trade_event_id = twc.trade_event_id "
            "AND txs.receiver_bref = twc.receiver_bref "
        ),
    ),
    OutcomeSpec(
        label="xwOBA-delta (R-19 replicate)",
        outcome_sql="txo.xwoba_delta_mean AS outcome",
        join_clause=(
            "JOIN trade_xwoba_outcome txo "
            "ON txo.trade_event_id = twc.trade_event_id "
            "AND txo.receiver_bref = twc.receiver_bref "
        ),
    ),
)


def load_subset(spec: OutcomeSpec) -> pd.DataFrame:
    """Load (outcome, features) for one outcome variable."""
    query = f"""
        SELECT twc.trade_event_id, twc.trade_season, twc.receiver_bref,
               {spec.outcome_sql},
               {", ".join("twc." + c for c in ALL_FEATURES)}
        FROM trade_with_context twc
        {spec.join_clause}
        WHERE {" AND ".join(f"twc.{c} IS NOT NULL" for c in ALL_FEATURES)}
    """
    with db.connect(read_only=True) as conn:
        df = conn.execute(query).df()
    df = df[df["outcome"].notna()].reset_index(drop=True)
    return df


def fit(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Fit multilevel model; return beta posterior samples and feature names."""
    feature_cols = ALL_FEATURES
    means = df[feature_cols].mean()
    stds = df[feature_cols].std().replace(0, 1.0)
    x = ((df[feature_cols] - means) / stds).to_numpy(dtype=float)
    y = df["outcome"].to_numpy(dtype=float)
    y_scale = float(y.std()) or 1.0

    teams = sorted(set(df["receiver_bref"]))
    t2i = {t: i for i, t in enumerate(teams)}
    t_idx = np.array([t2i[t] for t in df["receiver_bref"]])

    with pm.Model(coords={"team": teams, "feature": feature_cols}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=y_scale)
        tau = pm.HalfNormal("tau_team", sigma=y_scale)
        sigma = pm.HalfNormal("sigma", sigma=y_scale * 2)
        alpha_team = pm.Normal("alpha_team", mu=0.0, sigma=tau, dims="team")
        beta = pm.Normal("beta", mu=0.0, sigma=y_scale / 2, dims="feature")
        mu = alpha + alpha_team[t_idx] + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y)
        trace = pm.sample(
            draws=1500,
            tune=2000,
            chains=4,
            random_seed=SEED,
            progressbar=False,
            target_accept=0.97,
        )

    beta_s = trace.posterior["beta"].values.reshape(-1, len(feature_cols))
    return beta_s, feature_cols


def report(label: str, df: pd.DataFrame, beta_s: np.ndarray, feature_cols: list[str]) -> None:
    """Print per-feature coefficient table for one outcome."""
    print("=" * 86)
    print(f"OUTCOME: {label}    n={len(df)}    y_scale={df['outcome'].std():.4f}")
    print("=" * 86)
    rows = []
    for i, name in enumerate(feature_cols):
        v = beta_s[:, i]
        mass = max((v > 0).mean(), (v < 0).mean())
        rows.append((mass, name, v.mean(), np.percentile(v, 5), np.percentile(v, 95)))
    rows.sort(reverse=True)
    for mass, name, mean, p5, p95 in rows:
        credible = mass >= 0.975
        flag = "*** CREDIBLE" if credible else ("  directional" if mass >= 0.85 else "")
        print(
            f"  mass={mass:>4.0%}  {name:<54} {mean:>+9.5f}  [{p5:>+8.5f}, {p95:>+8.5f}]   {flag}"
        )
    print()


def main() -> None:
    """Run omnibus ablation across five outcomes."""
    for spec in OUTCOMES:
        df = load_subset(spec)
        if len(df) < 50:
            print(f"\nSKIPPING {spec.label}: n={len(df)} too small\n")
            continue
        print(f"\nFitting {spec.label} (n={len(df)})...")
        beta_s, feature_cols = fit(df)
        report(spec.label, df, beta_s, feature_cols)


if __name__ == "__main__":
    main()
