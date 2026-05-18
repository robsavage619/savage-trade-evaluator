"""Project paths and configuration constants."""

from __future__ import annotations

import logging
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
# Allow STE_DUCKDB_PATH env var to point at a DB from a different worktree.
DUCKDB_PATH = Path(os.environ["STE_DUCKDB_PATH"]) if "STE_DUCKDB_PATH" in os.environ else DATA_DIR / "duckdb" / "trades.db"

MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"

BACKTESTER_START_SEASON = 1990
BACKTESTER_END_SEASON = 2024


def configure_logging(level: int = logging.INFO) -> None:
    """Set up a single root logger format for all CLI / library entrypoints.

    Args:
        level: Logging level constant (defaults to ``INFO``).
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
