from __future__ import annotations

import httpx
import pytest

from savage_trade_evaluator.ingest import fetch


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return fetch.make_client(transport=handler)


def test_truncated_connection_then_bad_body_then_success_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("peer closed connection without a complete body")
        if calls["n"] == 2:
            return httpx.Response(200, content=b'{"truncated": ')
        return httpx.Response(200, json={"ok": True})

    assert fetch.get_json(_client(httpx.MockTransport(handler)), "http://x") == {"ok": True}
    assert calls["n"] == 3


def test_server_error_is_retried_but_not_found_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    seq = iter([503, 200])

    def flaky(request: httpx.Request) -> httpx.Response:
        code = next(seq)
        return httpx.Response(code, json={"ok": True})

    assert fetch.get_json(_client(httpx.MockTransport(flaky)), "http://x") == {"ok": True}

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        fetch.get_json(_client(httpx.MockTransport(missing)), "http://x")


def test_giving_up_names_the_last_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)

    def always(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset")

    with pytest.raises(RuntimeError, match="connection reset"):
        fetch.get_json(_client(httpx.MockTransport(always)), "http://x", retries=3)
