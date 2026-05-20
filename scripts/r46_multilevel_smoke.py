"""R-46: V3-multilevel smoke test.

Runs ``backtest_outcome_v3_multilevel`` on ``war_delta`` with a small
sampler budget (draws=200, tune=300, chains=2) to confirm the architecture
builds, samples without error, and produces sensible diagnostics.

Prints coverage_90, CRPS, and credible feature count.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np

from savage_trade_evaluator.modeling.v3_multilevel import backtest_outcome_v3_multilevel


def main() -> None:
    print("R-46: V3-multilevel smoke test (draws=200, tune=300, chains=2)")
    print("=" * 72)

    result = backtest_outcome_v3_multilevel(
        "war_delta",
        draws=200,
        tune=300,
        chains=2,
    )

    cred = result.credible_features[result.credible_features["credible"]]
    n_credible = len(cred)

    print(f"outcome      : {result.outcome}")
    print(f"train_n      : {result.train_n}")
    print(f"test_n       : {result.test_n}")
    print(f"coverage_90  : {result.coverage_90:.1%}  (target: 90%)")
    print(f"CRPS         : {result.test_crps:.4f}")
    print(f"MAE          : {result.test_mae:.4f}")
    print(f"credible features (D-26): {n_credible}")

    if n_credible:
        print()
        print("CREDIBLE FEATURES:")
        for _, r in cred.iterrows():
            sign = "+" if r["mean_beta"] > 0 else ""
            print(
                f"  *** {r['feature']:<48}  beta={sign}{r['mean_beta']:.4f}  "
                f"[{r['p05']:+.3f}, {r['p95']:+.3f}]  mass={r['directional_mass']:.0%}"
            )

    # Print sigma_team posterior summary to assess whether team pooling
    # is adding non-trivial variance (expected to be near zero per R-34/35).
    post = result.fit.trace.posterior
    sigma_team_samples = post["sigma_team"].values.reshape(-1)
    print()
    print(f"sigma_team mean : {float(sigma_team_samples.mean()):.4f}")
    print(
        f"sigma_team 90CI : [{float(np.percentile(sigma_team_samples, 5)):.4f}, "
        f"{float(np.percentile(sigma_team_samples, 95)):.4f}]"
    )
    print()
    print("Done.")


if __name__ == "__main__":
    main()
