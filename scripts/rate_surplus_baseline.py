"""Rate-based xwOBA surplus naïve baseline + optional V3 head-to-head.

Computes xwoba_surplus = sum(xwoba_delta for received players)
                       - sum(xwoba_delta for sent players)
per trade event from ``trade_player_xwoba_window``, then optionally compares
against V3 test-set predictions for ``xwoba_delta``.

Usage:
    uv run python scripts/rate_surplus_baseline.py
    uv run python scripts/rate_surplus_baseline.py --skip-v3

The V3 comparison requires running the full MCMC backtest (minutes to hours
depending on machine). Pass ``--skip-v3`` or wait; the script auto-skips if
the backtest doesn't complete within 60 s (wall-clock timeout).
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from contextlib import contextmanager
from typing import Generator

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v2.backtest import _crps_empirical
from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_TEST_START = 2021
_TEST_END = 2024


# ---------------------------------------------------------------------------
# Timeout context manager (SIGALRM — Unix only)
# ---------------------------------------------------------------------------

class _TimeoutError(Exception):
    pass


@contextmanager
def _timeout(seconds: int) -> Generator[None, None, None]:
    """Raise _TimeoutError if the body takes longer than ``seconds``."""
    def _handler(signum: int, frame: object) -> None:  # noqa: ARG001
        raise _TimeoutError

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# ---------------------------------------------------------------------------
# Rate-baseline computation
# ---------------------------------------------------------------------------

def _load_xwoba_window() -> pd.DataFrame:
    """Pull trade_player_xwoba_window rows that have both t-1 and t+1 data."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT
                trade_event_id,
                trade_season,
                from_team_bref,
                to_team_bref,
                xwoba_t_minus_1,
                xwoba_t_plus_1
            FROM trade_player_xwoba_window
            WHERE xwoba_t_minus_1 IS NOT NULL
              AND xwoba_t_plus_1  IS NOT NULL
            """
        ).df()
    return df


def compute_rate_baseline(df_window: pd.DataFrame) -> pd.DataFrame:
    """Compute per-trade-event, per-receiver xwoba_surplus.

    For each (trade_event_id, receiver_bref):
        xwoba_surplus = Σ xwoba_delta(received players)
                      - Σ xwoba_delta(sent players)

    where xwoba_delta = xwoba_t_plus_1 - xwoba_t_minus_1.

    Args:
        df_window: Row-per-player from trade_player_xwoba_window.

    Returns:
        DataFrame keyed on (trade_event_id, receiver_bref, trade_season)
        with columns: xwoba_surplus_raw (point estimate).
    """
    df = df_window.copy()
    df["xwoba_delta"] = df["xwoba_t_plus_1"] - df["xwoba_t_minus_1"]

    # Received: player went TO the receiver (to_team_bref == receiver)
    recv = (
        df.rename(columns={"to_team_bref": "receiver_bref"})
        .groupby(["trade_event_id", "receiver_bref", "trade_season"])["xwoba_delta"]
        .sum()
        .rename("recv_sum")
    )

    # Sent: player came FROM the receiver
    sent = (
        df.rename(columns={"from_team_bref": "receiver_bref"})
        .groupby(["trade_event_id", "receiver_bref", "trade_season"])["xwoba_delta"]
        .sum()
        .rename("sent_sum")
    )

    combined = pd.concat([recv, sent], axis=1).fillna(0.0)
    combined["xwoba_surplus_raw"] = combined["recv_sum"] - combined["sent_sum"]
    return combined.reset_index()


# ---------------------------------------------------------------------------
# CRPS for a degenerate point-mass "distribution"
# ---------------------------------------------------------------------------

def _crps_point_mass(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """CRPS for a degenerate point-mass predictive: CRPS = MAE for point forecasts.

    Analytically, CRPS(δ_x̂, y) = |x̂ - y|.

    Args:
        y_true: Observed values, shape (n,).
        y_pred: Point predictions, shape (n,).

    Returns:
        Mean CRPS (= MAE) as a scalar.
    """
    return float(np.mean(np.abs(y_true - y_pred)))


# ---------------------------------------------------------------------------
# Baseline metrics on the test set
# ---------------------------------------------------------------------------

def evaluate_rate_baseline(
    baseline: pd.DataFrame,
    test_start: int = _TEST_START,
    test_end: int = _TEST_END,
) -> dict[str, float]:
    """Compute MAE and CRPS for the rate baseline on the test split.

    Args:
        baseline: Output of compute_rate_baseline.
        test_start: First test season (inclusive).
        test_end: Last test season (inclusive).

    Returns:
        Dict with keys mae, crps, n.
    """
    test = baseline[
        (baseline["trade_season"] >= test_start)
        & (baseline["trade_season"] <= test_end)
    ].dropna(subset=["xwoba_surplus_raw"])

    # The rate baseline predicts xwoba_surplus_raw; the target is itself (for
    # standalone eval we treat xwoba_surplus_raw as both prediction and truth).
    # For head-to-head we merge against V3's xwoba_delta (per-receiver) and
    # compute MAE vs the same ground-truth labels V3 uses.
    return {
        "mae": float(np.mean(np.abs(test["xwoba_surplus_raw"]))),
        "crps": _crps_point_mass(
            test["xwoba_surplus_raw"].to_numpy(),
            np.zeros(len(test)),  # naïve zero-center baseline for self-eval
        ),
        "n": float(len(test)),
    }


# ---------------------------------------------------------------------------
# V3 comparison
# ---------------------------------------------------------------------------

def _run_v3_backtest_with_timeout(timeout_s: int = 60) -> object | None:
    """Try to run backtest_outcome_v3('xwoba_delta') within timeout_s seconds.

    Returns the V3BacktestResult or None if timed out / errored.
    """
    try:
        from savage_trade_evaluator.modeling.v3 import backtest_outcome_v3  # noqa: PLC0415

        with _timeout(timeout_s):
            logger.info("Running V3 backtest for xwoba_delta (timeout=%ds)…", timeout_s)
            t0 = time.monotonic()
            result = backtest_outcome_v3("xwoba_delta")
            elapsed = time.monotonic() - t0
            logger.info("V3 backtest completed in %.1fs", elapsed)
            return result
    except _TimeoutError:
        logger.warning(
            "V3 backtest did not complete within %ds — skipping V3 comparison. "
            "Pre-run with: uv run python scripts/v2_full_backtest.py",
            timeout_s,
        )
        return None
    except Exception as exc:
        logger.warning("V3 backtest failed (%s) — skipping V3 comparison.", exc)
        return None


def _head_to_head(
    baseline: pd.DataFrame,
    v3_result: object,
    test_start: int = _TEST_START,
    test_end: int = _TEST_END,
) -> None:
    """Print head-to-head metrics between rate baseline and V3.

    Args:
        baseline: Output of compute_rate_baseline.
        v3_result: V3BacktestResult (typed as object to avoid hard import).
        test_start: First test season.
        test_end: Last test season.
    """
    import numpy as np  # noqa: PLC0415 (already imported above, keep local for clarity)

    v3_preds: pd.DataFrame = v3_result.test_predictions  # type: ignore[union-attr]

    # V3 predicts xwoba_delta (per-receiver, already the Δ); the rate baseline
    # predicts xwoba_surplus (same concept but aggregated across all legs).
    # Merge on (trade_event_id, receiver_bref, trade_season) for apples-to-apples.
    test_base = baseline[
        (baseline["trade_season"] >= test_start)
        & (baseline["trade_season"] <= test_end)
    ].copy()

    merged = test_base.merge(
        v3_preds[["trade_event_id", "receiver_bref", "trade_season", "y_true", "y_pred_mean"]],
        on=["trade_event_id", "receiver_bref", "trade_season"],
        how="inner",
    ).dropna(subset=["xwoba_surplus_raw", "y_true"])

    if merged.empty:
        logger.warning(
            "No overlapping rows after merge — trade_event_id / receiver_bref key "
            "mismatch between baseline and V3 predictions. Skipping head-to-head."
        )
        return

    y_true = merged["y_true"].to_numpy(dtype=float)
    base_pred = merged["xwoba_surplus_raw"].to_numpy(dtype=float)
    v3_pred = merged["y_pred_mean"].to_numpy(dtype=float)

    base_mae = float(np.mean(np.abs(base_pred - y_true)))
    v3_mae = float(np.mean(np.abs(v3_pred - y_true)))

    # CRPS: rate baseline is a point mass; V3 has a posterior.
    base_crps = _crps_point_mass(y_true, base_pred)

    # For V3 CRPS, reconstruct samples from the stored result.
    # The test_predictions frame has only mean/p05/p95 — use the empirical
    # CRPS from the cached result directly if available.
    v3_crps = float(v3_result.test_crps)  # type: ignore[union-attr]

    n = len(merged)
    print()
    print("=" * 72)
    print("HEAD-TO-HEAD: Rate-Surplus Baseline vs. V3 (xwoba_delta, test 2021-2024)")
    print("=" * 72)
    print(f"  Matched rows:         {n}")
    print()
    print(f"  Rate-baseline MAE:    {base_mae:.5f}")
    print(f"  V3 MAE:              {v3_mae:.5f}")
    print()
    print(f"  Rate-baseline CRPS:   {base_crps:.5f}  (point-mass = MAE)")
    print(f"  V3 CRPS:             {v3_crps:.5f}")
    print()

    if v3_mae < base_mae:
        pct_mae = (base_mae - v3_mae) / base_mae * 100
        pct_crps = (base_crps - v3_crps) / base_crps * 100 if base_crps > 0 else float("nan")
        print(f"  VERDICT: V3 beats rate-baseline by {pct_mae:.1f}% MAE / {pct_crps:.1f}% CRPS")
    else:
        pct_mae = (v3_mae - base_mae) / v3_mae * 100
        print(
            f"  VERDICT: V3 does NOT beat rate-baseline "
            f"(rate-baseline better by {pct_mae:.1f}% MAE)"
        )
    print("=" * 72)


# ---------------------------------------------------------------------------
# Standalone rate-baseline report
# ---------------------------------------------------------------------------

def _report_standalone(baseline: pd.DataFrame) -> None:
    """Print summary statistics for the rate-surplus baseline across all seasons."""
    print()
    print("=" * 72)
    print("RATE-SURPLUS BASELINE — xwOBA (all seasons with Statcast coverage)")
    print("=" * 72)

    n_total = len(baseline)
    n_nonzero = (baseline["xwoba_surplus_raw"] != 0).sum()
    surplus = baseline["xwoba_surplus_raw"]

    print(f"  Total trade-receiver rows:  {n_total}")
    print(f"  Rows with non-zero surplus: {n_nonzero}")
    print()
    print(f"  Mean xwoba_surplus:  {surplus.mean():.5f}")
    print(f"  Median:              {surplus.median():.5f}")
    print(f"  Std:                 {surplus.std():.5f}")
    print(f"  Min / Max:           {surplus.min():.5f} / {surplus.max():.5f}")
    print()

    test = baseline[
        (baseline["trade_season"] >= _TEST_START)
        & (baseline["trade_season"] <= _TEST_END)
    ]
    print(f"  Test-set rows (2021-2024):  {len(test)}")
    if len(test) > 0:
        ts = test["xwoba_surplus_raw"]
        print(f"  Test mean:   {ts.mean():.5f}")
        print(f"  Test std:    {ts.std():.5f}")
        print(f"  Test MAE vs zero-center: {np.abs(ts).mean():.5f}")
    print("=" * 72)

    print()
    print("TOP 10 LARGEST POSITIVE SURPLUS (receiver gained most)")
    top10 = baseline.nlargest(10, "xwoba_surplus_raw")[
        ["trade_event_id", "receiver_bref", "trade_season", "xwoba_surplus_raw"]
    ]
    print(top10.to_string(index=False))

    print()
    print("TOP 10 LARGEST NEGATIVE SURPLUS (receiver gave up most)")
    bot10 = baseline.nsmallest(10, "xwoba_surplus_raw")[
        ["trade_event_id", "receiver_bref", "trade_season", "xwoba_surplus_raw"]
    ]
    print(bot10.to_string(index=False))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Compute rate-surplus baseline and optionally compare against V3."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-v3",
        action="store_true",
        help="Skip the V3 MCMC backtest comparison entirely.",
    )
    parser.add_argument(
        "--v3-timeout",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Wall-clock timeout for the V3 backtest (default: 60s). "
             "Pass 0 to disable timeout (runs until complete).",
    )
    args = parser.parse_args()

    logger.info("Loading trade_player_xwoba_window…")
    df_window = _load_xwoba_window()
    logger.info("Loaded %d player-rows with Statcast coverage.", len(df_window))

    if df_window.empty:
        logger.error(
            "No rows returned from trade_player_xwoba_window. "
            "Run the Statcast ingest first: uv run ste ingest statcast"
        )
        sys.exit(1)

    baseline = compute_rate_baseline(df_window)
    _report_standalone(baseline)

    if args.skip_v3:
        logger.info("--skip-v3 set; skipping V3 comparison.")
        return

    timeout = args.v3_timeout if args.v3_timeout > 0 else 10_000
    v3_result = _run_v3_backtest_with_timeout(timeout_s=timeout)
    if v3_result is None:
        logger.info("V3 comparison skipped.")
        return

    _head_to_head(baseline, v3_result)


if __name__ == "__main__":
    main()
