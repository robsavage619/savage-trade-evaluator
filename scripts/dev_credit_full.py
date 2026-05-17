"""R-31-v3: complete dev-credit attribution.

Combines four fixes Rob asked for in one pass:
1. Franchise-history alias mapping (TBD↔TBR, FLO↔MIA, MON↔WSN, ANA→LAA, etc.)
2. Scout-to-sign conversion rate by round
3. International signing proxy (post-1990 MLB debutees NOT in draft_picks)
4. 2D (dev-credit, trade-results) coordinate map

The international-signing proxy is imperfect: we don't have a clean public
dataset of amateur international signings (MLB Trade Rumors and Baseball
America aggregate these but no API). Best proxy available with our data:
players who debuted in MLB after 1990 AND are not in our draft_picks table.
That excludes most US/PR/Canada draftees and captures most Latin / Asian
amateur free agents. Caveats:
  - Pre-1990 draftees who debuted in early 1990s get miscounted as int'l
  - Some independent-league signings get counted as int'l
  - The "signing team" is the first MLB team, which misses prospect trades
    that happened in the minors (e.g. acquired-from-Cuba then traded as A-ball)
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db

# Franchise rename map: historical bref → current bref. Only same-franchise
# lineage; Negro Leagues / Federal League / 1800s teams are filtered out by
# the CURRENT_30_FRANCHISES whitelist below, not mapped here.
FRANCHISE_ALIASES: dict[str, str] = {
    # Modern renames (post-1990)
    "TBD": "TBR",  # Devil Rays → Rays (2008)
    "FLA": "MIA",  # Florida Marlins → Miami Marlins (2012)
    "FLO": "MIA",  # alt code
    "MON": "WSN",  # Expos → Nationals (2005)
    "ANA": "LAA",  # Anaheim Angels → LA Angels (2005)
    "CAL": "LAA",  # California Angels → LA Angels
    # B-Ref alt spellings the bWAR data uses
    "CHA": "CHW",
    "KCA": "OAK",  # Kansas City A's → Oakland A's (1968)
    "PHA": "OAK",  # Philadelphia A's → KC A's → Oakland A's
    "LAN": "LAD",
    "BRO": "LAD",  # Brooklyn Dodgers → LA Dodgers (1958)
    "NYA": "NYY",
    "NYN": "NYM",
    "NYG": "SFG",  # NY Giants → SF Giants (1958)
    "SDN": "SDP",
    "SFN": "SFG",
    "SLN": "STL",
    "BSN": "ATL",  # Boston Braves → Milwaukee → Atlanta
    "MLN": "ATL",  # Milwaukee Braves stop
    "SLB": "BAL",  # St. Louis Browns → Orioles (1954)
    "WS1": "MIN",  # Original Senators → Twins (1961)
    "WS2": "TEX",  # Expansion Senators → Rangers (1972)
}

# Only output current 30 MLB franchises. Negro Leagues / Federal / 1800s
# teams are dropped entirely.
CURRENT_30_FRANCHISES: set[str] = {
    "ARI",
    "ATL",
    "BAL",
    "BOS",
    "CHC",
    "CHW",
    "CIN",
    "CLE",
    "COL",
    "DET",
    "HOU",
    "KCR",
    "LAA",
    "LAD",
    "MIA",
    "MIL",
    "MIN",
    "NYM",
    "NYY",
    "OAK",
    "PHI",
    "PIT",
    "SDP",
    "SEA",
    "SFG",
    "STL",
    "TBR",
    "TEX",
    "TOR",
    "WSN",
}

# Map "drafting_team_name" (full name from draft_picks) to current bref_code.
# Some renamed teams appear under the historical name in our draft_picks rows.
DRAFT_NAME_TO_BREF: dict[str, str] = {
    "San Diego Padres": "SDP",
    "Los Angeles Dodgers": "LAD",
    "Boston Red Sox": "BOS",
    "New York Yankees": "NYY",
    "New York Mets": "NYM",
    "Atlanta Braves": "ATL",
    "Houston Astros": "HOU",
    "Cleveland Indians": "CLE",
    "Cleveland Guardians": "CLE",
    "Texas Rangers": "TEX",
    "Tampa Bay Devil Rays": "TBR",
    "Tampa Bay Rays": "TBR",
    "Florida Marlins": "MIA",
    "Miami Marlins": "MIA",
    "Montreal Expos": "WSN",
    "Washington Nationals": "WSN",
    "Anaheim Angels": "LAA",
    "California Angels": "LAA",
    "Los Angeles Angels": "LAA",
    "Los Angeles Angels of Anaheim": "LAA",
    "Athletics": "OAK",
    "Oakland Athletics": "OAK",
    "Toronto Blue Jays": "TOR",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Detroit Tigers": "DET",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "St. Louis Cardinals": "STL",
    "Seattle Mariners": "SEA",
    "San Francisco Giants": "SFG",
    "Baltimore Orioles": "BAL",
    "Kansas City Royals": "KCR",
    "Colorado Rockies": "COL",
    "Arizona Diamondbacks": "ARI",
}


def _alias(bref: str | None) -> str | None:
    """Resolve historical bref code to current."""
    if bref is None:
        return None
    return FRANCHISE_ALIASES.get(bref, bref)


def load_player_facts() -> pd.DataFrame:
    """Return one row per player: first_mlb_team_bref, career WAR, drafted-by-bref."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            WITH career AS (
                SELECT mlb_id, SUM(war) AS career_war, COUNT(DISTINCT year_id) AS mlb_seasons,
                       MIN(year_id) AS first_year
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
            SELECT c.mlb_id,
                   fs.first_mlb_team_raw,
                   c.career_war,
                   c.mlb_seasons,
                   c.first_year
            FROM career c
            LEFT JOIN first_stint fs ON fs.mlb_id = c.mlb_id
            """
        ).df()

    # Apply franchise alias
    df["first_mlb_team"] = df["first_mlb_team_raw"].apply(_alias)

    # Drafted set
    with db.connect(read_only=True) as conn:
        drafted = conn.execute(
            """
            SELECT mlb_player_id, MIN(draft_year) AS first_draft_year,
                   ANY_VALUE(team_name) AS drafting_team_name
            FROM draft_picks
            WHERE mlb_player_id IS NOT NULL
            GROUP BY mlb_player_id
            """
        ).df()
    drafted["drafting_team_bref"] = drafted["drafting_team_name"].map(DRAFT_NAME_TO_BREF)
    drafted["drafting_team_bref"] = drafted["drafting_team_bref"].apply(_alias)

    df = df.merge(
        drafted[["mlb_player_id", "drafting_team_bref", "first_draft_year"]],
        left_on="mlb_id",
        right_on="mlb_player_id",
        how="left",
    )
    return df


def dev_credit_by_team(df: pd.DataFrame, since_year: int = 1990) -> pd.DataFrame:
    """Per current-franchise bref, total career WAR for 1990+ debutees."""
    keep = df.dropna(subset=["first_mlb_team", "career_war"]).copy()
    keep = keep[keep["first_year"] >= since_year]
    keep = keep[keep["first_mlb_team"].isin(CURRENT_30_FRANCHISES)]
    return (
        keep.groupby("first_mlb_team")
        .agg(
            n_mlb_debutees=("mlb_id", "count"),
            dev_war=("career_war", "sum"),
            mean_dev_war=("career_war", "mean"),
        )
        .sort_values("dev_war", ascending=False)
    )


def international_dev_credit(df: pd.DataFrame) -> pd.DataFrame:
    """Post-1990 MLB debutees NOT in our draft table → proxy for int'l signings."""
    int_l = df[
        df["drafting_team_bref"].isna()  # not in draft_picks
        & (df["first_year"] >= 1995)  # filter out pre-1990-draft echoes
        & df["first_mlb_team"].notna()
        & df["career_war"].notna()
        & df["first_mlb_team"].isin(CURRENT_30_FRANCHISES)
    ]
    return (
        int_l.groupby("first_mlb_team")
        .agg(
            n_intl=("mlb_id", "count"),
            intl_war=("career_war", "sum"),
            top_war=("career_war", "max"),
        )
        .sort_values("intl_war", ascending=False)
    )


def scout_to_sign_by_round() -> pd.DataFrame:
    """Per draft round, % of picks who debuted for the drafting team."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            WITH first_stint AS (
                SELECT mlb_id, team_id AS first_mlb_team
                FROM (
                    SELECT mlb_id, team_id, year_id,
                           ROW_NUMBER() OVER (PARTITION BY mlb_id ORDER BY year_id, stint_id) AS rn
                    FROM bwar_player_seasons
                    WHERE mlb_id IS NOT NULL AND team_id IS NOT NULL
                ) WHERE rn = 1
            )
            SELECT d.pick_round, d.team_name, d.mlb_player_id, fs.first_mlb_team
            FROM draft_picks d
            LEFT JOIN first_stint fs ON fs.mlb_id = d.mlb_player_id
            WHERE d.mlb_player_id IS NOT NULL
            """
        ).df()
    df["drafting_bref"] = df["team_name"].map(DRAFT_NAME_TO_BREF).apply(_alias)
    df["first_bref"] = df["first_mlb_team"].apply(_alias)
    df["reached_mlb"] = df["first_bref"].notna()
    df["debuted_with_drafter"] = (df["drafting_bref"] == df["first_bref"]) & df["reached_mlb"]
    df["round_num"] = pd.to_numeric(df["pick_round"], errors="coerce")
    rounds = (
        df[df["round_num"].between(1, 15)]
        .groupby("round_num")
        .agg(
            n_picks=("mlb_player_id", "count"),
            n_reached=("reached_mlb", "sum"),
            n_debuted_with_drafter=("debuted_with_drafter", "sum"),
        )
    )
    rounds["reach_rate"] = rounds["n_reached"] / rounds["n_picks"]
    rounds["scout_to_sign_rate"] = rounds["n_debuted_with_drafter"] / rounds["n_reached"].replace(
        0, 1
    )
    return rounds


def trade_result_by_team() -> pd.DataFrame:
    """Per receiver-bref, cumulative trade WAR delta (departed players' Δ)."""
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
        .sort_values("mean_delta_war")
    )


def main() -> None:
    """Run all four analyses."""
    print("Loading player + draft data...")
    df = load_player_facts()
    print(
        f"  {len(df)} players with bWAR data; "
        f"{df['drafting_team_bref'].notna().sum()} in draft_picks"
    )
    print()

    dev = dev_credit_by_team(df)
    intl = international_dev_credit(df)
    trade = trade_result_by_team()

    # === 1) DEV CREDIT with franchise aliases ===
    print("=" * 100)
    print("DEV CREDIT (career WAR of players who DEBUTED for this team, franchise aliases applied)")
    print("=" * 100)
    print(f"{'rank':>4}  {'team':<5}  {'n debutees':>10}  {'dev WAR':>9}  {'mean WAR/debutee':>17}")
    for i, (team, r) in enumerate(dev.iterrows(), 1):
        print(
            f"{i:>4}  {team:<5}  {int(r['n_mlb_debutees']):>10}  "
            f"{r['dev_war']:>9.1f}  {r['mean_dev_war']:>17.2f}"
        )

    # === 2) INTERNATIONAL SIGNING PROXY ===
    print("\n" + "=" * 100)
    print("INTERNATIONAL SIGNING PROXY (post-1995 debutees NOT in draft_picks)")
    print("=" * 100)
    print("Excludes US/PR/Canada amateur draftees. Most rows = Latin / Asian amateur FAs.")
    print()
    print(f"{'rank':>4}  {'team':<5}  {'n intl':>9}  {'intl WAR':>9}  {'top single WAR':>15}")
    for i, (team, r) in enumerate(intl.iterrows(), 1):
        print(
            f"{i:>4}  {team:<5}  {int(r['n_intl']):>9}  "
            f"{r['intl_war']:>9.1f}  {r['top_war']:>15.1f}"
        )

    # === 3) SCOUT-TO-SIGN CONVERSION BY ROUND ===
    print("\n" + "=" * 100)
    print("SCOUT-TO-SIGN CONVERSION BY DRAFT ROUND")
    print("=" * 100)
    print("scout-to-sign = % of MLB-reaching draftees who debuted FOR the team that drafted them")
    print()
    rounds = scout_to_sign_by_round()
    hdr = (
        f"{'round':>5}  {'n picks':>8}  {'reach MLB':>10}  "
        f"{'debuted-with-drafter':>22}  {'rate':>6}"
    )
    print(hdr)
    for round_num, r in rounds.iterrows():
        print(
            f"{int(round_num):>5}  {int(r['n_picks']):>8}  {int(r['n_reached']):>10}  "
            f"{int(r['n_debuted_with_drafter']):>22}  {r['scout_to_sign_rate']:>5.1%}"
        )

    # === 4) 2D MAP: DEV-CREDIT (incl. intl) vs TRADE-DELTA ===
    print("\n" + "=" * 100)
    print("2D ORG QUALITY MAP: total DEV WAR (debut + int'l) vs mean TRADE Δ WAR")
    print("=" * 100)
    print(
        "DEV-WAR higher = better dev pipeline. TRADE-Δ negative = sell-high or system-tax pattern."
    )
    print()
    combined = dev[["dev_war"]].copy()
    combined["intl_war"] = intl["intl_war"].reindex(combined.index, fill_value=0)
    combined["total_dev_war"] = combined["dev_war"] + combined["intl_war"]
    combined["trade_delta"] = trade["mean_delta_war"].reindex(combined.index, fill_value=0.0)
    combined = combined.sort_values("total_dev_war", ascending=False)

    print(
        f"{'rank':>4}  {'team':<5}  {'dev WAR':>9}  {'intl WAR':>9}  "
        f"{'TOTAL':>9}  {'trade Δ':>9}  quadrant"
    )
    median_dev = combined["total_dev_war"].median()
    median_trade = combined["trade_delta"].median()
    print(f"  (medians: total dev = {median_dev:.1f}, trade Δ = {median_trade:+.3f})")
    print()
    for i, (team, r) in enumerate(combined.iterrows(), 1):
        dev_high = r["total_dev_war"] > median_dev
        trade_pos = r["trade_delta"] > median_trade
        if dev_high and trade_pos:
            q = "HIGH-DEV  POS-TRADE"
        elif dev_high and not trade_pos:
            q = "HIGH-DEV  NEG-TRADE"
        elif not dev_high and trade_pos:
            q = "LOW-DEV   POS-TRADE"
        else:
            q = "LOW-DEV   NEG-TRADE"
        print(
            f"{i:>4}  {team:<5}  {r['dev_war']:>9.1f}  {r['intl_war']:>9.1f}  "
            f"{r['total_dev_war']:>9.1f}  {r['trade_delta']:>+9.4f}  {q}"
        )


if __name__ == "__main__":
    main()
