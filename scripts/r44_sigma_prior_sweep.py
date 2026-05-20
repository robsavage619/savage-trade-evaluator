from __future__ import annotations

from savage_trade_evaluator.modeling.v3 import backtest_outcome_v3, print_backtest_report


def main() -> None:
    sigma_values = [0.3, 0.5, 0.75, 1.0]
    rows: list[tuple[float, float, float, int]] = []

    for sp in sigma_values:
        print(f"\n{'=' * 60}")
        print(f"sigma_prior={sp}")
        print("=" * 60)
        result = backtest_outcome_v3("war_delta", sigma_prior=sp)
        print_backtest_report(result)
        n_credible = int(result.credible_features["credible"].sum())
        rows.append((sp, result.coverage_90, result.test_crps, n_credible))

    print("\n\nSummary")
    print("-" * 52)
    print(f"{'sigma_prior':>12} {'coverage_90':>12} {'test_crps':>10} {'credible_n':>10}")
    print("-" * 52)
    for sp, cov, crps, n in rows:
        print(f"{sp:>12.2f} {cov:>12.3f} {crps:>10.4f} {n:>10d}")
    print("-" * 52)


if __name__ == "__main__":
    main()
