"""R-31: dev-credit attribution.

Give the drafting team lifetime credit for a player's MLB WAR, regardless of
where that WAR was actually earned.

Rob's insight: trade-outcome metrics (R-10 through R-30) measure how trades
worked out, but they don't credit teams for dev programs that produced
players who *eventually* became MLB stars — even after being traded away.
Logan Forsythe (drafted SDP → traded to TBR → All-Star with TBR) should
add to SDP's dev resume, not just to TBR's "acquired-player-gain" line.

This script builds a "drafting-team credit" leaderboard:
- For each player in our draft_picks table (1990-2024), sum their lifetime
  MLB bWAR.
- Aggregate by drafting team.
- Report: total career WAR, top picks, WAR-per-pick rate.

The result is an independent dev-quality signal that the trade-outcome
work has been mixing in with trade-skill. Cross-comparing the two lets us
ask: which teams are good at DEVELOPING vs which are good at TRADING?

Caveats:
- International free-agent signings (Latin America, Asia) are NOT in our
  draft_picks table; this only covers US/PR/Canada amateur draft.
- "Drafted by X" means we credit X for the player's entire MLB career
  even if they were traded as a prospect before debut. A second pass
  could prorate by minor-league years spent in each system.
- Backtester scope is 1990+ for draft picks; players drafted earlier
  contribute to bWAR but aren't captured here as draft-credit.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db


def load_drafted_player_war() -> pd.DataFrame:
    """For every player in draft_picks, sum their MLB career WAR."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            WITH player_career_war AS (
                SELECT mlb_id, SUM(war) AS career_war, COUNT(DISTINCT year_id) AS mlb_seasons
                FROM bwar_player_seasons
                WHERE mlb_id IS NOT NULL
                GROUP BY mlb_id
            )
            SELECT
                d.team_id,
                d.team_name AS drafting_team,
                d.draft_year,
                d.pick_round,
                d.pick_number,
                d.overall_rank,
                d.mlb_player_id,
                d.player_name AS drafted_name,
                pcw.career_war,
                pcw.mlb_seasons
            FROM draft_picks d
            LEFT JOIN player_career_war pcw ON pcw.mlb_id = d.mlb_player_id
            WHERE d.mlb_player_id IS NOT NULL
            """
        ).df()
    return df


def team_rollup(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per drafting team (current MLB-team name)."""
    grouped = df.groupby("drafting_team").agg(
        n_picks_made=("mlb_player_id", "count"),
        n_picks_reached_mlb=("career_war", lambda s: int(s.notna().sum())),
        total_career_war=("career_war", "sum"),
        median_career_war=("career_war", "median"),
        mean_career_war=("career_war", "mean"),
    )
    grouped["reach_rate"] = grouped["n_picks_reached_mlb"] / grouped["n_picks_made"]
    grouped["total_war_per_pick"] = grouped["total_career_war"] / grouped["n_picks_made"]
    grouped["total_war_per_mlb_player"] = grouped["total_career_war"] / grouped[
        "n_picks_reached_mlb"
    ].replace(0, 1)
    return grouped.sort_values("total_career_war", ascending=False)


def top_picks_per_team(df: pd.DataFrame, team_name: str, k: int = 8) -> pd.DataFrame:
    """The k highest-career-WAR draftees by a given team."""
    return (
        df[df["drafting_team"] == team_name]
        .dropna(subset=["career_war"])
        .sort_values("career_war", ascending=False)
        .head(k)[["draft_year", "pick_round", "drafted_name", "career_war", "mlb_seasons"]]
    )


def hit_rate_by_round(df: pd.DataFrame, max_round: int = 10) -> pd.DataFrame:
    """Per pick_round, what fraction of picks become productive MLB players?"""
    df = df.copy()
    df["pick_round_num"] = pd.to_numeric(df["pick_round"], errors="coerce")
    df["productive"] = df["career_war"] >= 5.0
    df["solid"] = df["career_war"] >= 1.0
    df = df[df["pick_round_num"].between(1, max_round)]
    return (
        df.groupby("pick_round_num")
        .agg(
            n_picks=("mlb_player_id", "count"),
            n_reached_mlb=("career_war", lambda s: int(s.notna().sum())),
            n_solid_war_1plus=("solid", "sum"),
            n_star_war_5plus=("productive", "sum"),
        )
        .assign(
            reach_rate=lambda d: d["n_reached_mlb"] / d["n_picks"],
            solid_rate=lambda d: d["n_solid_war_1plus"] / d["n_picks"],
            star_rate=lambda d: d["n_star_war_5plus"] / d["n_picks"],
        )
    )


def main() -> None:
    """Run dev-credit attribution analysis."""
    df = load_drafted_player_war()
    print(f"Loaded {len(df)} draft-pick rows with mlb_player_id (1990-2024)")
    print(f"  of which {df['career_war'].notna().sum()} reached MLB and have bWAR data")
    print()

    print("=" * 95)
    print("DEV-CREDIT LEADERBOARD: total career WAR produced by team's draftees (1990-2024)")
    print("=" * 95)
    roll = team_rollup(df)
    print(
        f"{'rank':>4}  {'drafting team':<28}  {'picks':>6}  {'→MLB':>5}  "
        f"{'reach%':>6}  {'total WAR':>9}  {'WAR/pick':>8}  {'WAR/MLBer':>9}"
    )
    for i, (team, r) in enumerate(roll.iterrows(), 1):
        print(
            f"{i:>4}  {str(team)[:28]:<28}  {int(r['n_picks_made']):>6}  "
            f"{int(r['n_picks_reached_mlb']):>5}  {r['reach_rate']:>6.1%}  "
            f"{r['total_career_war']:>9.1f}  {r['total_war_per_pick']:>8.3f}  "
            f"{r['total_war_per_mlb_player']:>9.2f}"
        )

    print("\n" + "=" * 95)
    print("HIGHLIGHT: Top draftees per regime-discussion team (their dev resume)")
    print("=" * 95)
    for team in (
        "Los Angeles Dodgers",
        "Houston Astros",
        "Cleveland Guardians",
        "Cleveland Indians",
        "San Diego Padres",
        "Texas Rangers",
        "Oakland Athletics",
        "Tampa Bay Rays",
        "Milwaukee Brewers",
    ):
        top = top_picks_per_team(df, team)
        if top.empty:
            continue
        print(f"\n{team}:")
        for _, r in top.iterrows():
            print(
                f"  {int(r['draft_year'])} R{r['pick_round']:<3}  "
                f"{str(r['drafted_name'])[:28]:<28}  career WAR={r['career_war']:>+6.1f}  "
                f"({int(r['mlb_seasons'])} seasons)"
            )

    print("\n" + "=" * 95)
    print("HIT RATES BY PICK ROUND — what does the league average produce per round?")
    print("=" * 95)
    rounds = hit_rate_by_round(df)
    print(
        f"{'round':>5}  {'n picks':>8}  {'→MLB':>6}  {'reach%':>6}  "
        f"{'≥1 WAR':>7}  {'solid%':>6}  {'≥5 WAR':>7}  {'star%':>6}"
    )
    for round_num, r in rounds.iterrows():
        print(
            f"{int(round_num):>5}  {int(r['n_picks']):>8}  "
            f"{int(r['n_reached_mlb']):>6}  {r['reach_rate']:>6.1%}  "
            f"{int(r['n_solid_war_1plus']):>7}  {r['solid_rate']:>6.1%}  "
            f"{int(r['n_star_war_5plus']):>7}  {r['star_rate']:>6.1%}"
        )


if __name__ == "__main__":
    main()
