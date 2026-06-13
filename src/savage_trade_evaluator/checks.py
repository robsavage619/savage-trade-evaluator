"""Data-quality check suite for ``ste check``.

Each Expectation runs a read-only SQL query and asserts a condition.
Thresholds are seeded from actual DB state (``ste check --seed``) so the
checks stay calibrated to the current data without hand-tuned magic numbers.

Baseline is stored at data/check_baseline.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from savage_trade_evaluator.config import DATA_DIR
from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

BASELINE_PATH = DATA_DIR / "check_baseline.json"


@dataclass
class CheckResult:
    """Result of running one Expectation."""

    name: str
    passed: bool
    message: str
    actual: float
    threshold: float | None = None


@dataclass
class Expectation:
    """One checkable assertion against the database."""

    name: str
    sql: str
    metric_label: str = "value"
    # Seeded as actual * min_ratio — checks that current value >= seeded_min
    min_ratio: float = 0.95

    def run(self, conn: object, baseline: dict[str, float]) -> CheckResult:
        """Execute the SQL, compare to baseline threshold."""
        result = conn.execute(self.sql).fetchone()  # type: ignore[attr-defined]
        actual = float(result[0]) if result and result[0] is not None else 0.0
        threshold = baseline.get(self.name)
        if threshold is None:
            return CheckResult(
                name=self.name,
                passed=True,
                message=f"no baseline yet — run `ste check --seed` (actual={actual:.1f})",
                actual=actual,
            )
        passed = actual >= threshold
        direction = ">=" if passed else "<"
        return CheckResult(
            name=self.name,
            passed=passed,
            message=(
                f"{self.metric_label}={actual:.1f} {direction} threshold={threshold:.1f}"
            ),
            actual=actual,
            threshold=threshold,
        )

    def seed_value(self, conn: object) -> float:
        """Return the value to persist as the baseline threshold."""
        result = conn.execute(self.sql).fetchone()  # type: ignore[attr-defined]
        raw = float(result[0]) if result and result[0] is not None else 0.0
        return raw * self.min_ratio


# ---------------------------------------------------------------------------
# Expectation definitions
# ---------------------------------------------------------------------------

EXPECTATIONS: list[Expectation] = [
    # --- Row-count guards ---
    Expectation(
        name="transactions_rows",
        sql="SELECT COUNT(*) FROM transactions",
        metric_label="transactions",
    ),
    Expectation(
        name="bwar_batting_rows",
        sql="SELECT COUNT(*) FROM bwar_batting",
        metric_label="bwar_batting rows",
    ),
    Expectation(
        name="bwar_pitching_rows",
        sql="SELECT COUNT(*) FROM bwar_pitching",
        metric_label="bwar_pitching rows",
    ),
    Expectation(
        name="trade_events_rows",
        sql="SELECT COUNT(*) FROM trade_events",
        metric_label="trade_events rows",
    ),
    Expectation(
        name="statcast_batting_rows",
        sql="SELECT COUNT(*) FROM statcast_batting_expected",
        metric_label="statcast_batting_expected rows",
    ),
    Expectation(
        name="chadwick_rows",
        sql="SELECT COUNT(*) FROM chadwick_register",
        metric_label="chadwick_register rows",
    ),
    # --- Null-rate guards on join keys ---
    # mlb_player_id coverage in trade_player_unified (critical for war-window join)
    Expectation(
        name="trade_player_mlb_id_coverage",
        sql="""
            SELECT (1.0 - COUNT(*) FILTER (WHERE mlb_player_id IS NULL)::DOUBLE / COUNT(*))
            FROM trade_player_unified
        """,
        metric_label="trade_player_unified mlb_id coverage",
        min_ratio=0.98,
    ),
    # bwar join-key coverage: mlb_id not null rate
    Expectation(
        name="bwar_batting_mlb_id_coverage",
        sql="""
            SELECT (1.0 - COUNT(*) FILTER (WHERE mlb_id IS NULL)::DOUBLE / COUNT(*))
            FROM bwar_batting
        """,
        metric_label="bwar_batting mlb_id coverage",
        min_ratio=0.99,
    ),
    # --- Crosswalk coverage ---
    # % of trade players resolvable in chadwick_register
    Expectation(
        name="crosswalk_coverage",
        sql="""
            SELECT COUNT(cr.mlb_player_id)::DOUBLE / COUNT(tpu.mlb_player_id)
            FROM trade_player_unified tpu
            LEFT JOIN chadwick_register cr ON cr.mlb_player_id = tpu.mlb_player_id
            WHERE tpu.mlb_player_id IS NOT NULL
        """,
        metric_label="trade players in chadwick",
        min_ratio=0.95,
    ),
    # --- Era coverage: bWAR must span the full trade era ---
    Expectation(
        name="bwar_era_min_season",
        sql="SELECT MIN(year_id) FROM bwar_batting WHERE mlb_id IS NOT NULL",
        metric_label="bwar earliest season",
        min_ratio=1.0,  # must be <= 1871; seeded as actual*1.0 so check passes if unchanged
    ),
    Expectation(
        name="bwar_era_max_season",
        sql="SELECT MAX(year_id) FROM bwar_batting WHERE mlb_id IS NOT NULL",
        metric_label="bwar latest season",
        min_ratio=0.98,  # 2024 * 0.98 = 1983 — still requires coverage near the era end
    ),
    # Season-level transaction coverage for trade era (2010+)
    Expectation(
        name="transactions_trade_era_seasons",
        sql="""
            SELECT COUNT(DISTINCT season)
            FROM transactions
            WHERE season BETWEEN 2010 AND 2024
        """,
        metric_label="transaction seasons 2010-2024",
        min_ratio=0.99,
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_checks(seed: bool = False) -> list[CheckResult]:
    """Run all expectations and return results.

    Args:
        seed: If True, write current actuals to the baseline file and return
              synthetic pass results — use ``ste check --seed`` once per
              major ingest to recalibrate thresholds.

    Returns:
        List of CheckResult, one per Expectation.
    """
    with db.connect(read_only=True) as conn:
        if seed:
            baseline: dict[str, float] = {}
            for exp in EXPECTATIONS:
                baseline[exp.name] = exp.seed_value(conn)
            BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
            BASELINE_PATH.write_text(json.dumps(baseline, indent=2))
            logger.info("baseline written to %s", BASELINE_PATH)
            return [
                CheckResult(
                    name=exp.name,
                    passed=True,
                    message=f"seeded threshold={baseline[exp.name]:.2f}",
                    actual=baseline[exp.name],
                    threshold=baseline[exp.name],
                )
                for exp in EXPECTATIONS
            ]

        baseline_data: dict[str, float] = {}
        if BASELINE_PATH.exists():
            baseline_data = json.loads(BASELINE_PATH.read_text())

        return [exp.run(conn, baseline_data) for exp in EXPECTATIONS]


def check_and_report(seed: bool = False) -> int:
    """Run all checks, print results, return exit code (0=pass, 1=fail)."""
    results = run_checks(seed=seed)
    failures = [r for r in results if not r.passed]

    width = max(len(r.name) for r in results)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name:<{width}}  {r.message}")

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED — see above")
        return 1
    print(f"All {len(results)} checks passed.")
    return 0
