"""Sweep all V3 outcomes for credible features and score by interestingness.

Fits backtest_outcome_v3 across every outcome in V3_OUTCOME_FEATURES, collects
every credible coefficient (D-26: directional mass >= 0.95, CI excludes zero),
and scores each feature by:

  - n_credible_outcomes: robustness across independent outcomes
  - is_org_feature: org-level signals (receiver_pct_*, receiver_avg_*, etc.)
    over player-level signals (receiver_acquired_*) — org features are less
    obvious and more actionable for roster construction
  - mean_mass: average directional mass across credible outcomes
  - consistent_sign: same direction everywhere the feature clears D-26

Writes findings_raw.json to frontend/src/data/model/ for the /intern-theses
skill to consume.

Run:
    uv run python scripts/discover_theses.py
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    backtest_outcome_v3,
    coefficient_summary,
)

logger = logging.getLogger(__name__)

OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "data" / "model"
TRAIN_END = 2020
TEST_END = 2024

# Features that are "obvious" to any baseball analyst — included in sweep but
# flagged so the intern agent can note when something non-obvious shows up.
OBVIOUS_FEATURES: frozenset[str] = frozenset(
    {
        "receiver_acquired_player_quality",
        "receiver_avg_age_at_trade",
    }
)


def _is_org_feature(feature: str) -> bool:
    """Org-level features don't have 'acquired' in the name — they describe
    what the receiving team IS, not what they GOT."""
    return "acquired" not in feature


def interestingness_score(
    n_credible: int,
    is_org: bool,
    mean_mass: float,
    consistent_sign: bool,
    n_total_outcomes: int,
) -> float:
    """Score a feature finding by how surprising/actionable it is.

    Org-level features get a bonus because they describe what a team IS,
    not just what they acquired. Cross-outcome consistency is the strongest
    evidence guard against spurious findings.
    """
    cross_outcome = n_credible / max(n_total_outcomes, 1)
    org_bonus = 0.30 if is_org else 0.0
    mass_signal = (mean_mass - 0.95) / 0.05  # 0.95 → 0, 1.00 → 1.0
    sign_bonus = 0.10 if consistent_sign else 0.0
    return round(cross_outcome * 0.45 + org_bonus + mass_signal * 0.15 + sign_bonus, 4)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    combined = assemble_v3_combined()
    outcomes = list(V3_OUTCOME_FEATURES.keys())
    logger.info("Sweeping %d outcomes: %s", len(outcomes), outcomes)

    # outcome → list of {feature, mean_beta, directional_mass, direction}
    outcome_results: dict[str, list[dict]] = {}

    for outcome in outcomes:
        logger.info("  fitting %s ...", outcome)
        try:
            result = backtest_outcome_v3(
                outcome,
                train_end_season=TRAIN_END,
                test_end_season=TEST_END,
                combined=combined,
            )
        except ValueError as e:
            logger.warning("  SKIP %s: %s", outcome, e)
            continue

        coef = coefficient_summary(result.fit)
        credible = coef[coef["credible"]]
        logger.info(
            "  %s: train=%d test=%d credible_features=%d",
            outcome,
            result.train_n,
            result.test_n,
            len(credible),
        )
        outcome_results[outcome] = [
            {
                "feature": str(r.feature),
                "mean_beta": float(r.mean_beta),
                "directional_mass": float(r.directional_mass),
                "direction": "positive" if float(r.mean_beta) > 0 else "negative",
            }
            for r in credible.itertuples()
        ]

    # Aggregate by feature across all outcomes
    feature_map: dict[str, dict] = {}
    for outcome, rows in outcome_results.items():
        for row in rows:
            feat = row["feature"]
            if feat not in feature_map:
                feature_map[feat] = {
                    "feature": feat,
                    "is_org_feature": _is_org_feature(feat),
                    "is_obvious": feat in OBVIOUS_FEATURES,
                    "credible_outcomes": [],
                    "betas": [],
                    "masses": [],
                }
            feature_map[feat]["credible_outcomes"].append(outcome)
            feature_map[feat]["betas"].append(row["mean_beta"])
            feature_map[feat]["masses"].append(row["directional_mass"])

    n_outcomes = len(outcome_results)
    findings: list[dict] = []
    for feat, info in feature_map.items():
        betas = info["betas"]
        masses = info["masses"]
        n_credible = len(info["credible_outcomes"])
        consistent_sign = all(b > 0 for b in betas) or all(b < 0 for b in betas)
        mean_mass = float(np.mean(masses))
        score = interestingness_score(
            n_credible=n_credible,
            is_org=info["is_org_feature"],
            mean_mass=mean_mass,
            consistent_sign=consistent_sign,
            n_total_outcomes=n_outcomes,
        )
        findings.append(
            {
                "feature": feat,
                "is_org_feature": info["is_org_feature"],
                "is_obvious": info["is_obvious"],
                "credible_outcomes": info["credible_outcomes"],
                "n_credible_outcomes": n_credible,
                "mean_beta": round(float(np.mean(betas)), 4),
                "mean_mass": round(mean_mass, 4),
                "direction": "positive" if float(np.mean(betas)) > 0 else "negative",
                "consistent_sign": consistent_sign,
                "interestingness_score": score,
                "per_outcome": [
                    {
                        "outcome": o,
                        "beta": round(b, 4),
                        "mass": round(m, 4),
                    }
                    for o, b, m in zip(info["credible_outcomes"], betas, masses, strict=False)
                ],
            }
        )

    findings.sort(key=lambda x: x["interestingness_score"], reverse=True)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "outcomes_swept": list(outcome_results.keys()),
        "n_outcomes": n_outcomes,
        "train_window": [2010, TRAIN_END],
        "test_window": [TRAIN_END + 1, TEST_END],
        "findings": findings,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "findings_raw.json"
    out.write_text(json.dumps(payload, indent=2))
    logger.info(
        "Wrote %d findings (%d unique features) → %s",
        len(findings),
        len(feature_map),
        out,
    )

    logger.info("\nTop 10 by interestingness:")
    for f in findings[:10]:
        logger.info(
            "  %.3f  %-52s  org=%s  n_outcomes=%d  direction=%s",
            f["interestingness_score"],
            f["feature"],
            f["is_org_feature"],
            f["n_credible_outcomes"],
            f["direction"],
        )


if __name__ == "__main__":
    main()
