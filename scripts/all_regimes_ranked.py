"""R-28: show all 79 regimes ranked, not just our cherry-picked 10.

Rob's correct critique: we've been name-checking the same 10 teams
(LAD/HOU/CLE/OAK/STL + the "analytics leaders") through R-10 through R-27.
There are 30 MLB teams and ~79 regimes. What does the full ranking look like?
Are we missing real outliers because we never bothered to look at them?

Outputs the regime-controlled multilevel intercept for every regime
with n >= 10 trades, sorted most negative to most positive. Highlights
where our prior "highlight set" sits in the full distribution and
surfaces under-discussed regimes worth investigating.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
MIN_N = 10  # raise from R-27's 6 to filter noisier regimes

PRIOR_HIGHLIGHT = {
    "LAD_Andrew Friedman",
    "LAD_Ned Colletti",
    "HOU_Jeff Luhnow",
    "HOU_James Click",
    "HOU_Dana Brown",
    "CLE_Chris Antonetti",
    "CLE_Mark Shapiro",
    "TBR_Andrew Friedman",
    "SDP_A. J. Preller",
    "OAK_Billy Beane",
    "STL_John Mozeliak",
    "BOS_Theo Epstein",
    "BOS_Ben Cherington",
    "BOS_Chaim Bloom",
}


def main() -> None:
    """Fit + print full regime rankings on the WAR outcome."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT tpu.from_team_bref AS origin_team,
                   tra.regime_id AS origin_regime,
                   tpu.trade_season,
                   w.war_t_minus_1 AS pre,
                   w.war_t_plus_1 - w.war_t_minus_1 AS delta
            FROM trade_player_war_window w
            JOIN trade_player_unified tpu
                ON tpu.trade_event_id = w.trade_event_id
                AND tpu.leg_index = w.leg_index
            JOIN team_regime_assignments tra
                ON tra.bref_code = tpu.from_team_bref
                AND tra.season = tpu.trade_season
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND tra.regime_id IS NOT NULL
            """
        ).df()

    counts = df.groupby("origin_regime").size()
    keep = counts[counts >= MIN_N].index
    df = df[df["origin_regime"].isin(keep)].reset_index(drop=True)
    print(
        f"Loaded {len(df)} trade legs across {df['origin_regime'].nunique()} regimes (MIN_N={MIN_N})"
    )

    regimes = sorted(df["origin_regime"].unique())
    r2i = {r: i for i, r in enumerate(regimes)}
    r_idx = np.array([r2i[r] for r in df["origin_regime"]])

    pre_z = (df["pre"] - df["pre"].mean()) / df["pre"].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    y = df["delta"].to_numpy(dtype=float)

    with pm.Model(coords={"regime": regimes}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=0.5)
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=1.0)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=0.5)
        tau = pm.HalfNormal("tau_regime", sigma=0.5)
        alpha_regime = pm.Normal("alpha_regime", mu=0.0, sigma=tau, dims="regime")
        sigma = pm.HalfNormal("sigma", sigma=2.0)
        mu = (
            alpha
            + alpha_regime[r_idx]
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

    ar = trace.posterior["alpha_regime"].values.reshape(-1, len(regimes))
    summary = pd.DataFrame(
        {
            "regime": regimes,
            "n": [int((df["origin_regime"] == r).sum()) for r in regimes],
            "mean": ar.mean(axis=0),
            "p05": np.percentile(ar, 5, axis=0),
            "p95": np.percentile(ar, 95, axis=0),
            "p_neg": (ar < 0).mean(axis=0),
        }
    ).sort_values("mean")

    print("\n" + "=" * 95)
    print("ALL REGIMES RANKED on WAR outcome (most negative first)")
    print("=" * 95)
    print(f"{'rank':>4}  {'regime':<37}  {'n':>4}  {'mean':>8}  {'90% CI':>22}  {'P(<0)':>6}  flag")
    for i, (_, r) in enumerate(summary.iterrows(), 1):
        prior_flag = "  [prior-highlight]" if r["regime"] in PRIOR_HIGHLIGHT else ""
        outlier_flag = ""
        if r["p_neg"] >= 0.85:
            outlier_flag = "  *NEG-outlier"
        elif r["p_neg"] <= 0.15:
            outlier_flag = "  *POS-outlier"
        print(
            f"{i:>4}  {r['regime']:<37}  {int(r['n']):>4}  {r['mean']:>+8.4f}  "
            f"[{r['p05']:>+7.4f}, {r['p95']:>+7.4f}]  {r['p_neg']:>5.1%}{prior_flag}{outlier_flag}"
        )

    # Decile bins
    print("\n" + "=" * 95)
    print("Top 8 NEGATIVE outliers (regimes whose departed players UNDERPERFORM expectation)")
    print("=" * 95)
    top_neg = summary.head(8)
    for _, r in top_neg.iterrows():
        flag = "[prior]" if r["regime"] in PRIOR_HIGHLIGHT else "[NEW    ]"
        print(
            f"  {flag} {r['regime']:<37}  n={int(r['n']):>3}  "
            f"mean={r['mean']:+.4f}  P(<0)={r['p_neg']:.1%}"
        )

    print("\n" + "=" * 95)
    print("Top 8 POSITIVE outliers (regimes whose departed players OUTPERFORM expectation)")
    print("=" * 95)
    top_pos = summary.tail(8)[::-1]
    for _, r in top_pos.iterrows():
        flag = "[prior]" if r["regime"] in PRIOR_HIGHLIGHT else "[NEW    ]"
        print(
            f"  {flag} {r['regime']:<37}  n={int(r['n']):>3}  "
            f"mean={r['mean']:+.4f}  P(<0)={r['p_neg']:.1%}"
        )


if __name__ == "__main__":
    main()
