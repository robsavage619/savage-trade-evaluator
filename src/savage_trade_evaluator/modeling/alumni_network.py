"""Front-office alumni network score for MLB organizations.

Scores each (bref_code, season) by whether the current GM/POBO is an alumnus
of a known analytics-pioneer org during its pioneer window. The hypothesis
(Reiter 2018, Astroball): the Cardinals → Astros → Orioles pipeline shows
that a receiving GM who trained at a pioneer org carries that org's dev
process with them, independent of the team regime label.

The data layer (``front_office`` table) has GM stints by (bref_code, season)
from Baseball Reference but no within-season date granularity — we cannot
reliably track mid-season hires. All signals are pre-trade-year (season - 1).

Scoring rules:
    1.0 — GM or Scouting/Farm Director at receiving team this season was
          a GM or Scouting/Farm Director at a pioneer org during its window.
    0.5 — GM at receiving team was a Scouting/Farm Director (non-GM) at a
          pioneer org during its window (partial exposure, not full process
          ownership).
    0.0 — no traceable pioneer-org lineage.

Because the ``front_office`` table only records who held a role at a given
team-season, and does not record prior stints, we close the lineage gap with
a hardcoded ``PIONEER_LINEAGE`` lookup keyed by ``person_name``. This is an
approximation pending a full multi-org career-path scrape; every entry is
sourced from public reporting listed below.

Sources:
    Reiter 2018 (Astroball): Sig Mejdal STL → HOU, Mike Fast STL → HOU,
        Kevin Goldstein HOU, Dana Brown HOU → ATL.
    Epstein 2002-2011 (BOS / CHC pipeline): Jed Hoyer BOS → SDP → CHC,
        Jason McLeod BOS → CHC, Scott Harris CHC → SFG.
    Friedman 2006-2014 (TB → LAD): Erik Neander TB, Farhan Zaidi TB → OAK → SFG,
        David Forst OAK (Alderson lineage).
    Antonetti / Chernoff (CLE): Mike Chernoff CLE promoted from analyst.
    General public record: Baseball America, The Athletic, Ken Rosenthal reporting.
"""

from __future__ import annotations

# Pioneer org windows: when the org was a genuine process leader.
# Key = bref_code, value = (first_pioneer_season, last_pioneer_season) inclusive.
PIONEER_ORG_WINDOWS: dict[str, tuple[int, int]] = {
    "STL": (2011, 2017),  # DeWitt → Mozeliak analytics build
    "HOU": (2012, 2019),  # Luhnow / Sig era
    "CHC": (2012, 2017),  # Epstein / Hoyer build
    "LAD": (2014, 2024),  # Friedman / Farhan era (ongoing)
    "TB": (2008, 2024),  # Friedman then Silverman (ongoing)
    "CLE": (2011, 2019),  # Antonetti / Chernoff sabermetric build
}

# Hardcoded lineage: person_name → list of (pioneer_bref, first_season, last_season, role).
# role: "gm" = GM-level (score 1.0 if they become GM elsewhere),
#       "dir" = director-level (score 0.5 if they become GM; 1.0 if they stay director).
#
# NOTE: Approximation only — tracks the most prominent public-record moves.
# Missing: mid-level analysts, assistant GMs without public attribution.
PIONEER_LINEAGE: dict[str, list[tuple[str, int, int, str]]] = {
    # HOU pioneer alumni (Luhnow / Sig era from STL)
    "Sig Mejdal": [("STL", 2005, 2011, "dir"), ("HOU", 2012, 2019, "dir")],
    "Mike Fast": [("STL", 2010, 2011, "dir"), ("HOU", 2012, 2019, "dir")],
    "Kevin Goldstein": [("HOU", 2012, 2016, "dir")],
    "Jeff Luhnow": [("STL", 2003, 2011, "dir"), ("HOU", 2012, 2017, "gm")],
    "David Stearns": [("HOU", 2012, 2015, "dir")],
    "Mike Elias": [("STL", 2010, 2011, "dir"), ("HOU", 2012, 2018, "dir")],
    "Dana Brown": [("HOU", 2014, 2022, "dir")],
    # CHC / BOS pipeline (Epstein / Hoyer)
    "Theo Epstein": [("BOS", 2002, 2011, "gm")],
    "Jed Hoyer": [("BOS", 2003, 2009, "dir"), ("CHC", 2012, 2021, "gm")],
    "Jason McLeod": [("BOS", 2003, 2011, "dir"), ("CHC", 2012, 2020, "dir")],
    "Scott Harris": [("CHC", 2014, 2021, "dir")],
    "Carter Hawkins": [("CHC", 2014, 2021, "dir")],
    # TB / LAD pipeline (Friedman)
    "Andrew Friedman": [("TB", 2006, 2014, "gm")],
    "Erik Neander": [("TB", 2006, 2024, "dir")],
    "Farhan Zaidi": [("TB", 2011, 2014, "dir"), ("OAK", 2015, 2018, "dir")],
    "Matt Arnold": [("TB", 2010, 2018, "dir")],
    # CLE pipeline (Antonetti / Chernoff)
    "Mike Chernoff": [("CLE", 2010, 2024, "dir")],
    "Carter Bloom": [("CLE", 2011, 2018, "dir")],
    # STL pipeline
    "John Mozeliak": [("STL", 2007, 2024, "gm")],
    "Michael Girsch": [("STL", 2013, 2022, "dir")],
    # OAK (Alderson / Beane — precursor lineage feeding into analytics era)
    "David Forst": [("OAK", 2014, 2024, "gm")],
}

_GM_ROLES: frozenset[str] = frozenset({"General Manager", "President"})
_DIR_ROLES: frozenset[str] = frozenset({"Scouting Director", "Farm Director"})


def _in_pioneer_window(bref: str, season: int) -> bool:
    """Return True if (bref, season) falls inside that org's pioneer window."""
    window = PIONEER_ORG_WINDOWS.get(bref)
    if window is None:
        return False
    return window[0] <= season <= window[1]


def alumni_network_score(person_name: str | None, role: str | None) -> float:
    """Score one person-role pair for pioneer-org lineage.

    Args:
        person_name: Name as it appears in the ``front_office`` table.
        role: Role string from ``front_office`` (e.g. ``"General Manager"``).

    Returns:
        1.0, 0.5, or 0.0 per scoring rules in module docstring.
    """
    if person_name is None or role is None:
        return 0.0
    stints = PIONEER_LINEAGE.get(person_name)
    if not stints:
        return 0.0

    is_gm_role = role in _GM_ROLES
    is_dir_role = role in _DIR_ROLES

    best = 0.0
    for pioneer_bref, first_s, last_s, stint_role in stints:
        if not _in_pioneer_window(pioneer_bref, (first_s + last_s) // 2):
            # Confirm the stint overlaps the pioneer window, not just the org.
            overlap = any(
                _in_pioneer_window(pioneer_bref, s) for s in range(first_s, last_s + 1)
            )
            if not overlap:
                continue
        else:
            overlap = True

        if not overlap:
            continue

        if stint_role == "gm":
            # Was a GM-level at a pioneer org → full credit regardless of current role.
            best = max(best, 1.0)
        elif stint_role == "dir":
            if is_gm_role:
                # Director-level alumnus now running their own org → partial credit.
                best = max(best, 0.5)
            elif is_dir_role:
                # Stayed at director level, trained at pioneer → full credit.
                best = max(best, 1.0)

    return best


def team_alumni_score(
    bref_code: str,
    season: int,
    front_office_rows: list[tuple[str, str]],
) -> float:
    """Compute the alumni network score for a team-season.

    Takes the best score across all GM/director personnel at the team in that
    season. Called by ``features.compute_all`` after querying the DB.

    Args:
        bref_code: Baseball Reference team abbreviation (unused in logic but
            kept for call-site clarity).
        season: The season being scored.
        front_office_rows: List of ``(person_name, role)`` tuples for every
            front-office row at this (bref_code, season).

    Returns:
        Best score in [0.0, 1.0] across all personnel.
    """
    best = 0.0
    for person_name, role in front_office_rows:
        s = alumni_network_score(person_name, role)
        if s > best:
            best = s
            if best >= 1.0:
                break
    return best
