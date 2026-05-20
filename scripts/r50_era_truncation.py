"""R-50 — post-2015 training truncation for war_delta coverage fix.

war_delta coverage is 97.9-98.0% vs 90% target.
R-48 confirmed era variance shift is the cause: training std=2.23 vs test
std=1.27 (1.76x).  R-48 also showed dropping 2020 alone moved coverage only
-0.4pp.

Hypothesis: removing pre-Statcast/pre-TrackMan seasons (pre-2015) from the
training window reduces training variance toward the 2021-2024 test regime and
brings coverage closer to 90%.

Three windows tested:
  Full       2010-2020  (current baseline)
  Post-2013  2014-2020
  Post-2015  2015-2020  (Statcast era begins)
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import os

os.environ.setdefault(
    "STE_DUCKDB_PATH",
    "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db",
)

from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    backtest_outcome_v3,
)

_WINDOWS: tuple[tuple[str, int], ...] = (
    ("Full (2010-2020)", 2010),
    ("Post-2013 (2014-2020)", 2014),
    ("Post-2015 (2015-2020)", 2015),
)

_OUTCOME = "war_delta"


def _feature_cols(combined: object) -> tuple[str, ...]:
    import pandas as pd

    df = combined  # type: ignore[assignment]
    all_cols = V3_OUTCOME_FEATURES[_OUTCOME]
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"expected DataFrame, got {type(df)}")
    if "receiver_acquired_contract_year_pct" not in df.columns:
        return tuple(c for c in all_cols if c != "receiver_acquired_contract_year_pct")
    return all_cols


def main() -> None:
    print(f"R-50 — era truncation sweep for outcome={_OUTCOME}")
    print("Assembling combined feature+outcome matrix … (shared across all runs)")
    combined = assemble_v3_combined()
    cols = _feature_cols(combined)

    rows: list[dict[str, object]] = []
    for label, start_season in _WINDOWS:
        print(f"\n--- {label} ---")
        result = backtest_outcome_v3(
            _OUTCOME,
            train_end_season=2020,
            test_end_season=2024,
            feature_cols=cols,
            combined=combined,
            train_start_season=start_season,
        )
        credible_n = int(result.credible_features["credible"].sum())
        rows.append(
            {
                "window": label,
                "train_start": start_season,
                "train_n": result.train_n,
                "test_n": result.test_n,
                "coverage_90": result.coverage_90,
                "crps": result.test_crps,
                "credible_n": credible_n,
            }
        )
        print(
            f"  train_n={result.train_n}  test_n={result.test_n}"
            f"  coverage={result.coverage_90:.3f}  crps={result.test_crps:.4f}"
            f"  credible_features={credible_n}"
        )

    print("\n" + "=" * 88)
    print("SUMMARY TABLE")
    print("=" * 88)
    header = (
        f"{'train_start':>11}  {'train_n':>8}  {'test_n':>7}"
        f"  {'coverage_90':>12}  {'CRPS':>8}  {'credible_n':>10}"
    )
    print(header)
    print("-" * 88)
    for r in rows:
        print(
            f"{r['train_start']!s:>11}  {r['train_n']!s:>8}  {r['test_n']!s:>7}"
            f"  {r['coverage_90']:.3f}{'':>8}  {r['crps']:.4f}{'':>3}  {r['credible_n']!s:>10}"
        )
    print()

    coverages = [r["coverage_90"] for r in rows]
    closest = min(rows, key=lambda r: abs(float(r["coverage_90"]) - 0.90))  # type: ignore[arg-type]
    print(f"Closest to 90% target: {closest['window']} → coverage={closest['coverage_90']:.3f}")


if __name__ == "__main__":
    main()
