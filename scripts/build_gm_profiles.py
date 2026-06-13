"""Build and persist GM behavioral profiles + archetype clusters (Phase 3).

Run:
  uv run python scripts/build_gm_profiles.py

Writes to:
  gm_behavioral_profiles  — one row per qualifying GM tenure
  gm_archetypes           — archetype cluster assignments
"""

from __future__ import annotations

import logging

from savage_trade_evaluator.analysis.gm_profiles import (
    build_gm_profiles,
    persist_profiles,
)
from savage_trade_evaluator.modeling.gm_archetypes import (
    cluster_gms,
    persist_archetypes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("building GM behavioral profiles…")
    profiles = build_gm_profiles()
    persist_profiles(profiles)

    logger.info("clustering into archetypes…")
    archetypes = cluster_gms(profiles)
    persist_archetypes(archetypes)

    print()
    print("=" * 72)
    print("  GM BEHAVIORAL PROFILES + ARCHETYPES")
    print("=" * 72)
    display = archetypes[
        [
            "decision_maker",
            "bref_code",
            "regime_start",
            "regime_end",
            "n_trades",
            "war_buyer_bias",
            "avg_age_received",
            "deadline_pct",
            "prospect_hugging_ratio",
            "archetype",
        ]
    ].copy()
    display["war_buyer_bias"] = display["war_buyer_bias"].round(2)
    display["avg_age_received"] = display["avg_age_received"].round(1)
    display["deadline_pct"] = (display["deadline_pct"] * 100).round(1)
    display["prospect_hugging_ratio"] = display["prospect_hugging_ratio"].round(2)
    display = display.sort_values("archetype")
    print(display.to_string(index=False))
    print()
    print("Archetype counts:")
    print(archetypes["archetype"].value_counts().to_string())


if __name__ == "__main__":
    main()
