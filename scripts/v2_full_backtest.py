"""V2 full backtest — all four outcomes + Pressly smoke check.

Bumps ``target_accept`` to 0.99 to suppress the xwOBA divergences seen in
the smoke test, then runs xwoba / kpct / war / dollar_surplus in series.

After fitting, looks up the Pressly trade (event 371509, HOU side) in each
outcome's test predictions when present, else prints its training-set
posterior; we expect a clear positive signal across all four.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np

from savage_trade_evaluator.modeling.v2.backtest import (
    OUTCOME_FEATURES,
    assemble_combined,
    backtest_outcome,
    print_backtest_report,
)
from savage_trade_evaluator.modeling.v2.features import filter_complete_cases

PRESSLY_EVENT_ID = 371509
PRESSLY_RECEIVER = "HOU"


def _pressly_check(outcome: str, result) -> None:  # noqa: ANN001
    """Posterior summary for the Pressly HOU 2018 trade (in-sample)."""
    fit = result.fit
    combined = assemble_combined()
    combined = combined[combined[outcome].notna()].copy()
    feature_cols = list(fit.feature_cols)
    for c in feature_cols:
        combined[c] = combined[c].astype("float64")
        combined[c] = combined[c].fillna(combined[c].mean())
    row = combined[
        (combined["trade_event_id"] == PRESSLY_EVENT_ID)
        & (combined["receiver_bref"] == PRESSLY_RECEIVER)
    ]
    if row.empty:
        print(f"  >>> PRESSLY HOU: no row found for {outcome}")
        return
    r = row.iloc[0]
    x_row = ((row[feature_cols] - fit.feature_means) / fit.feature_stds).to_numpy(
        dtype=float
    )[0]
    post = fit.trace.posterior
    n = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n)
    beta_s = post["beta"].values.reshape(n, len(feature_cols))
    alpha_regime_s = post["alpha_regime"].values.reshape(n, len(fit.regimes))
    regime_idx = {rg: i for i, rg in enumerate(fit.regimes)}.get(r["regime_id"], -1)
    team_alpha = alpha_regime_s[:, regime_idx] if regime_idx >= 0 else 0.0
    mu_z = alpha0_s + team_alpha + beta_s @ x_row
    samples = mu_z * fit.y_std + fit.y_mean
    print(
        f"  >>> PRESSLY HOU (in-sample): "
        f"true={r[outcome]:+.4f}  "
        f"pred_mean={float(samples.mean()):+.4f}  "
        f"[{float(np.percentile(samples, 5)):+.4f}, "
        f"{float(np.percentile(samples, 95)):+.4f}]  "
        f"regime={r['regime_id']}"
    )


def main() -> None:
    """Run V2 backtest across all four outcomes."""
    outcomes = ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus")
    results = {}
    for o in outcomes:
        print()
        print("#" * 88)
        print(f"# {o.upper()}")
        print("#" * 88)
        try:
            result = backtest_outcome(
                outcome=o,
                train_end_season=2020,
                test_end_season=2024,
                minimum_features_present=5,
            )
        except ValueError as e:
            print(f"  SKIPPED: {e}")
            continue
        print_backtest_report(result)
        results[o] = result

        # Pressly snapshot — 2018 trade falls in train split; pull a posterior
        # prediction directly from the fitted model on that row.
        _pressly_check(o, result)

    print()
    print("=" * 88)
    print("SUMMARY")
    print("=" * 88)
    for o, r in results.items():
        ncred = int(r.credible_features["credible"].sum())
        print(
            f"  {o:<16} train={r.train_n:>4} test={r.test_n:>4}  "
            f"MAE={r.test_mae:.4f}  CRPS={r.test_crps:.4f}  "
            f"cov90={r.coverage_90:.1%}  credible_features={ncred}"
        )


if __name__ == "__main__":
    main()
