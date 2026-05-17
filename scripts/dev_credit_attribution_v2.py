"""R-31-v2: Dev-credit attribution with proper didn't-sign filtering.

Rob caught a real data error in R-31-v1: Todd Helton (drafted SDP 1992 R2,
didn't sign, drafted COL 1995 R1, signed) was being credited to SDP. SDP
shouldn't get dev-credit for a player who never spent a day in their org.

Fix: split the metric into two clean signals.

  SCOUTING CREDIT — you correctly identified this player as worth picking,
                    regardless of whether they signed.
                    Filter: drafted by you (the current v1 metric, retained
                    for transparency).

  DEV CREDIT      — the player actually entered your org and either debuted
                    for you OR you traded them later (so we still get credit
                    for keeping them long enough to acquire trade value).
                    Filter: player's first MLB team matches the drafting team.

For each team, report both rankings. The gap between them is the story:
- Big SCOUTING > DEV gap = "we identify talent but don't sign / keep them"
- DEV ≈ SCOUTING       = "we sign and develop the players we draft"

This gives the more honest picture of org dev quality.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db


def load_data() -> pd.DataFrame:
    """For every draft pick with mlb_player_id, attach career WAR + first MLB team."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            WITH career AS (
                SELECT mlb_id, SUM(war) AS career_war, COUNT(DISTINCT year_id) AS mlb_seasons
                FROM bwar_player_seasons
                WHERE mlb_id IS NOT NULL
                GROUP BY mlb_id
            ),
            first_stint AS (
                -- For each player, the bref_code of the team where they first played MLB
                SELECT mlb_id, team_id AS first_mlb_team_bref
                FROM (
                    SELECT mlb_id, team_id, year_id,
                           ROW_NUMBER() OVER (PARTITION BY mlb_id ORDER BY year_id, stint_id) AS rn
                    FROM bwar_player_seasons
                    WHERE mlb_id IS NOT NULL AND team_id IS NOT NULL
                ) WHERE rn = 1
            )
            SELECT
                d.draft_year,
                d.pick_round,
                d.team_name AS drafting_team_name,
                t.bref_code AS drafting_team_bref,
                d.mlb_player_id,
                d.player_name AS drafted_name,
                d.signing_bonus,
                c.career_war,
                c.mlb_seasons,
                fs.first_mlb_team_bref,
                -- did the player debut for the drafting team?
                CASE WHEN fs.first_mlb_team_bref = t.bref_code
                     THEN 1 ELSE 0 END AS debuted_with_drafter
            FROM draft_picks d
            LEFT JOIN teams t ON t.name = d.team_name
            LEFT JOIN career c ON c.mlb_id = d.mlb_player_id
            LEFT JOIN first_stint fs ON fs.mlb_id = d.mlb_player_id
            WHERE d.mlb_player_id IS NOT NULL
            """
        ).df()
    return df


def rollup(df: pd.DataFrame, filter_label: str, mask) -> pd.DataFrame:
    """Aggregate (total_war, n_picks, etc.) given a filter mask on draft picks."""
    sub = df[mask].copy()
    g = sub.groupby("drafting_team_name").agg(
        n_picks=("mlb_player_id", "count"),
        n_reached_mlb=("career_war", lambda s: int(s.notna().sum())),
        total_career_war=("career_war", "sum"),
    )
    g["war_per_pick"] = g["total_career_war"] / g["n_picks"]
    g["reach_rate"] = g["n_reached_mlb"] / g["n_picks"]
    g["_label"] = filter_label
    return g


def main() -> None:
    """Compute scouting credit vs dev credit; show the gap."""
    df = load_data()
    print(f"Loaded {len(df)} draft-pick rows with mlb_player_id")
    print(f"  picks where player debuted with drafter:  {df['debuted_with_drafter'].sum()}")
    print(
        f"  picks where player debuted elsewhere:     "
        f"{((df['debuted_with_drafter'] == 0) & df['career_war'].notna()).sum()}"
    )
    print(f"  picks where player never reached MLB:     {df['career_war'].isna().sum()}")
    print()

    # SCOUTING credit — every pick where they reached MLB (anywhere)
    scout = rollup(df, "scouting", df["career_war"].notna())
    # DEV credit — only picks where the player debuted with the drafter
    dev = rollup(df, "dev", df["debuted_with_drafter"] == 1)

    # Merge
    merged = scout.join(dev, lsuffix="_scout", rsuffix="_dev", how="outer")
    merged["dev_war"] = merged["total_career_war_dev"].fillna(0)
    merged["scout_war"] = merged["total_career_war_scout"].fillna(0)
    merged["scout_minus_dev_gap"] = merged["scout_war"] - merged["dev_war"]
    merged = merged.sort_values("dev_war", ascending=False)

    print("=" * 100)
    print("DEV CREDIT vs SCOUTING CREDIT — total career WAR by drafting team")
    print("=" * 100)
    print(
        f"{'rank':>4}  {'drafting team':<28}  "
        f"{'DEV-WAR':>9}  {'SCOUT-WAR':>10}  {'gap':>8}  {'gap%':>6}  story"
    )
    for i, (team, row) in enumerate(merged.iterrows(), 1):
        gap = row["scout_minus_dev_gap"]
        scout_war = row["scout_war"]
        gap_pct = (gap / scout_war * 100) if scout_war > 0 else 0
        story = ""
        if gap_pct > 25:
            story = "  ← LARGE leak (identified but didn't keep)"
        elif gap_pct < 10:
            story = "  ← tight (signed/kept what they drafted)"
        print(
            f"{i:>4}  {str(team)[:28]:<28}  "
            f"{row['dev_war']:>9.1f}  {row['scout_war']:>10.1f}  "
            f"{gap:>8.1f}  {gap_pct:>5.1f}%{story}"
        )

    # Now: per-team top draftees, separated by debuted-with-drafter or not
    print("\n" + "=" * 100)
    print("PER-TEAM SPLIT: top draftees who DEBUTED vs DIDN'T DEBUT for the drafting team")
    print("=" * 100)
    for team in (
        "San Diego Padres",
        "Los Angeles Dodgers",
        "Houston Astros",
        "Cleveland Guardians",
        "Cleveland Indians",
        "Boston Red Sox",
        "Texas Rangers",
        "Tampa Bay Rays",
    ):
        sub = df[(df["drafting_team_name"] == team) & df["career_war"].notna()]
        if sub.empty:
            continue
        print(f"\n{team}:")
        for label, mask in [
            ("DEBUTED for them (sign-and-develop credit)", sub["debuted_with_drafter"] == 1),
            ("DEBUTED ELSEWHERE (scouted only, didn't keep)", sub["debuted_with_drafter"] == 0),
        ]:
            print(f"  {label}:")
            top = sub[mask].sort_values("career_war", ascending=False).head(5)
            for _, r in top.iterrows():
                bonus = r["signing_bonus"]
                bonus_str = f"${bonus / 1000:.0f}K" if pd.notna(bonus) and bonus > 0 else "no-bonus"
                first_team = r["first_mlb_team_bref"] or "—"
                print(
                    f"    {int(r['draft_year'])} R{r['pick_round']:<3} "
                    f"{str(r['drafted_name'])[:24]:<24}  "
                    f"career WAR={r['career_war']:>+6.1f}  "
                    f"first-MLB={first_team:<4}  bonus={bonus_str}"
                )


if __name__ == "__main__":
    main()
