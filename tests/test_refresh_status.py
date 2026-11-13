from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from savage_trade_evaluator import refresh


def _run_build_only(tmp: Path, prior: dict | None) -> dict:
    (tmp / "dist").mkdir(parents=True, exist_ok=True)
    if prior is not None:
        (tmp / "status.json").write_text(json.dumps(prior))
    with (
        mock.patch.object(refresh, "STATUS_PATH", tmp / "status.json"),
        mock.patch.object(refresh, "LAST_GOOD_PATH", tmp / "last_good.json"),
        mock.patch.object(refresh, "FRONTEND", tmp),
        mock.patch.object(refresh, "build_site", lambda: None),
    ):
        refresh.main(["--build-only"])
    return json.loads((tmp / "dist" / "status.json").read_text())


def test_build_only_keeps_the_last_refresh_verdict(tmp_path: Path) -> None:
    prior = {
        "started": "t",
        "finished": "2026-11-12T16:33:45",
        "status": "degraded",
        "data_as_of": "2026-11-12T16:33:45",
        "published": True,
        "problems": ["step:spotrac-terms: exit 2"],
        "gates": [],
    }
    shown = _run_build_only(tmp_path, prior)
    assert shown["status"] == "degraded"
    assert shown["problems"] == ["step:spotrac-terms: exit 2"]


def test_build_only_without_a_refresh_is_not_reported_ok(tmp_path: Path) -> None:
    shown = _run_build_only(tmp_path, None)
    assert shown["status"] == "degraded"
    assert shown["problems"]
