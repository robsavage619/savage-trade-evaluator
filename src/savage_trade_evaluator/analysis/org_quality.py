"""R-31: 2D org-quality coordinate map — dev credit vs trade outcome.

Extracted from scripts/dev_credit_full.py for use in reports and CLI.
"""

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db

FRANCHISE_ALIASES: dict[str, str] = {
    "TBD": "TBR",
    "FLA": "MIA",
    "FLO": "MIA",
    "MON": "WSN",
    "ANA": "LAA",
    "CAL": "LAA",
    "CHA": "CHW",
    "KCA": "OAK",
    "PHA": "OAK",
    "LAN": "LAD",
    "BRO": "LAD",
    "NYA": "NYY",
    "NYN": "NYM",
    "NYG": "SFG",
    "SDN": "SDP",
    "SFN": "SFG",
    "SLN": "STL",
    "BSN": "ATL",
    "MLN": "ATL",
    "SLB": "BAL",
    "WS1": "MIN",
    "WS2": "TEX",
}

CURRENT_30_FRANCHISES: set[str] = {
    "ARI", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL", "DET",
    "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "OAK",
    "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR", "TEX", "TOR", "WSN",
}

DRAFT_NAME_TO_BREF: dict[str, str] = {
    "San Diego Padres": "SDP", "Los Angeles Dodgers": "LAD", "Boston Red Sox": "BOS",
    "New York Yankees": "NYY", "New York Mets": "NYM", "Atlanta Braves": "ATL",
    "Houston Astros": "HOU", "Cleveland Indians": "CLE", "Cleveland Guardians": "CLE",
    "Texas Rangers": "TEX", "Tampa Bay Devil Rays": "TBR", "Tampa Bay Rays": "TBR",
    "Florida Marlins": "MIA", "Miami Marlins": "MIA", "Montreal Expos": "WSN",
    "Washington Nationals": "WSN", "Anaheim Angels": "LAA", "California Angels": "LAA",
    "Los Angeles Angels": "LAA", "Los Angeles Angels of Anaheim": "LAA",
    "Athletics": "OAK", "Oakland Athletics": "OAK", "Toronto Blue Jays": "TOR",
    "Chicago Cubs": "CHC", "Chicago White Sox": "CHW", "Cincinnati Reds": "CIN",
    "Detroit Tigers": "DET", "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT",
    "St. Louis Cardinals": "STL", "Seattle Mariners": "SEA",
    "San Francisco Giants": "SFG", "Baltimore Orioles": "BAL",
    "Kansas City Royals": "KCR", "Colorado Rockies": "COL",
    "Arizona Diamondbacks": "ARI",
}

FULL_NAMES: dict[str, str] = {
    "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox", "CHC": "Chicago Cubs", "CHW": "Chicago White Sox",
    "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians", "COL": "Colorado Rockies",
    "DET": "Detroit Tigers", "HOU": "Houston Astros", "KCR": "Kansas City Royals",
    "LAA": "LA Angels", "LAD": "LA Dodgers", "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins", "NYM": "NY Mets",
    "NYY": "NY Yankees", "OAK": "Oakland A's", "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates", "SDP": "San Diego Padres", "SEA": "Seattle Mariners",
    "SFG": "San Francisco Giants", "STL": "St. Louis Cardinals", "TBR": "Tampa Bay Rays",
    "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays", "WSN": "Washington Nationals",
}


def _alias(bref: str | None) -> str | None:
    if bref is None:
        return None
    return FRANCHISE_ALIASES.get(bref, bref)


def _load_player_facts() -> pd.DataFrame:
    """One row per player: first_mlb_team, career WAR, drafted-by."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            WITH career AS (
                SELECT mlb_id, SUM(war) AS career_war, MIN(year_id) AS first_year
                FROM bwar_player_seasons
                WHERE mlb_id IS NOT NULL
                GROUP BY mlb_id
            ),
            first_stint AS (
                SELECT mlb_id, team_id AS first_mlb_team_raw
                FROM (
                    SELECT mlb_id, team_id, year_id,
                           ROW_NUMBER() OVER (PARTITION BY mlb_id ORDER BY year_id, stint_id) AS rn
                    FROM bwar_player_seasons
                    WHERE mlb_id IS NOT NULL AND team_id IS NOT NULL
                ) WHERE rn = 1
            )
            SELECT c.mlb_id, fs.first_mlb_team_raw, c.career_war, c.first_year
            FROM career c
            LEFT JOIN first_stint fs ON fs.mlb_id = c.mlb_id
            """
        ).df()

        drafted = conn.execute(
            """
            SELECT mlb_player_id, MIN(draft_year) AS first_draft_year,
                   ANY_VALUE(team_name) AS drafting_team_name
            FROM draft_picks
            WHERE mlb_player_id IS NOT NULL
            GROUP BY mlb_player_id
            """
        ).df()

    df["first_mlb_team"] = df["first_mlb_team_raw"].apply(_alias)
    drafted["drafting_team_bref"] = drafted["drafting_team_name"].map(DRAFT_NAME_TO_BREF)
    drafted["drafting_team_bref"] = drafted["drafting_team_bref"].apply(_alias)
    df = df.merge(
        drafted[["mlb_player_id", "drafting_team_bref"]],
        left_on="mlb_id", right_on="mlb_player_id", how="left",
    )
    return df


def _dev_credit(df: pd.DataFrame, since_year: int = 1990) -> pd.DataFrame:
    keep = df.dropna(subset=["first_mlb_team", "career_war"]).copy()
    keep = keep[keep["first_year"] >= since_year]
    keep = keep[keep["first_mlb_team"].isin(CURRENT_30_FRANCHISES)]
    return (
        keep.groupby("first_mlb_team")
        .agg(n_mlb_debutees=("mlb_id", "count"), dev_war=("career_war", "sum"))
        .sort_values("dev_war", ascending=False)
    )


def _intl_credit(df: pd.DataFrame) -> pd.DataFrame:
    intl = df[
        df["drafting_team_bref"].isna()
        & (df["first_year"] >= 1995)
        & df["first_mlb_team"].notna()
        & df["career_war"].notna()
        & df["first_mlb_team"].isin(CURRENT_30_FRANCHISES)
    ]
    return (
        intl.groupby("first_mlb_team")
        .agg(n_intl=("mlb_id", "count"), intl_war=("career_war", "sum"))
        .sort_values("intl_war", ascending=False)
    )


def _trade_delta() -> pd.DataFrame:
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT from_team_bref AS team,
                   COUNT(*) AS n_trades,
                   AVG(war_t_plus_1 - war_t_minus_1) AS mean_delta_war
            FROM trade_player_war_window
            WHERE war_t_minus_1 IS NOT NULL
              AND war_t_plus_1 IS NOT NULL
              AND from_team_bref IS NOT NULL
              AND trade_season >= 1990
            GROUP BY from_team_bref
            """
        ).df()
    df["team_bref"] = df["team"].apply(_alias)
    df = df[df["team_bref"].isin(CURRENT_30_FRANCHISES)]
    return (
        df.groupby("team_bref")
        .agg(n_trades=("n_trades", "sum"), mean_delta_war=("mean_delta_war", "mean"))
    )


def org_quality_map() -> pd.DataFrame:
    """Return one row per franchise with dev WAR, trade Δ, and quadrant label.

    Columns: franchise, full_name, dev_war, intl_war, total_dev_war, trade_delta,
             n_mlb_debutees, n_intl, n_trades, quadrant, rank_dev, rank_trade
    """
    df = _load_player_facts()
    dev = _dev_credit(df)
    intl = _intl_credit(df)
    trade = _trade_delta()

    combined = dev[["dev_war", "n_mlb_debutees"]].copy()
    combined["intl_war"] = intl["intl_war"].reindex(combined.index, fill_value=0.0)
    combined["n_intl"] = intl["n_intl"].reindex(combined.index, fill_value=0)
    combined["total_dev_war"] = combined["dev_war"] + combined["intl_war"]
    combined["trade_delta"] = trade["mean_delta_war"].reindex(combined.index, fill_value=0.0)
    combined["n_trades"] = trade["n_trades"].reindex(combined.index, fill_value=0)

    median_dev = combined["total_dev_war"].median()
    median_trade = combined["trade_delta"].median()

    def _quadrant(row: pd.Series) -> str:
        high_dev = row["total_dev_war"] > median_dev
        pos_trade = row["trade_delta"] > median_trade
        if high_dev and pos_trade:
            return "HIGH-DEV / POS-TRADE"
        if high_dev and not pos_trade:
            return "HIGH-DEV / NEG-TRADE"
        if not high_dev and pos_trade:
            return "LOW-DEV / POS-TRADE"
        return "LOW-DEV / NEG-TRADE"

    combined["quadrant"] = combined.apply(_quadrant, axis=1)
    combined["franchise"] = combined.index
    combined["full_name"] = combined["franchise"].map(FULL_NAMES).fillna(combined["franchise"])
    combined["rank_dev"] = combined["total_dev_war"].rank(ascending=False).astype(int)
    combined["rank_trade"] = combined["trade_delta"].rank(ascending=False).astype(int)
    return combined.reset_index(drop=True).sort_values("total_dev_war", ascending=False)
