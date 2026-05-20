"""R-48 — structural over-dispersion diagnosis for war_delta.

V3 war_delta hits 97.9% coverage on the 90% CI target.
R-44 ruled out sigma prior tuning (coverage flat across sigma=[0.3..1.0]).
D-28 ruled out team random intercepts.

Three structural suspects tested here:
  1. Era variance shift — 2021-2024 test period compresses outcomes
     (pitch clock, shift ban, sticky-stuff crackdown).
  2. COVID 2020 inflation — shortened season bloats training sigma.
  3. Heteroscedasticity — variance grows with receiver_acquired_player_quality.

Checks 1 and 3 are pure pandas (fast).
Check 2 (refit with train_end_season=2019) is gated behind --run-mcmc.
"""

from __future__ import annotations

import argparse
import os

import pandas as pd

os.environ.setdefault(
    "STE_DUCKDB_PATH",
    "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db",
)


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def check1_era_variance(combined: pd.DataFrame) -> dict[str, float]:
    """Compare war_delta std across eras."""
    _section("Check 1 — Era variance comparison")

    col = "war_delta"
    df = combined[combined[col].notna()].copy()

    pre_2020 = df[df["trade_season"] < 2020][col]
    covid_2020 = df[df["trade_season"] == 2020][col]
    test_era = df[df["trade_season"].between(2021, 2024)][col]

    results = {
        "pre_2020_std": pre_2020.std(),
        "covid_2020_std": covid_2020.std(),
        "test_era_std": test_era.std(),
        "pre_2020_n": len(pre_2020),
        "covid_2020_n": len(covid_2020),
        "test_era_n": len(test_era),
        "pre_2020_mean": pre_2020.mean(),
        "covid_2020_mean": covid_2020.mean(),
        "test_era_mean": test_era.mean(),
    }

    print(f"\n{'Era':<20} {'n':>6} {'mean':>8} {'std':>8}")
    print("-" * 44)
    print(f"{'train (pre-2020)':<20} {int(results['pre_2020_n']):>6} {results['pre_2020_mean']:>8.3f} {results['pre_2020_std']:>8.3f}")
    print(f"{'COVID 2020':<20} {int(results['covid_2020_n']):>6} {results['covid_2020_mean']:>8.3f} {results['covid_2020_std']:>8.3f}")
    print(f"{'test (2021-2024)':<20} {int(results['test_era_n']):>6} {results['test_era_mean']:>8.3f} {results['test_era_std']:>8.3f}")

    ratio_covid = results["covid_2020_std"] / results["test_era_std"] if results["test_era_std"] > 0 else float("nan")
    ratio_pre = results["pre_2020_std"] / results["test_era_std"] if results["test_era_std"] > 0 else float("nan")
    print(f"\n  train-std / test-std  : {ratio_pre:.2f}x")
    print(f"  covid-std / test-std  : {ratio_covid:.2f}x")

    return results


def check2_drop_covid_refit() -> None:
    """Refit with train_end_season=2019 to isolate COVID inflation effect."""
    _section("Check 2 — Drop 2020 and refit (MCMC)")

    from savage_trade_evaluator.modeling.v3 import backtest_outcome_v3, print_backtest_report

    # receiver_acquired_contract_year_pct was added to ACQUIRED_PLAYER_FEATURES
    # but the underlying DB column doesn't exist in the current schema — exclude
    # it here so assemble_v3_combined() doesn't fail on a missing column.
    from savage_trade_evaluator.modeling.v3 import assemble_v3_combined, V3_OUTCOME_FEATURES
    combined = assemble_v3_combined()
    if "receiver_acquired_contract_year_pct" in combined.columns:
        pass  # column is live — no action needed
    else:
        from savage_trade_evaluator.modeling.v2.features import ALL_FEATURES
        feature_cols = tuple(c for c in ALL_FEATURES if c != "receiver_acquired_contract_year_pct")
    from savage_trade_evaluator.modeling.v3 import V3_OUTCOME_FEATURES
    feature_cols = tuple(
        c for c in V3_OUTCOME_FEATURES["war_delta"]
        if c != "receiver_acquired_contract_year_pct"
    )

    print("\n  --- Standard fit (train_end_season=2020) ---")
    result_2020 = backtest_outcome_v3("war_delta", train_end_season=2020, feature_cols=feature_cols)
    print_backtest_report(result_2020)

    print("\n  --- COVID-excluded fit (train_end_season=2019) ---")
    result_2019 = backtest_outcome_v3("war_delta", train_end_season=2019, feature_cols=feature_cols)
    print_backtest_report(result_2019)

    print(f"\n  coverage_90 (incl 2020): {result_2020.coverage_90:.3f}")
    print(f"  coverage_90 (excl 2020): {result_2019.coverage_90:.3f}")
    delta = result_2019.coverage_90 - result_2020.coverage_90
    print(f"  delta                  : {delta:+.3f}")

    if abs(delta) >= 0.02:
        direction = "closer to 90%" if delta < 0 else "further from 90%"
        print(f"\n  >>> COVID 2020 moves coverage {direction} — SUPPORTED as a cause.")
    else:
        print("\n  >>> Dropping 2020 has negligible effect — COVID not the primary cause.")


def check3_heteroscedasticity(combined: pd.DataFrame) -> dict[str, object]:
    """Bin test-era rows by receiver_acquired_player_quality quartile; compute std per bin."""
    _section("Check 3 — Heteroscedastic sigma by player quality")

    col = "war_delta"
    qcol = "receiver_acquired_player_quality"

    test = combined[
        combined["trade_season"].between(2021, 2024)
        & combined[col].notna()
        & combined[qcol].notna()
    ].copy()

    if test.empty:
        print("  No test-era rows with both war_delta and quality — cannot run check.")
        return {}

    test["quality_quartile"] = pd.qcut(test[qcol], q=4, labels=["Q1 (low)", "Q2", "Q3", "Q4 (high)"])

    stats = (
        test.groupby("quality_quartile", observed=True)[col]
        .agg(n="count", mean="mean", std="std")
        .reset_index()
    )

    print(f"\n{'Quartile':<14} {'n':>6} {'mean':>8} {'std':>8}")
    print("-" * 38)
    for _, row in stats.iterrows():
        print(f"{row['quality_quartile']!s:<14} {int(row['n']):>6} {row['mean']:>8.3f} {row['std']:>8.3f}")

    stds = stats["std"].dropna().tolist()
    ratio = max(stds) / min(stds) if min(stds) > 0 else float("nan")
    print(f"\n  Q4-std / Q1-std ratio  : {ratio:.2f}x")

    return {"std_ratio": ratio, "stats": stats}


def verdict(era_results: dict[str, float], hetero_results: dict[str, object]) -> None:
    _section("Verdict")

    suspects: list[str] = []

    if era_results:
        train_std = era_results["pre_2020_std"]
        covid_std = era_results["covid_2020_std"]
        test_std = era_results["test_era_std"]

        if test_std > 0 and train_std / test_std >= 1.3:
            suspects.append(
                f"ERA VARIANCE SHIFT — train std ({train_std:.3f}) is "
                f"{train_std/test_std:.1f}x test std ({test_std:.3f}). "
                "Model trained on wider distribution than it's predicting → over-wide CIs."
            )
        if test_std > 0 and covid_std / test_std >= 1.3:
            suspects.append(
                f"COVID 2020 INFLATION — 2020 std ({covid_std:.3f}) is "
                f"{covid_std/test_std:.1f}x test std ({test_std:.3f}). "
                "Run Check 2 (--run-mcmc) to confirm."
            )

    if hetero_results and "std_ratio" in hetero_results:
        ratio = hetero_results["std_ratio"]
        if ratio >= 2.0:
            suspects.append(
                f"HETEROSCEDASTICITY — Q4/Q1 std ratio = {ratio:.2f}x. "
                "High-quality player trades have much wider outcome spread. "
                "Fix: sigma = exp(alpha_sigma + beta_sigma * quality_z) in PyMC model."
            )

    if not suspects:
        print("\n  No structural suspect clears the threshold.")
        print("  Over-dispersion source remains unresolved — consider student-T likelihood.")
    else:
        print(f"\n  {len(suspects)} suspect(s) supported:\n")
        for i, s in enumerate(suspects, 1):
            print(f"  [{i}] {s}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="R-48 over-dispersion structural diagnosis")
    parser.add_argument(
        "--run-mcmc",
        action="store_true",
        default=False,
        help="Run Check 2 (drop 2020 refit) — slow, requires MCMC.",
    )
    args = parser.parse_args()

    from savage_trade_evaluator.modeling.v3 import assemble_v3_combined

    print("Loading assemble_v3_combined()...")
    combined = assemble_v3_combined()
    print(f"  {len(combined):,} rows loaded.")

    era_results = check1_era_variance(combined)

    if args.run_mcmc:
        check2_drop_covid_refit()
    else:
        _section("Check 2 — Drop 2020 and refit (SKIPPED)")
        print("  Pass --run-mcmc to run this check.")

    hetero_results = check3_heteroscedasticity(combined)

    verdict(era_results, hetero_results)


if __name__ == "__main__":
    main()
