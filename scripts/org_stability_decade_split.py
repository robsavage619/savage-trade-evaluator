"""R-25: Are organizations static, or do GM regimes matter?

Splits each team's trade history by decade and refits the origin-org system-tax
test (R-12/R-17 lineage) on each decade independently. If a team's intercept
is consistent across decades, the system-tax effect is organizational culture.
If it shifts dramatically, the effect is GM/regime-driven.

Plain English: did LAD-1995 trades produce the same pattern as LAD-2020 trades?

Methodology:
- Fit multilevel with (origin x decade) interaction terms.
- Compare within-team variance across decades vs between-team variance.
- For each team, report decade-specific intercepts side by side.

WAR outcome (1990+ coverage; rate-based outcomes don't extend back far enough
to support decade splits per D-26).
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
MIN_N_PER_TEAM_DECADE = 8  # min trades for a (team, decade) to be included
HIGHLIGHT_TEAMS = ("LAD", "HOU", "CLE", "NYM", "TBR", "BOS", "SDP", "NYY", "STL", "OAK")


def load_data() -> pd.DataFrame:
    """Load trade legs with origin and decade markers."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT from_team_bref AS origin,
                   trade_season,
                   FLOOR(trade_season / 10) * 10 AS decade,
                   war_t_minus_1 AS pre_war,
                   war_t_plus_1 - war_t_minus_1 AS delta_war
            FROM trade_player_war_window
            WHERE war_t_minus_1 IS NOT NULL
              AND war_t_plus_1 IS NOT NULL
              AND from_team_bref IS NOT NULL
              AND trade_season >= 1990
            """
        ).df()
    df["decade"] = df["decade"].astype(int).astype(str) + "s"
    df["team_decade"] = df["origin"] + "_" + df["decade"]
    # filter (team, decade) cells with enough data
    counts = df.groupby("team_decade").size()
    keep = counts[counts >= MIN_N_PER_TEAM_DECADE].index
    df = df[df["team_decade"].isin(keep)].reset_index(drop=True)
    return df


def fit(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """Fit multilevel with (team x decade) as the cluster. Return summary."""
    cells = sorted(df["team_decade"].unique())
    c2i = {c: i for i, c in enumerate(cells)}
    c_idx = np.array([c2i[c] for c in df["team_decade"]])

    pre_z = (df["pre_war"] - df["pre_war"].mean()) / df["pre_war"].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    y = df["delta_war"].to_numpy(dtype=float)

    with pm.Model(coords={"cell": cells}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=0.5)
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=1.0)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=0.5)
        tau = pm.HalfNormal("tau_cell", sigma=0.5)
        alpha_cell = pm.Normal("alpha_cell", mu=0.0, sigma=tau, dims="cell")
        sigma = pm.HalfNormal("sigma", sigma=2.0)
        mu = (
            alpha
            + alpha_cell[c_idx]
            + beta_pre * pre_z.to_numpy(dtype=float)
            + beta_season * season_z.to_numpy(dtype=float)
        )
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y)
        trace = pm.sample(
            draws=2000,
            tune=2000,
            chains=4,
            random_seed=SEED,
            progressbar=False,
            target_accept=0.97,
        )

    print("\n=== Population posteriors ===")
    for name in ("alpha", "beta_pre", "tau_cell", "sigma"):
        v = trace.posterior[name].values.reshape(-1)
        print(
            f"  {name:<10} mean={v.mean():>+8.4f}  5%={np.percentile(v, 5):>+8.4f}  "
            f"95%={np.percentile(v, 95):>+8.4f}"
        )

    ac = trace.posterior["alpha_cell"].values.reshape(-1, len(cells))
    summary = pd.DataFrame(
        {
            "cell": cells,
            "n": [int((df["team_decade"] == c).sum()) for c in cells],
            "mean": ac.mean(axis=0),
            "p05": np.percentile(ac, 5, axis=0),
            "p95": np.percentile(ac, 95, axis=0),
            "p_neg": (ac < 0).mean(axis=0),
        }
    )
    summary[["origin", "decade"]] = summary["cell"].str.split("_", expand=True)
    return summary, ac, cells


def report_within_team(summary: pd.DataFrame) -> None:
    """For each highlight team, show their decade-by-decade intercepts."""
    print("\n" + "=" * 80)
    print("WITHIN-TEAM STABILITY across decades (intercept mean ± 90% CI)")
    print("=" * 80)
    print(f"{'team':<6} " + " ".join(f"{d:>20}" for d in ("1990s", "2000s", "2010s", "2020s")))
    for team in HIGHLIGHT_TEAMS:
        row = [f"{team:<6}"]
        for decade in ("1990s", "2000s", "2010s", "2020s"):
            sub = summary[(summary["origin"] == team) & (summary["decade"] == decade)]
            if sub.empty:
                row.append(f"{'—':>20}")
            else:
                r = sub.iloc[0]
                row.append(f"{r['mean']:+.3f}[{r['p05']:+.2f},{r['p95']:+.2f}]")
        print(" ".join(row))


def variance_decomposition(summary: pd.DataFrame) -> None:
    """Plain-English: how much of the variation in intercepts is within-team vs between-team?"""
    summary = summary.copy()
    # restrict to teams with >= 2 decades of data
    team_decade_counts = summary.groupby("origin").size()
    multi_decade_teams = team_decade_counts[team_decade_counts >= 2].index
    multi = summary[summary["origin"].isin(multi_decade_teams)].copy()

    overall_var = float(multi["mean"].var())
    between_team_var = float(multi.groupby("origin")["mean"].mean().var())
    within_team_var = float(multi.groupby("origin")["mean"].apply(lambda s: s.var()).mean())

    print("\n" + "=" * 80)
    print("VARIANCE DECOMPOSITION (teams with 2+ decades of data)")
    print("=" * 80)
    print(f"  total variance of decade-cell intercepts:  {overall_var:.5f}")
    print(
        f"  between-team variance (org culture):       {between_team_var:.5f}  "
        f"({100 * between_team_var / overall_var:.1f}% of total)"
    )
    print(
        f"  within-team variance (GM/era shift):       {within_team_var:.5f}  "
        f"({100 * within_team_var / overall_var:.1f}% of total)"
    )
    if between_team_var > within_team_var * 1.5:
        verdict = "ORG CULTURE DOMINANT — origin-org effects largely persist across regimes"
    elif within_team_var > between_team_var * 1.5:
        verdict = "REGIME/GM DOMINANT — origin-org effects shift substantially across decades"
    else:
        verdict = "MIXED — both org culture and regime contribute meaningfully"
    print(f"\n  Verdict: {verdict}")


def main() -> None:
    """Run the org-stability decade-split test."""
    df = load_data()
    print(f"Loaded {len(df)} trade legs across {df['team_decade'].nunique()} (team, decade) cells")
    print(f"Decades present: {sorted(df['decade'].unique())}")
    print()

    summary, _, _ = fit(df)
    report_within_team(summary)
    variance_decomposition(summary)


if __name__ == "__main__":
    main()
