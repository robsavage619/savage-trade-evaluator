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
