"""R-47: contention window component decomposition.

R-45 showed receiver_contention_window_score is null on all outcomes.
Hypothesis: the product (prior_year_pyth_pct × (1 - payroll_pct_of_cap))
destroys signal — the two raw components may carry independent signal that
cancels in the composite.

Three ablations on war_delta:
  1. Composite only   — ACQUIRED_PLAYER_FEATURES + contention_window_score
  2. Components only  — ACQUIRED_PLAYER_FEATURES + prior_year_pyth_pct + payroll_pct_of_cap
  3. All three        — ACQUIRED_PLAYER_FEATURES + both components + composite
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v2.features import ACQUIRED_PLAYER_FEATURES
from savage_trade_evaluator.modeling.v3 import (
    V3BacktestResult,
    backtest_outcome_v3,
    coefficient_summary,
)

if "STE_DUCKDB_PATH" not in os.environ:
    os.environ["STE_DUCKDB_PATH"] = (
        "/Users/robsavage/Projects/savage-trade-evaluator"
        "/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db"
    )

CONTENTION_FEATURES = (
    "receiver_prior_year_pyth_pct",
    "receiver_payroll_pct_of_cap",
    "receiver_contention_window_score",
)

ABLATIONS: list[tuple[str, tuple[str, ...]]] = [
    (
        "composite_only",
        ACQUIRED_PLAYER_FEATURES + ("receiver_contention_window_score",),
    ),
    (
        "components_only",
        ACQUIRED_PLAYER_FEATURES + (
            "receiver_prior_year_pyth_pct",
            "receiver_payroll_pct_of_cap",
        ),
    ),
    (
        "all_three",
        ACQUIRED_PLAYER_FEATURES + CONTENTION_FEATURES,
    ),
]


def _contention_verdicts(result: V3BacktestResult) -> list[dict]:
    summary = coefficient_summary(result.fit)
    rows = []
    for feat in CONTENTION_FEATURES:
        row = summary[summary["feature"] == feat]
        if row.empty:
            rows.append({"feature": feat, "mean_beta": float("nan"), "p05": float("nan"),
                         "p95": float("nan"), "mass": float("nan"), "credible": False})
        else:
            r = row.iloc[0]
            rows.append({
                "feature": feat,
                "mean_beta": r["mean_beta"],
                "p05": r["p05"],
                "p95": r["p95"],
                "mass": r["directional_mass"],
                "credible": bool(r["credible"]),
            })
    return rows


def main() -> None:
    outcome = "war_delta"
    summary_rows: list[dict] = []

    for label, feature_cols in ABLATIONS:
        print()
        print("=" * 88)
        print(f"R-47 ablation: {label}  ({len(feature_cols)} features)")
        print("=" * 88)

        result = backtest_outcome_v3(outcome, feature_cols=feature_cols)

        print(f"  n_train={result.train_n}  n_test={result.test_n}")
        print(f"  coverage_90={result.coverage_90:.1%}  CRPS={result.test_crps:.4f}")

        verdicts = _contention_verdicts(result)
        for v in verdicts:
            if np.isnan(v["mean_beta"]):
                continue
            verdict_str = "CREDIBLE" if v["credible"] else "not credible"
            sign = "+" if v["mean_beta"] > 0 else ""
            print(
                f"    {v['feature']:<44}  beta={sign}{v['mean_beta']:.4f}"
                f"  [{v['p05']:+.3f}, {v['p95']:+.3f}]"
                f"  mass={v['mass']:.0%}  → {verdict_str}"
            )

        for v in verdicts:
            summary_rows.append({
                "ablation": label,
                "n_train": result.train_n,
                "n_test": result.test_n,
                "coverage_90": round(result.coverage_90, 3),
                "crps": round(result.test_crps, 4),
                "feature": v["feature"],
                "mean_beta": round(v["mean_beta"], 4) if not np.isnan(v["mean_beta"]) else float("nan"),
                "p05": round(v["p05"], 3) if not np.isnan(v["p05"]) else float("nan"),
                "p95": round(v["p95"], 3) if not np.isnan(v["p95"]) else float("nan"),
                "directional_mass": round(v["mass"], 3) if not np.isnan(v["mass"]) else float("nan"),
                "credible": v["credible"],
            })

    print()
    print("=" * 88)
    print("R-47 SUMMARY TABLE")
    print("=" * 88)
    df = pd.DataFrame(summary_rows)
    df = df[df["feature"].isin(CONTENTION_FEATURES)].reset_index(drop=True)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
