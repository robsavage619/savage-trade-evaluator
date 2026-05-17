"""R-10-prep: Origin-org system-tax exploration.

Thesis: prospects/young players developed in tech-forward orgs (LAD/HOU/BOS/TBR)
underperform their pedigree after trade. Mirror image of the MVP Machine Ch 9
receiving-side dev-fit feature we already have.

Step 1: For each origin org, compute the mean post-trade delta on departed
players for both xwOBA (hitters, 2015+) and WAR (everyone, 2010+). Rank.
Look for LAD/HOU/BOS/TBR as negative outliers.

Caveat (Step 2 territory): cannot yet distinguish "system tax" (a) from
"sell-high skill" (b) — both predict negative dropoff. Requires synthetic-control
counterfactual against equally-rated prospects from other orgs.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from savage_trade_evaluator.storage import db

MIN_N = 8  # minimum departed-player trades per org to include in rank


def main() -> None:
    """Print origin-org rank tables by post-trade xwOBA and WAR delta."""
    with db.connect(read_only=True) as conn:
        print("=" * 78)
        print("ORIGIN-ORG xwOBA DROPOFF ON DEPARTED HITTERS (2015+, Statcast era)")
        print("delta = xwoba_t_plus_1 - xwoba_t_minus_1; negative = dropoff after leaving")
        print("=" * 78)
        rows = conn.execute(
            f"""
            SELECT from_team_bref AS origin,
                   COUNT(*) AS n,
                   AVG(xwoba_t_plus_1 - xwoba_t_minus_1) AS mean_delta,
                   STDDEV_SAMP(xwoba_t_plus_1 - xwoba_t_minus_1) / SQRT(COUNT(*)) AS sem
            FROM trade_player_xwoba_window
            WHERE xwoba_t_minus_1 IS NOT NULL
              AND xwoba_t_plus_1 IS NOT NULL
              AND from_team_bref IS NOT NULL
            GROUP BY from_team_bref
            HAVING COUNT(*) >= {MIN_N}
            ORDER BY mean_delta ASC
            """
        ).fetchall()
        print(f"{'rank':>4} {'org':<5} {'n':>4} {'mean_delta':>11} {'sem':>8}")
        for i, (org, n, mean_d, sem) in enumerate(rows, 1):
            marker = " <--" if org in ("LAD", "HOU", "BOS", "TBA") else ""
            print(f"{i:>4} {org:<5} {n:>4} {mean_d:>+11.4f} {sem:>8.4f}{marker}")

        print()
        print("=" * 78)
        print("ORIGIN-ORG WAR DROPOFF ON DEPARTED PLAYERS (all trade-seasons w/ bWAR)")
        print("delta = war_t_plus_1 - war_t_minus_1; negative = dropoff after leaving")
        print("=" * 78)
        rows = conn.execute(
            f"""
            SELECT from_team_bref AS origin,
                   COUNT(*) AS n,
                   AVG(war_t_plus_1 - war_t_minus_1) AS mean_delta,
                   STDDEV_SAMP(war_t_plus_1 - war_t_minus_1) / SQRT(COUNT(*)) AS sem
            FROM trade_player_war_window
            WHERE war_t_minus_1 IS NOT NULL
              AND war_t_plus_1 IS NOT NULL
              AND from_team_bref IS NOT NULL
              AND trade_season >= 2010
            GROUP BY from_team_bref
            HAVING COUNT(*) >= {MIN_N}
            ORDER BY mean_delta ASC
            """
        ).fetchall()
        print(f"{'rank':>4} {'org':<5} {'n':>4} {'mean_delta':>11} {'sem':>8}")
        for i, (org, n, mean_d, sem) in enumerate(rows, 1):
            marker = " <--" if org in ("LAD", "HOU", "BOS", "TBA") else ""
            print(f"{i:>4} {org:<5} {n:>4} {mean_d:>+11.4f} {sem:>8.4f}{marker}")

        print()
        print("=" * 78)
        print("YOUNG/PROSPECT-Y SUBSET: WAR DROPOFF on departures where war_t-1 <= 1.0")
        print("(filters out vet-for-vet swaps; isolates the 'system guy' archetype)")
        print("=" * 78)
        rows = conn.execute(
            f"""
            SELECT from_team_bref AS origin,
                   COUNT(*) AS n,
                   AVG(war_t_plus_1 - war_t_minus_1) AS mean_delta,
                   STDDEV_SAMP(war_t_plus_1 - war_t_minus_1) / SQRT(COUNT(*)) AS sem
            FROM trade_player_war_window
            WHERE war_t_minus_1 IS NOT NULL
              AND war_t_plus_1 IS NOT NULL
              AND war_t_minus_1 <= 1.0
              AND from_team_bref IS NOT NULL
              AND trade_season >= 2010
            GROUP BY from_team_bref
            HAVING COUNT(*) >= {MIN_N}
            ORDER BY mean_delta ASC
            """
        ).fetchall()
        print(f"{'rank':>4} {'org':<5} {'n':>4} {'mean_delta':>11} {'sem':>8}")
        for i, (org, n, mean_d, sem) in enumerate(rows, 1):
            marker = " <--" if org in ("LAD", "HOU", "BOS", "TBA") else ""
            print(f"{i:>4} {org:<5} {n:>4} {mean_d:>+11.4f} {sem:>8.4f}{marker}")

        print()
        print("=" * 78)
        print("LAD-SPECIFIC: every hitter who left LAD via trade with xwOBA window")
        print("=" * 78)
        rows = conn.execute(
            """
            SELECT trade_season, player_name, to_team_bref,
                   xwoba_t_minus_1, xwoba_t_plus_1,
                   xwoba_t_plus_1 - xwoba_t_minus_1 AS delta
            FROM trade_player_xwoba_window
            WHERE from_team_bref = 'LAD'
              AND xwoba_t_minus_1 IS NOT NULL
              AND xwoba_t_plus_1 IS NOT NULL
            ORDER BY trade_season, delta
            """
        ).fetchall()
        print(f"{'season':>6} {'player':<26} {'to':<5} {'pre':>6} {'post':>6} {'delta':>7}")
        for season, name, to, pre, post, delta in rows:
            print(f"{season:>6} {name[:26]:<26} {to:<5} {pre:>6.3f} {post:>6.3f} {delta:>+7.3f}")


if __name__ == "__main__":
    main()
