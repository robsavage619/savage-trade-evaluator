"""Technology adoption earliness score for MLB organizations.

Captures how many seasons ahead of the league mandate an org deployed
data-capture technology (TrackMan, Edgertronic, PITCHf/x equivalents)
system-wide in their minor league affiliates. Early adopters had a dev-system
advantage before technology became league-wide standard.

Sources:
    Reiter 2018 (Astroball): HOU 2012-2013 Edgertronic + TrackMan in minors.
    Sawchik 2015 (Big Data Baseball): PIT 2012-2013 PITCHf/x in minors.
    Longenhagen/McDaniel 2020 (Future Value): league-wide adoption timeline,
        MiLB TrackMan rollout, early-adopter org narratives.
    Public reporting on TrackMan MiLB mandate (2017-2019 phased rollout,
        effective league-wide by 2019 season).
"""

from __future__ import annotations

# Season each org deployed tracking technology system-wide in their minor league system.
# Sources: Reiter 2018 (HOU), Sawchik 2015 (PIT), Longenhagen/McDaniel 2020 (league-wide),
#          public reporting on TrackMan MiLB rollout (2017-2019 league-wide mandate).
# Orgs not listed: assumed to adopt at the league-wide mandate year (2019).
MINOR_LEAGUE_TECH_ADOPTION_YEAR: dict[str, int] = {
    "HOU": 2013,  # Luhnow / Sig: Edgertronic + TrackMan in minors
    "PIT": 2012,  # Sawchik Big Data Baseball: PITCHf/x in minors
    "STL": 2014,  # Cardinals analytics build-out
    "CHC": 2014,  # Epstein/Hoyer
    "LAD": 2014,  # Friedman era
    "TB": 2015,  # Friedman then Silverman
    "CLE": 2014,  # Antonetti sabermetric build
    "BOS": 2015,  # Post-Epstein continuation
    "NYY": 2016,  # Cashman analytics investment
    "OAK": 2016,  # Forst era
    "ATL": 2015,  # Anthopoulos
    "SDP": 2016,  # Preller
    "MIN": 2016,  # Falvey/Levine
    "SEA": 2016,  # DiPoto
    # League-wide MLB mandate for TrackMan in all MiLB affiliates: 2019
}
LEAGUE_MANDATE_YEAR: int = 2019

_MAX_LEAD: float = 7.0


def tech_adoption_score(bref_code: str, season: int) -> float:
    """Seasons ahead of league mandate this org had MiLB tracking tech.

    Returns a positive float (seasons of lead time) if the org adopted early,
    0.0 at or after the league mandate year. Clamped to [0.0, 7.0].

    Args:
        bref_code: Baseball Reference team abbreviation (e.g. ``"HOU"``).
        season: The season to evaluate (typically trade_season - 1 so the
            feature reflects what was known before the trade).

    Returns:
        Lead years relative to league mandate, clamped to ``[0.0, 7.0]``.
    """
    adoption_year = MINOR_LEAGUE_TECH_ADOPTION_YEAR.get(bref_code, LEAGUE_MANDATE_YEAR)
    if season < adoption_year:
        return 0.0
    lead = float(LEAGUE_MANDATE_YEAR - adoption_year)
    return min(max(lead, 0.0), _MAX_LEAD)
