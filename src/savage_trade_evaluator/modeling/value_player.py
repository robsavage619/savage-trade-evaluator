"""Canonical prospective player valuation.

One function every surface should consume: given a player and a decision point,
return surplus WAR / surplus dollars over the remaining control window. It
composes the three GM-mind primitives that the old per-surface math lacked:

  1. :mod:`projection` — a regressed, playing-time-weighted true-talent WAR,
     replacing the raw last-season WAR that let a 10-start hot streak read as a
     7-WAR pitcher (the closer-trade bug).
  2. :mod:`leverage_value` — a reliever leverage premium, since context-neutral
     bWAR undervalues a high-leverage closer.
  3. A faithful Python port of the frontend arb/control model
     (``arbForecast.ts``): contract status → years of control + per-year salary.

Surplus is summed over the control window as aging-adjusted, leverage-adjusted
value minus projected salary, valued at a role-specific $/WAR. This is the
prospective analogue of ``three_term_value`` term 1; the post-FA (term 2) and
playoff-revenue (term 3) terms live there and can be layered on by the caller.

Porting the arb model here (rather than importing across the Python/TS split) is
the first concrete step of the "one brain, Python" consolidation: the frontend
will read these numbers instead of recomputing them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from savage_trade_evaluator.modeling.leverage_value import (
    LEAGUE_RELIEVER_GMLI,
    leverage_adjusted_war,
    player_game_leverage,
)
from savage_trade_evaluator.modeling.projection import project_player
from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# --- arb/control model (ported from frontend/src/lib/arbForecast.ts) ---------

MLB_MIN: int = 740_000

# Role-specific open-market $/WAR (batter/starter/reliever), 2024-26 FA actuals.
MARKET_RATE: dict[str, int] = {
    "batter": 8_500_000,
    "starter": 7_200_000,
    "reliever": 6_000_000,
}

# Fraction of open-market value paid in each arb year.
ARB_MULTIPLIERS: dict[int, float] = {1: 0.40, 2: 0.60, 3: 0.80}

# Position premium/discount on the arb multiplier.
POSITION_PREMIUM: dict[str, float] = {
    "SS": 1.12,
    "2B": 1.08,
    "CF": 1.08,
    "C": 1.06,
    "3B": 1.02,
    "RF": 1.00,
    "LF": 0.98,
    "1B": 0.90,
    "DH": 0.88,
    "SP": 1.00,
    "RP": 0.95,
    "P": 1.00,
}

_ARB_SEQUENCE: tuple[str, ...] = ("pre-arb", "arb1", "arb2", "arb3", "fa")


def infer_player_type(position_abbr: str | None, *, is_reliever: bool) -> str:
    """Map a position/role to a market-rate bucket."""
    if position_abbr:
        p = position_abbr.upper()
        if p in ("SP", "P"):
            return "reliever" if is_reliever else "starter"
        if p == "RP":
            return "reliever"
        if p not in POSITION_PREMIUM or p in ("SP", "RP", "P"):
            return "reliever" if is_reliever else "batter"
        return "batter"
    return "reliever" if is_reliever else "batter"


def parse_arb_class(status: str | None) -> str:
    """Parse a Spotrac contract_status string into an arb class."""
    if not status:
        return "fa"
    s = status.lower()
    if "pre-arb" in s or "pre arb" in s or "pre-arbitration" in s:
        return "pre-arb"
    if "arbitration 1" in s or "arb 1" in s or "arb1" in s:
        return "arb1"
    if "arbitration 2" in s or "arb 2" in s or "arb2" in s:
        return "arb2"
    if "arbitration 3" in s or "arbitration 4" in s or "arb3" in s:
        return "arb3"
    return "fa"


def _arb_rank(cls: str) -> int:
    return _ARB_SEQUENCE.index(cls)


def _next_class(cls: str) -> str:
    i = _ARB_SEQUENCE.index(cls)
    return _ARB_SEQUENCE[min(i + 1, len(_ARB_SEQUENCE) - 1)]


def aging_delta(age: float) -> float:
    """Per-year WAR aging adjustment (step curve; peak 26-27)."""
    if age < 24:
        return 0.15
    if age < 26:
        return 0.08
    if age < 28:
        return 0.0
    if age < 30:
        return -0.15
    if age < 33:
        return -0.25
    return -0.35


def _project_salary(
    cls: str,
    war: float,
    player_type: str,
    position_abbr: str | None,
    known_cap_hit: float | None,
) -> float:
    rate = MARKET_RATE[player_type]
    pos_premium = POSITION_PREMIUM.get((position_abbr or "").upper(), 1.0)
    open_market = max(MLB_MIN, war * rate * pos_premium)
    if cls == "pre-arb":
        return float(MLB_MIN)
    if cls in ("arb1", "arb2", "arb3"):
        return max(MLB_MIN, open_market * ARB_MULTIPLIERS[int(cls[-1])])
    return known_cap_hit if known_cap_hit is not None else open_market


@dataclass(frozen=True, slots=True)
class PlayerValue:
    """Prospective valuation of one player over the control window.

    Attributes:
        mlb_player_id: MLBAM player id.
        projected_war: Regressed full-season true-talent WAR.
        valued_war: ``projected_war`` after the reliever leverage premium.
        is_reliever: Role used for baseline/leverage/market-rate decisions.
        years_controlled: Remaining team-control seasons (capped at the window).
        control_salaries: Projected salary per controlled year.
        surplus_war: Aging-adjusted value minus salary, in WAR, over the window.
        surplus_dollars: ``surplus_war`` valued at the role $/WAR.
        note: Human-readable provenance (partial-sample regression, leverage).
    """

    mlb_player_id: int
    projected_war: float
    valued_war: float
    is_reliever: bool
    years_controlled: int
    control_salaries: tuple[float, ...]
    surplus_war: float
    surplus_dollars: float
    note: str


def value_player(
    mlb_player_id: int,
    season: int,
    contract_status: str | None,
    position_abbr: str | None,
    age: float,
    *,
    cap_hit: float | None = None,
    window_years: int = 3,
    regression_pt: float | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> PlayerValue:
    """Value a player over the remaining control window (surplus WAR + dollars).

    Args:
        mlb_player_id: MLBAM player id.
        season: Decision-point season (its in-progress total is regressed).
        contract_status: Spotrac contract_status string (drives arb class).
        position_abbr: Position abbreviation (SS, CF, SP, RP, …).
        age: Player age at the decision point.
        cap_hit: Known cap hit, used for FA/veteran salary years.
        window_years: Max control years to value (default 3).
        regression_pt: Optional override for projection shrinkage strength.
        conn: Optional open read-only connection.

    Returns:
        A :class:`PlayerValue`.
    """
    if conn is None:
        with db.connect(read_only=True) as opened:
            return value_player(
                mlb_player_id,
                season,
                contract_status,
                position_abbr,
                age,
                cap_hit=cap_hit,
                window_years=window_years,
                regression_pt=regression_pt,
                conn=opened,
            )

    proj = (
        project_player(mlb_player_id, season, conn=conn)
        if regression_pt is None
        else project_player(mlb_player_id, season, regression_pt=regression_pt, conn=conn)
    )
    war = proj.full_season_war
    is_reliever = proj.is_reliever

    valued_war = war
    leverage_note = ""
    if is_reliever:
        gm_li, _ = player_game_leverage(mlb_player_id, (season - 2, season - 1), conn=conn)
        gm_li_used = gm_li if gm_li is not None else LEAGUE_RELIEVER_GMLI
        valued_war = leverage_adjusted_war(war, gm_li_used, is_reliever=True)
        leverage_note = f"leverage gmLI {gm_li_used:.2f} x{valued_war / war:.2f}" if war else ""

    player_type = infer_player_type(position_abbr, is_reliever=is_reliever)
    rate = MARKET_RATE[player_type]

    current_class = parse_arb_class(contract_status)
    years_controlled = min(window_years, max(0, 4 - _arb_rank(current_class)))

    surplus_war = 0.0
    salaries: list[float] = []
    running_war = valued_war
    cls = current_class
    for t in range(years_controlled):
        running_war = max(0.0, running_war + aging_delta(age + t))
        cls = _next_class(cls)
        salary = _project_salary(cls, war, player_type, position_abbr, cap_hit)
        salaries.append(salary)
        surplus_war += running_war - salary / rate

    notes = [n for n in (proj.note, leverage_note) if n]
    return PlayerValue(
        mlb_player_id=mlb_player_id,
        projected_war=war,
        valued_war=valued_war,
        is_reliever=is_reliever,
        years_controlled=years_controlled,
        control_salaries=tuple(salaries),
        surplus_war=surplus_war,
        surplus_dollars=surplus_war * rate,
        note="; ".join(notes),
    )
