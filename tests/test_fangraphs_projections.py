from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any

import duckdb
import pytest

from savage_trade_evaluator.ingest import fangraphs_projections as fp

SOTO = {
    "PlayerName": "Juan Soto", "playerids": "20123", "xMLBAMID": 665742, "Team": "NYM",
    "minpos": "OF", "G": 138.75, "PA": 625.663, "WAR": 4.89342, "wOBA": 0.399477,
    "wRC+": 160.0, "K%": 0.160156, "BB%": 0.1864,
}  # fmt: skip


def _payload(n: int = 1600) -> list[dict[str, Any]]:
    filler = [
        {"PlayerName": f"P{i}", "playerids": str(i), "xMLBAMID": 1000 + i, "WAR": 0.1}
        for i in range(n)
    ]
    return [SOTO, *filler, {"PlayerName": "No Id", "playerids": "x", "xMLBAMID": None, "WAR": 0.0}]


def test_a_real_record_maps_to_columns_and_missing_ids_are_dropped() -> None:
    rows = fp.parse_projections(date(2026, 11, 12), "steamer", "bat", _payload())
    soto = next(r for r in rows if r["mlb_player_id"] == 665742)
    assert (soto["war"], soto["pa"], soto["wrc_plus"], soto["k_pct"], soto["position"]) == (
        4.89342,
        625.663,
        160.0,
        0.160156,
        "OF",
    )
    assert soto["ip"] is None and soto["fg_player_id"] == "20123"
    assert all(r["mlb_player_id"] for r in rows) and len(rows) == 1601


def test_a_short_or_reshaped_response_fails_instead_of_storing_a_partial_table() -> None:
    with pytest.raises(ValueError, match="at least"):
        fp.parse_projections(date(2026, 11, 12), "steamer", "bat", _payload(10))
    reshaped = [{"name": "x", "id": 1}] * 2000
    with pytest.raises(ValueError, match="endpoint changed"):
        fp.parse_projections(date(2026, 11, 12), "steamer", "bat", reshaped)
    with pytest.raises(ValueError, match="dict"):
        fp.parse_projections(date(2026, 11, 12), "steamer", "bat", {"error": "blocked"})  # type: ignore[arg-type]


def test_rerunning_a_day_replaces_it_and_a_new_day_adds_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = duckdb.connect()

    @contextmanager
    def fake_connect(*a: Any, **k: Any) -> Any:
        yield conn

    monkeypatch.setattr(fp.db, "connect", fake_connect)
    for day, war in (
        (date(2026, 11, 12), 4.9),
        (date(2026, 11, 12), 5.1),
        (date(2026, 11, 13), 5.2),
    ):
        payload = _payload()
        payload[0] = {**SOTO, "WAR": war}
        monkeypatch.setattr(fp, "get_json", lambda client, url, p=payload: p)
        fp.ingest_snapshot(None, day, "steamer", "bat")  # type: ignore[arg-type]
    got = conn.execute(
        "SELECT as_of, war FROM fg_projections WHERE mlb_player_id = 665742 ORDER BY as_of"
    ).fetchall()
    assert got == [(date(2026, 11, 12), 5.1), (date(2026, 11, 13), 5.2)]
