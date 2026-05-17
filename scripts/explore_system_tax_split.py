"""Test B: split LAD-departed hitters by pre-trade xwOBA, see if high group drops more.

Selection-cancellation hypothesis: the LAD-traded population is a mix of
(a) sell-high prospects the org secretly distrusts (expect drop) and
(b) forced-to-move-for-win-now prospects (expect average). Averaging the
two gives the noise-floor mid-pack result we saw.

If your "system tax" thesis is right, the high-pre-trade-xwOBA cohort
should drop more than the low cohort — those are the players the system
was actively inflating. We also bucket the league at large and the
analytics-leader comp set (HOU/BOS/TBR/SDP/CLE) as references.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from savage_trade_evaluator.storage import db

HIGH_THRESHOLD = 0.330
LOW_THRESHOLD = 0.300

# Industry-recognized analytics-forward orgs as of ~2018-2024
ANALYTICS_LEADERS = ("HOU", "TBR", "BOS", "SDP", "CLE")
COMP_BUCKETS = {
    "LAD": ("LAD",),
    "Analytics leaders (HOU/TBR/BOS/SDP/CLE)": ANALYTICS_LEADERS,
    "All other orgs": None,  # sentinel — computed as everything else
}


def bucket_query(orgs: tuple[str, ...] | None, exclude_orgs: tuple[str, ...] = ()) -> str:
    """Build SQL filter for an origin-org bucket."""
    if orgs is None:
        excl = "', '".join(exclude_orgs)
        return f"from_team_bref NOT IN ('{excl}')"
    orgs_list = "', '".join(orgs)
    return f"from_team_bref IN ('{orgs_list}')"


def run_bucket(conn, label: str, where: str) -> None:
    """Print high/low/all split for one origin-org bucket."""
    print(f"--- {label} ---")
    for cohort_name, cohort_filter in [
        (f"HIGH (pre xwOBA >= {HIGH_THRESHOLD})", f"xwoba_t_minus_1 >= {HIGH_THRESHOLD}"),
        (
            f"MID  ({LOW_THRESHOLD} <= pre < {HIGH_THRESHOLD})",
            f"xwoba_t_minus_1 >= {LOW_THRESHOLD} AND xwoba_t_minus_1 < {HIGH_THRESHOLD}",
        ),
        (f"LOW  (pre xwOBA < {LOW_THRESHOLD})", f"xwoba_t_minus_1 < {LOW_THRESHOLD}"),
        ("ALL", "1=1"),
    ]:
        r = conn.execute(
            f"""
            SELECT COUNT(*) AS n,
                   AVG(xwoba_t_plus_1 - xwoba_t_minus_1) AS mean_delta,
                   STDDEV_SAMP(xwoba_t_plus_1 - xwoba_t_minus_1) / SQRT(COUNT(*)) AS sem,
                   AVG(xwoba_t_minus_1) AS mean_pre,
                   AVG(xwoba_t_plus_1) AS mean_post
            FROM trade_player_xwoba_window
            WHERE {where}
              AND xwoba_t_minus_1 IS NOT NULL
              AND xwoba_t_plus_1 IS NOT NULL
              AND ({cohort_filter})
            """
        ).fetchone()
        n, delta, sem, pre, post = r
        if n == 0:
            print(f"  {cohort_name:<42} n=0")
            continue
        sig = "***" if abs(delta) > 2 * sem else (" ** " if abs(delta) > sem else "    ")
        print(
            f"  {cohort_name:<42} n={n:>3}  pre={pre:.3f}  post={post:.3f}  "
            f"delta={delta:>+7.4f}  sem={sem:.4f}  {sig}"
        )
    print()


def main() -> None:
    """Run high/low xwOBA splits per origin-org bucket."""
    with db.connect(read_only=True) as conn:
        print("=" * 80)
        print("xwOBA DROPOFF SPLIT BY PRE-TRADE TIER, BY ORIGIN-ORG BUCKET")
        print("=" * 80)
        print("Significance markers: *** = |delta| > 2*SEM, ** = |delta| > SEM")
        print()

        for label, orgs in COMP_BUCKETS.items():
            if orgs is None:
                # "all other" = everything not in LAD or analytics-leaders
                excluded = ("LAD", *ANALYTICS_LEADERS)
                where = bucket_query(None, exclude_orgs=excluded)
            else:
                where = bucket_query(orgs)
            run_bucket(conn, label, where)

        # Also do LAD-only WAR split for the same reason (since rate vs counting matters)
        print("=" * 80)
        print("LAD-DEPARTED PLAYERS, WAR DROPOFF SPLIT BY PRE-TRADE WAR")
        print("=" * 80)
        for cohort_name, cohort_filter in [
            ("HIGH (war_t-1 >= 2.0)", "war_t_minus_1 >= 2.0"),
            ("MID  (0.5 <= war_t-1 < 2.0)", "war_t_minus_1 >= 0.5 AND war_t_minus_1 < 2.0"),
            ("LOW  (war_t-1 < 0.5)", "war_t_minus_1 < 0.5"),
        ]:
            r = conn.execute(
                f"""
                SELECT COUNT(*) AS n,
                       AVG(war_t_plus_1 - war_t_minus_1) AS mean_delta,
                       STDDEV_SAMP(war_t_plus_1 - war_t_minus_1) / SQRT(COUNT(*)) AS sem,
                       AVG(war_t_minus_1) AS mean_pre,
                       AVG(war_t_plus_1) AS mean_post
                FROM trade_player_war_window
                WHERE from_team_bref = 'LAD'
                  AND war_t_minus_1 IS NOT NULL
                  AND war_t_plus_1 IS NOT NULL
                  AND trade_season >= 2010
                  AND ({cohort_filter})
                """
            ).fetchone()
            n, delta, sem, pre, post = r
            if n == 0:
                print(f"  {cohort_name:<28} n=0")
                continue
            sig = "***" if abs(delta) > 2 * sem else (" ** " if abs(delta) > sem else "    ")
            print(
                f"  {cohort_name:<28} n={n:>3}  pre={pre:>+5.2f}  post={post:>+5.2f}  "
                f"delta={delta:>+6.3f}  sem={sem:.3f}  {sig}"
            )
        print()

        # The key visualization: high-pre-xwOBA LAD departures, sorted
        print("=" * 80)
        print("LAD-DEPARTED HITTERS WITH HIGH PRE-TRADE xwOBA (>= 0.330)")
        print("=" * 80)
        rows = conn.execute(
            f"""
            SELECT trade_season, player_name, to_team_bref,
                   xwoba_t_minus_1, xwoba_t_plus_1,
                   xwoba_t_plus_1 - xwoba_t_minus_1 AS delta
            FROM trade_player_xwoba_window
            WHERE from_team_bref = 'LAD'
              AND xwoba_t_minus_1 >= {HIGH_THRESHOLD}
              AND xwoba_t_plus_1 IS NOT NULL
            ORDER BY trade_season, delta
            """
        ).fetchall()
        print(f"{'season':>6} {'player':<26} {'to':<5} {'pre':>6} {'post':>6} {'delta':>7}")
        for season, name, to, pre, post, delta in rows:
            print(f"{season:>6} {name[:26]:<26} {to:<5} {pre:>6.3f} {post:>6.3f} {delta:>+7.3f}")


if __name__ == "__main__":
    main()
