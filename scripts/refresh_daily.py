"""Daily refresh entry point: ingest, gate, export, build, publish.

Run:
  uv run python scripts/refresh_daily.py --gates-only   # read-only check of the data now
  uv run python scripts/refresh_daily.py                # the full job the iMac runs daily
  uv run python scripts/refresh_daily.py --build-only   # rebuild and swap the site only
"""

from __future__ import annotations

from savage_trade_evaluator.refresh import main

if __name__ == "__main__":
    raise SystemExit(main())
