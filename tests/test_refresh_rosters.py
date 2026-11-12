from __future__ import annotations

import gzip
import http.client
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "refresh_rosters", Path(__file__).resolve().parents[1] / "scripts" / "refresh_rosters.py"
)
assert _SPEC and _SPEC.loader
rr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rr)


class _Resp:
    def __init__(self, body: bytes, encoding: str | None = None) -> None:
        self._body = body
        self.headers = {"Content-Encoding": encoding} if encoding else {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def test_gzip_response_is_requested_and_decoded(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: float) -> _Resp:
        seen["accept"] = req.get_header("Accept-encoding")
        return _Resp(gzip.compress(json.dumps({"roster": [1]}).encode()), "gzip")

    monkeypatch.setattr(rr.urllib.request, "urlopen", fake_urlopen)
    assert rr._http_json("http://x") == {"roster": [1]}
    assert seen["accept"] == "gzip"


def test_truncated_read_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(req: Any, timeout: float) -> _Resp:
        calls["n"] += 1
        if calls["n"] < 3:
            raise http.client.IncompleteRead(b"{", 4310)
        return _Resp(b'{"ok": true}')

    monkeypatch.setattr(rr.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(rr.time, "sleep", lambda s: None)
    assert rr._http_json("http://x") == {"ok": True}
    assert calls["n"] == 3


def test_partial_league_is_refused_before_anything_is_written() -> None:
    full = {code: [{}] * 33 for code, _, _ in rr.TEAM_ROSTER}
    rr.validate_rosters(full)  # a full league passes
    with pytest.raises(SystemExit, match="partial seed"):
        rr.validate_rosters({**full, "NYM": []})
    with pytest.raises(SystemExit, match="partial seed"):
        rr.validate_rosters({k: v for k, v in full.items() if k != "SDP"})
