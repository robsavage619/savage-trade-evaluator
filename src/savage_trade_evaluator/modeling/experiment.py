"""B3: Experiment manifest writer — reproducibility harness.

Call ``write_manifest()`` at the start of each research script to snapshot:
- git SHA + schema version (code state at run time)
- DB row counts for key tables (data state at run time)
- Resolved feature sets (model state — strings, not live tuple references)

Manifests are written to ``data/experiments/<script>_<timestamp>_manifest.json``.
Compare two manifests to diagnose why a re-run produced different results:
  diff data/experiments/r57_*_manifest.json

The point is that ``V3_OUTCOME_FEATURES["war_delta"]`` resolves to ``ALL_FEATURES``
at import time. If ``ALL_FEATURES`` grows by one column, every script that imports
the live dict silently changes its model without leaving a trace. The manifest
freezes the resolved string list so the divergence is auditable.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from savage_trade_evaluator.config import DATA_DIR
from savage_trade_evaluator.storage import db
from savage_trade_evaluator.storage.schemas import SCHEMA_VERSION

logger = logging.getLogger(__name__)

EXPERIMENTS_DIR = DATA_DIR / "experiments"

_MANIFEST_TABLES = (
    "trade_events",
    "bwar_batting",
    "bwar_pitching",
    "statcast_batting_expected",
    "chadwick_register",
    "transactions",
)


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _table_row_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with db.connect(read_only=True) as conn:
        for table in _MANIFEST_TABLES:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row else 0
            except Exception:
                counts[table] = -1
    return counts


def write_manifest(
    script: str,
    feature_sets: dict[str, tuple[str, ...] | list[str]],
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a manifest JSON and return its path.

    Args:
        script: Short identifier, e.g. ``"r57_walk_forward_validation"``.
        feature_sets: Mapping from outcome name to the feature list used.
            Pass ``dict(V3_OUTCOME_FEATURES)`` or a subset. Tuples are
            serialised as lists so the file is plain JSON.
        extra: Additional key/value pairs embedded verbatim (fold counts, etc.).

    Returns:
        Path to the written manifest file.
    """
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    path = EXPERIMENTS_DIR / f"{script}_{ts}_manifest.json"

    manifest: dict[str, Any] = {
        "script": script,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "git_sha": _git_sha(),
        "schema_version": SCHEMA_VERSION,
        "table_row_counts": _table_row_counts(),
        "feature_sets": {
            outcome: list(features)
            for outcome, features in feature_sets.items()
        },
    }
    if extra:
        manifest["extra"] = extra

    path.write_text(json.dumps(manifest, indent=2))
    logger.info("manifest → %s", path)
    return path
