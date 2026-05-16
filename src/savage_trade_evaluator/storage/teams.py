"""Team-identifier bridge between the MLB Stats API and Baseball Reference.

The MLB Stats API uses integer team IDs (e.g., 117 = Houston Astros). Baseball
Reference uses 3-letter codes that we see in bWAR (e.g., HOU, KCR, SFG, TBR).
The two systems mostly agree on the abbreviation but diverge for ~7 teams.

The mapping below is hand-curated for the 30 current MLB franchises plus the
historical Florida Marlins → Miami Marlins and Montreal Expos → Washington
Nationals rebrands that show up in historical bWAR rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


TEAMS: list[tuple[int, str, str, str]] = [
    (108, "LAA", "LAA", "Los Angeles Angels"),
    (109, "AZ", "ARI", "Arizona Diamondbacks"),
    (110, "BAL", "BAL", "Baltimore Orioles"),
    (111, "BOS", "BOS", "Boston Red Sox"),
    (112, "CHC", "CHC", "Chicago Cubs"),
    (113, "CIN", "CIN", "Cincinnati Reds"),
    (114, "CLE", "CLE", "Cleveland Guardians"),
    (115, "COL", "COL", "Colorado Rockies"),
    (116, "DET", "DET", "Detroit Tigers"),
    (117, "HOU", "HOU", "Houston Astros"),
    (118, "KC", "KCR", "Kansas City Royals"),
    (119, "LAD", "LAD", "Los Angeles Dodgers"),
    (120, "WSH", "WSN", "Washington Nationals"),
    (121, "NYM", "NYM", "New York Mets"),
    (133, "ATH", "OAK", "Athletics"),
    (134, "PIT", "PIT", "Pittsburgh Pirates"),
    (135, "SD", "SDP", "San Diego Padres"),
    (136, "SEA", "SEA", "Seattle Mariners"),
    (137, "SF", "SFG", "San Francisco Giants"),
    (138, "STL", "STL", "St. Louis Cardinals"),
    (139, "TB", "TBR", "Tampa Bay Rays"),
    (140, "TEX", "TEX", "Texas Rangers"),
    (141, "TOR", "TOR", "Toronto Blue Jays"),
    (142, "MIN", "MIN", "Minnesota Twins"),
    (143, "PHI", "PHI", "Philadelphia Phillies"),
    (144, "ATL", "ATL", "Atlanta Braves"),
    (145, "CWS", "CHW", "Chicago White Sox"),
    (146, "MIA", "MIA", "Miami Marlins"),
    (147, "NYY", "NYY", "New York Yankees"),
    (158, "MIL", "MIL", "Milwaukee Brewers"),
]


HISTORICAL_BREF_ALIASES: dict[str, int] = {
    "FLA": 146,  # Florida Marlins (rebranded Miami 2012)
    "MON": 120,  # Montreal Expos (rebranded Washington 2005)
    "TBD": 139,  # Tampa Bay Devil Rays (rebranded Rays 2008)
    "ANA": 108,  # Anaheim Angels (rebranded Los Angeles Angels 2005)
}


def initialize(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the ``teams`` table and load the canonical mapping.

    Args:
        conn: Open DuckDB connection.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            mlb_team_id INTEGER PRIMARY KEY,
            mlb_abbrev VARCHAR NOT NULL,
            bref_code VARCHAR NOT NULL,
            name VARCHAR NOT NULL
        )
        """
    )
    rows = [(mlb_id, mlb_abbr, bref, name) for (mlb_id, mlb_abbr, bref, name) in TEAMS]
    conn.executemany(
        "INSERT INTO teams (mlb_team_id, mlb_abbrev, bref_code, name) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (mlb_team_id) DO NOTHING",
        rows,
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_aliases (
            bref_code VARCHAR PRIMARY KEY,
            mlb_team_id INTEGER NOT NULL
        )
        """
    )
    alias_rows = list(HISTORICAL_BREF_ALIASES.items())
    conn.executemany(
        "INSERT INTO team_aliases (bref_code, mlb_team_id) VALUES (?, ?) "
        "ON CONFLICT (bref_code) DO NOTHING",
        alias_rows,
    )
