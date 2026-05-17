"""R-30: Decompose each regime's negative intercept into sell-high vs system-tax mechanics.

R-29 archaeology showed TEX-Daniels' negative regime is driven by veterans-at-peak
(Lucroy, Minor, Michael Young, Darvish) — that's a sell-high mechanic, NOT the
system-tax thesis Rob originally proposed. This script systematically classifies
each regime's trades into two buckets:

  VET-AT-PEAK     pre_war >= 2.0 AND MLB-experience >= 6
                  (established player, late-career; if they decline post-trade,
                   it's "sold at peak" not "system dependency")

  YOUNG-PROSPECT  pre_war <= 1.0 AND MLB-experience <= 4
                  (not-yet-established player; if they decline post-trade,
                   it's "system was inflating production" or RTM)

  MIDDLE          everything else (career-mid players, mixed signals)

For each regime, report the mean Δ WAR in each bucket. If a regime's negative
intercept is concentrated in VET-AT-PEAK, the mechanism is sell-high. If it's
concentrated in YOUNG-PROSPECT, the mechanism is system-tax (the original
thesis). The two have opposite implications for trade-eval product design.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db

REGIMES_TO_CHECK = (
    # The 8 most-negative regimes from R-28
    "TEX_Jon Daniels",
    "SFG_Farhan Zaidi",
    "MIL_David Stearns",
    "LAA_Billy Eppler",
    "ATL_Alex Anthopoulos",
    "PHI_Ruben Amaro Jr",
    "TBR_Matt Silverman",
    "LAD_Andrew Friedman",
    # The 4 most-positive regimes from R-28
    "OAK_Billy Beane",
    "ARI_Tony La Russa",
    "PIT_Ben Cherington",
    "WSN_Mike Rizzo",
    # Other prior-highlight regimes for cross-check
    "HOU_Jeff Luhnow",
    "CLE_Chris Antonetti",
    "TOR_Alex Anthopoulos",
    "STL_John Mozeliak",
)


def load() -> pd.DataFrame:
    """Load all 2010+ trade legs joined to regime + experience proxy."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            WITH first_season AS (
                SELECT mlb_id, MIN(year_id) AS first_mlb_year
                FROM bwar_player_seasons
                WHERE mlb_id IS NOT NULL
                GROUP BY mlb_id
            )
            SELECT tra.regime_id AS regime,
                   tpu.player_name,
                   tpu.trade_season,
                   tpu.to_team_bref AS to_team,
                   w.war_t_minus_1 AS pre,
                   w.war_t_plus_1 AS post,
                   (w.war_t_plus_1 - w.war_t_minus_1) AS delta,
                   (tpu.trade_season - fs.first_mlb_year) AS experience
            FROM trade_player_war_window w
            JOIN trade_player_unified tpu
                ON tpu.trade_event_id = w.trade_event_id
                AND tpu.leg_index = w.leg_index
            JOIN team_regime_assignments tra
                ON tra.bref_code = tpu.from_team_bref
                AND tra.season = tpu.trade_season
            LEFT JOIN first_season fs ON fs.mlb_id = tpu.mlb_player_id
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND tra.regime_id IS NOT NULL
            """
        ).df()
    return df


def bucket(row: pd.Series) -> str:
    """Classify a trade leg into vet/prospect/middle."""
    pre = row["pre"]
    exp = row["experience"]
    if pd.isna(exp):
        return "MIDDLE"
    if pre >= 2.0 and exp >= 6:
        return "VET-AT-PEAK"
    if pre <= 1.0 and exp <= 4:
        return "YOUNG-PROSPECT"
    return "MIDDLE"


def regime_decomposition(df: pd.DataFrame, regime_id: str) -> dict[str, dict[str, float]]:
    """Per-bucket mean Δ WAR + counts for one regime."""
    sub = df[df["regime"] == regime_id].copy()
    if sub.empty:
        return {}
    sub["bucket"] = sub.apply(bucket, axis=1)
    out: dict[str, dict[str, float]] = {}
    for b in ("VET-AT-PEAK", "YOUNG-PROSPECT", "MIDDLE"):
        rows = sub[sub["bucket"] == b]
        if rows.empty:
            out[b] = {"n": 0, "mean_delta": float("nan"), "mean_pre": float("nan")}
        else:
            out[b] = {
                "n": len(rows),
                "mean_delta": float(rows["delta"].mean()),
                "mean_pre": float(rows["pre"].mean()),
            }
    out["ALL"] = {
        "n": len(sub),
        "mean_delta": float(sub["delta"].mean()),
        "mean_pre": float(sub["pre"].mean()),
    }
    return out


def classify_mechanism(d: dict[str, dict[str, float]]) -> str:
    """Plain-English mechanism label from bucket decomposition."""
    all_mean = d.get("ALL", {}).get("mean_delta", 0.0)
    vet = d.get("VET-AT-PEAK", {})
    young = d.get("YOUNG-PROSPECT", {})
    if all_mean > -0.05 and all_mean < 0.05:
        return "neutral"
    sign = "negative" if all_mean < 0 else "positive"
    # Which bucket carries the signal?
    vet_n, vet_mean = vet.get("n", 0), vet.get("mean_delta", 0.0)
    young_n, young_mean = young.get("n", 0), young.get("mean_delta", 0.0)
    if vet_n < 5 and young_n < 5:
        return f"{sign} (small buckets, inconclusive)"
    if vet_n >= 5 and young_n >= 5:
        if abs(vet_mean) > abs(young_mean) * 1.5:
            return f"{sign} via SELL-HIGH (vets carry signal)"
        if abs(young_mean) > abs(vet_mean) * 1.5:
            return f"{sign} via SYSTEM-TAX (young players carry signal)"
        return f"{sign} via BOTH mechanisms (vet + young aligned)"
    if vet_n >= 5:
        return f"{sign} via SELL-HIGH (only vet bucket has signal; young n={young_n})"
    return f"{sign} via SYSTEM-TAX (only young bucket has signal; vet n={vet_n})"


def main() -> None:
    """Print per-regime mechanism decomposition."""
    df = load()
    print(f"Loaded {len(df)} trade legs with regime + experience coverage")
    print()
    print("VET-AT-PEAK    = pre_war >= 2.0 AND experience >= 6 (sold high?)")
    print("YOUNG-PROSPECT = pre_war <= 1.0 AND experience <= 4 (system-dependent?)")
    print("MIDDLE         = everything else")
    print()

    for regime in REGIMES_TO_CHECK:
        d = regime_decomposition(df, regime)
        if not d:
            print(f"\n{regime}: NOT FOUND")
            continue
        all_ = d["ALL"]
        print(f"\n{regime}  (n={all_['n']}, overall Δ={all_['mean_delta']:+.3f})")
        for b in ("VET-AT-PEAK", "YOUNG-PROSPECT", "MIDDLE"):
            row = d[b]
            if row["n"] > 0:
                print(
                    f"  {b:<16}  n={row['n']:>3}  "
                    f"mean Δ WAR={row['mean_delta']:>+6.3f}  "
                    f"(pre-WAR avg {row['mean_pre']:>+4.2f})"
                )
            else:
                print(f"  {b:<16}  n=  0  --")
        print(f"  → {classify_mechanism(d)}")


if __name__ == "__main__":
    main()
