"""Unit tests for the Spotrac contract-terms parser (no network)."""

from __future__ import annotations

from savage_trade_evaluator.ingest.spotrac import parse_contract_terms

# Trimmed shape of a real player page: current contract block first, a prior
# extension block later (which must be ignored — only the active deal counts).
_BOGAERTS_HTML = """
<div class="contract-summary">
  <span>Contract Terms:</span> 11 yr(s) / $280,000,000
  <span>Average Salary:</span> $25,454,545
  <span>Signing Bonus:</span> $5,000,000
  <span>Free Agent:</span> 2034 / UFA
</div>
<div class="prior-contract">
  Arbitration Extension <span>Contract Terms:</span> 6 yr(s) / $120,000,000
  <span>Free Agent:</span> 2026 / UFA
</div>
"""


def test_parses_active_contract_block() -> None:
    terms = parse_contract_terms(_BOGAERTS_HTML)
    assert terms == {
        "contract_years": 11,
        "contract_total": 280_000_000,
        "aav": 25_454_545,
        "free_agent_year": 2034,
    }


def test_takes_first_block_not_prior_extension() -> None:
    terms = parse_contract_terms(_BOGAERTS_HTML)
    assert terms is not None
    # The 2026 free-agent year belongs to the old extension; the active deal's
    # 2034 must win because it is paired within the first block's window.
    assert terms["free_agent_year"] == 2034


def test_returns_none_without_contract_block() -> None:
    assert parse_contract_terms("<div>Pre-Arbitration player, no guaranteed deal</div>") is None


def test_partial_block_without_aav_or_fa() -> None:
    terms = parse_contract_terms("<span>Contract Terms:</span> 1 yr(s) / $2,000,000")
    assert terms == {"contract_years": 1, "contract_total": 2_000_000}


def test_rewriting_a_row_refreshes_ingested_at() -> None:
    """The freshness gate reads ingested_at, so a replace must advance it."""
    import time

    import duckdb

    from savage_trade_evaluator.ingest.spotrac import _upsert_contract_terms
    from savage_trade_evaluator.storage import schemas

    conn = duckdb.connect(":memory:")
    schemas.initialize(conn)
    terms = {"contract_years": 5, "contract_total": 100, "aav": 20, "free_agent_year": 2030}
    _upsert_contract_terms(conn, 1, 2026, 9, terms)
    row = conn.execute("SELECT ingested_at FROM spotrac_contract_terms").fetchone()
    assert row is not None
    first = row[0]
    time.sleep(1.1)
    _upsert_contract_terms(conn, 1, 2026, 9, {**terms, "aav": 25})
    row = conn.execute("SELECT ingested_at, aav FROM spotrac_contract_terms").fetchone()
    assert row is not None
    second, aav = row
    assert aav == 25
    assert second > first


def _veteran_db(ids: list[int]):
    import duckdb

    from savage_trade_evaluator.storage import schemas

    conn = duckdb.connect(":memory:")
    schemas.initialize(conn)
    for pid in ids:
        conn.execute(
            "INSERT INTO spotrac_player_contracts (spotrac_id, mlb_player_id, player_name, "
            "team_bref, season, status, cap_hit, table_type, spotrac_slug, source) "
            "VALUES (?, ?, ?, 'AAA', 2026, 'Veteran', 1000, 'active', ?, 't')",
            [pid + 1000, pid, f"P{pid}", f"p{pid}"],
        )
    return conn


def _terms_row(conn, pid: int, days_old: int) -> None:
    conn.execute(
        "INSERT INTO spotrac_contract_terms (mlb_player_id, season, spotrac_id, source, "
        "ingested_at) VALUES (?, 2026, ?, 't', now() - to_days(?))",
        [pid, pid + 1000, days_old],
    )


def test_the_stalest_terms_row_is_scraped_first() -> None:
    from savage_trade_evaluator.ingest.spotrac import _veterans_stalest_first

    conn = _veteran_db([1, 2, 3, 4])
    _terms_row(conn, 1, 10)
    _terms_row(conn, 2, 1)
    _terms_row(conn, 4, 20)  # player 3 has no row yet and counts as three days old
    order = [r[0] for r in _veterans_stalest_first(conn, 2026, 0)]
    assert order == [4, 1, 3, 2]


def _run_scrape(conn, outcomes: list[int | None]) -> tuple[int, int]:
    """Run the scrape with fetch results: an HTTP status to fail with, or None to succeed."""
    from contextlib import contextmanager
    from unittest import mock

    import httpx

    from savage_trade_evaluator.ingest import spotrac

    calls = {"n": 0}

    def fake_fetch(client, spotrac_id, slug):
        status = outcomes[calls["n"]]
        calls["n"] += 1
        if status is None:
            return {"contract_years": 3, "contract_total": 30, "aav": 10, "free_agent_year": 2029}
        request = httpx.Request("GET", "https://example.test")
        raise httpx.HTTPStatusError(
            "blocked", request=request, response=httpx.Response(status, request=request)
        )

    @contextmanager
    def fake_connect(*args, **kwargs):
        yield conn

    with (
        mock.patch.object(spotrac.db, "connect", fake_connect),
        mock.patch.object(spotrac, "fetch_player_contract", fake_fetch),
        mock.patch.object(spotrac.time, "sleep", lambda s: None),
    ):
        written = spotrac.ingest_contract_terms(2026)
    return written, calls["n"]


def test_the_scrape_stops_after_five_consecutive_403s() -> None:
    conn = _veteran_db(list(range(1, 9)))
    written, calls = _run_scrape(conn, [403] * 8)
    assert (written, calls) == (0, 5)


def test_a_success_resets_the_403_count() -> None:
    conn = _veteran_db(list(range(1, 11)))
    written, calls = _run_scrape(conn, [403] * 4 + [None] + [403] * 4 + [None])
    assert (written, calls) == (2, 10)
