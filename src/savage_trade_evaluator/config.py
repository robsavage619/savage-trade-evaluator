"""Project paths and configuration constants."""

from __future__ import annotations

import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DUCKDB_PATH = DATA_DIR / "duckdb" / "trades.db"

MLB_STATS_API_BASE = "https://statsapi.mlb.com/api/v1"

BACKTESTER_START_SEASON = 2010
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
