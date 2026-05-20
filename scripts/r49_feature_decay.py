"""R-49 — Market-efficiency feature decay diagnostic.

Tests whether ``receiver_org_pitcher_k_jump_3yr`` and
``receiver_acquired_pitcher_k_trajectory`` are losing predictive power
over time (vault synthesis thesis: novel → exploited → priced-in within
~1 off-season post-2015).

Default mode: pure-pandas rolling-correlation table — no MCMC, runs immediately.
--run-mcmc: era-split V3 fits on kpct_delta; compares directional mass across
            two eras to detect decaying posterior signal.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
from scipy import stats

os.environ.setdefault(
    "STE_DUCKDB_PATH",
    "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db",
)

from savage_trade_evaluator.modeling.v2.features import ACQUIRED_PLAYER_FEATURES
from savage_trade_evaluator.modeling.v3 import assemble_v3_combined

DECAY_FEATURES = (
    "receiver_org_pitcher_k_jump_3yr",
    "receiver_acquired_pitcher_k_trajectory",
)
OUTCOMES = ("war_delta", "kpct_delta")
WINDOW_SIZE = 3  # rolling window width in seasons
FIRST_SEASON = 2010
LAST_SEASON = 2024


# ---------------------------------------------------------------------------
# Rolling-correlation helper
# ---------------------------------------------------------------------------

def _rolling_corr_table(df: pd.DataFrame, feature: str, outcome: str) -> pd.DataFrame:
    """Compute Pearson r between feature and outcome for each 3-year rolling window."""
    rows: list[dict] = []
    for start in range(FIRST_SEASON, LAST_SEASON - WINDOW_SIZE + 2):
        end = start + WINDOW_SIZE - 1
        window = df[(df["trade_season"] >= start) & (df["trade_season"] <= end)].copy()
        window = window[[feature, outcome]].dropna()
        n = len(window)
        if n < 10:
            rows.append({"window": f"{start}-{end}", "n": n, "r": float("nan"), "p": float("nan")})
            continue
        r, p = stats.pearsonr(window[feature], window[outcome])
        rows.append({"window": f"{start}-{end}", "n": n, "r": round(r, 4), "p": round(p, 4)})
    return pd.DataFrame(rows)


def _abs_trend_slope(table: pd.DataFrame) -> float:
    """OLS slope of |r| vs window index — negative = declining predictive power."""
    valid = table.dropna(subset=["r"])
    if len(valid) < 3:
        return float("nan")
    x = np.arange(len(valid), dtype=float)
    y = valid["r"].abs().values
    slope, *_ = np.polyfit(x, y, 1)
    return float(slope)


def _verdict(slope: float) -> str:
    if np.isnan(slope):
        return "too noisy to judge"
    if slope < -0.005:
        return "declining"
    if slope > 0.005:
        return "stable"
    return "too noisy to judge"


# ---------------------------------------------------------------------------
# MCMC era-split (gated behind --run-mcmc)
# ---------------------------------------------------------------------------

def _run_mcmc_era_split(df: pd.DataFrame) -> None:
    from savage_trade_evaluator.modeling.v3 import coefficient_summary, fit_v3

    target_feature = "receiver_acquired_pitcher_k_trajectory"
    outcome = "kpct_delta"
    feature_cols = ACQUIRED_PLAYER_FEATURES

    eras: list[tuple[str, int, int]] = [
        ("early (2015-2018 train / 2019-2021 test)", 2015, 2018),
        ("late  (2018-2021 train / 2022-2024 test)", 2018, 2021),
    ]

    print("\n" + "=" * 72)
    print("MCMC ERA-SPLIT — kpct_delta / receiver_acquired_pitcher_k_trajectory")
    print("=" * 72)

    mass_by_era: list[tuple[str, float]] = []
    for label, train_start, train_end in eras:
        train = df[
            (df["trade_season"] >= train_start)
            & (df["trade_season"] <= train_end)
            & df[outcome].notna()
        ].copy()

        present = train[list(feature_cols)].notna().sum(axis=1)
        train = train[present >= 5].copy()
        for c in feature_cols:
            train[c] = train[c].astype("float64").fillna(train[c].mean())

        if len(train) < 50:
            print(f"  {label}: SKIPPED — only {len(train)} train rows")
            continue

        print(f"\n  Fitting {label}  (n_train={len(train)}) …")
        fit = fit_v3(train, outcome, feature_cols)
        summary = coefficient_summary(fit)
        row = summary[summary["feature"] == target_feature]
        if row.empty:
            print(f"  {label}: feature not found in summary")
            continue
        mass = float(row["directional_mass"].iloc[0])
        mean_beta = float(row["mean_beta"].iloc[0])
        mass_by_era.append((label, mass))
        print(
            f"  {label}:  directional_mass={mass:.1%}  mean_beta={mean_beta:+.4f}"
        )

    if len(mass_by_era) == 2:
        delta = mass_by_era[1][1] - mass_by_era[0][1]
        if delta < -0.05:
            mcmc_verdict = "declining"
        elif delta > 0.05:
            mcmc_verdict = "stable"
        else:
            mcmc_verdict = "too noisy to judge"
        print(
            f"\n  Δ directional_mass (late − early): {delta:+.1%} → {target_feature} "
            f"signal appears {mcmc_verdict} over time."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="R-49 feature decay diagnostic")
    parser.add_argument(
        "--run-mcmc",
        action="store_true",
        default=False,
        help="Run era-split V3 MCMC fits in addition to the rolling-correlation table.",
    )
    args = parser.parse_args()

    print("Loading V3 combined feature+outcome matrix …")
    df = assemble_v3_combined()
    print(f"  Rows loaded: {len(df)}   Seasons: {int(df['trade_season'].min())}–{int(df['trade_season'].max())}")

    verdicts: dict[str, dict[str, str]] = {}

    for feature in DECAY_FEATURES:
        if feature not in df.columns:
            print(f"\n  WARNING: {feature} not present in dataset — skipping.")
            continue
        verdicts[feature] = {}
        for outcome in OUTCOMES:
            if outcome not in df.columns:
                continue
            table = _rolling_corr_table(df, feature, outcome)
            slope = _abs_trend_slope(table)
            v = _verdict(slope)
            verdicts[feature][outcome] = v

            print(f"\n{'=' * 72}")
            print(f"FEATURE: {feature}")
            print(f"OUTCOME: {outcome}   (slope of |r|: {slope:+.5f}  → {v})")
            print(f"{'=' * 72}")
            print(table.to_string(index=False))

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for feature in DECAY_FEATURES:
        if feature not in verdicts:
            continue
        for outcome, v in verdicts[feature].items():
            short = feature.replace("receiver_", "")
            print(f"  {short:<52}  [{outcome}]  {v}")

    # Plain-English top-line verdict — keyed on the canonical pairing
    # (k_trajectory × kpct_delta) which R-40/R-43 identified as most sensitive.
    key_feature = "receiver_acquired_pitcher_k_trajectory"
    key_outcome = "kpct_delta"
    top_verdict = verdicts.get(key_feature, {}).get(key_outcome, "too noisy to judge")
    print(
        f"\nk_trajectory signal appears {top_verdict} over time."
    )

    if args.run_mcmc:
        _run_mcmc_era_split(df)


if __name__ == "__main__":
    main()
