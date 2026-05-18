"""R-29/R-30: Sell-high vs system-tax decomposition.

Extracted from scripts/sell_high_vs_system_tax.py for use in reports and CLI.

Key finding: TEX-Jon Daniels' negative regime is entirely driven by
veterans-at-peak (Lucroy, Minor, Darvish, Michael Young). Young prospects
are *positive* in every regime tested — no system-tax signal anywhere.
"""

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db

REGIMES_TO_CHECK: tuple[str, ...] = (
    # 8 most-negative regimes (R-28)
    "TEX_Jon Daniels",
    "SFG_Farhan Zaidi",
    "MIL_David Stearns",
    "LAA_Billy Eppler",
    "ATL_Alex Anthopoulos",
    "PHI_Ruben Amaro Jr",
    "TBR_Matt Silverman",
    "LAD_Andrew Friedman",
    # 4 most-positive regimes (R-28)
    "OAK_Billy Beane",
    "ARI_Tony La Russa",
    "PIT_Ben Cherington",
    "WSN_Mike Rizzo",
    # Cross-check regimes
    "HOU_Jeff Luhnow",
    "CLE_Chris Antonetti",
    "TOR_Alex Anthopoulos",
    "STL_John Mozeliak",
)


def load_all_trades() -> pd.DataFrame:
    """Load 2010+ trade legs joined to regime + MLB-experience proxy."""
    with db.connect(read_only=True) as conn:
        return conn.execute(
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
                   tpu.from_team_bref AS from_team,
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


def classify_player(pre: float, experience: float | None) -> str:
    """Classify one trade leg into a mechanism bucket."""
    if experience is None or pd.isna(experience):
        return "MIDDLE"
    if pre >= 2.0 and experience >= 6:
        return "VET-AT-PEAK"
    if pre <= 1.0 and experience <= 4:
        return "YOUNG-PROSPECT"
    return "MIDDLE"


def sell_high_decomposition(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """All trade legs with bucket + mechanism classification.

    Returns the full trade DataFrame with added columns:
    bucket (VET-AT-PEAK | YOUNG-PROSPECT | MIDDLE) and mechanism label.
    """
    if df is None:
        df = load_all_trades()
    out = df.copy()
    out["bucket"] = out.apply(
        lambda r: classify_player(r["pre"], r.get("experience")), axis=1
    )
    return out


def regime_decomposition(df: pd.DataFrame, regime_id: str) -> dict[str, dict[str, float]]:
    """Per-bucket mean Δ WAR + counts for one regime."""
    sub = df[df["regime"] == regime_id].copy()
    if sub.empty:
        return {}
    sub["bucket"] = sub.apply(lambda r: classify_player(r["pre"], r.get("experience")), axis=1)
    out: dict[str, dict[str, float]] = {}
    for b in ("VET-AT-PEAK", "YOUNG-PROSPECT", "MIDDLE"):
        rows = sub[sub["bucket"] == b]
        out[b] = (
            {"n": 0, "mean_delta": float("nan"), "mean_pre": float("nan")}
            if rows.empty
            else {
                "n": len(rows),
                "mean_delta": float(rows["delta"].mean()),
                "mean_pre": float(rows["pre"].mean()),
            }
        )
    out["ALL"] = {
        "n": len(sub),
        "mean_delta": float(sub["delta"].mean()),
        "mean_pre": float(sub["pre"].mean()),
    }
    return out


def classify_mechanism(d: dict[str, dict[str, float]]) -> str:
    """Plain-English mechanism label from a bucket decomposition dict."""
    all_mean = d.get("ALL", {}).get("mean_delta", 0.0)
    vet = d.get("VET-AT-PEAK", {})
    young = d.get("YOUNG-PROSPECT", {})
    if -0.05 < all_mean < 0.05:
        return "neutral"
    sign = "negative" if all_mean < 0 else "positive"
    vet_n, vet_mean = vet.get("n", 0), vet.get("mean_delta", 0.0)
    young_n, young_mean = young.get("n", 0), young.get("mean_delta", 0.0)
    if vet_n < 5 and young_n < 5:
        return f"{sign} (small buckets, inconclusive)"
    if vet_n >= 5 and young_n >= 5:
        if abs(vet_mean) > abs(young_mean) * 1.5:
            return f"{sign} via SELL-HIGH (vets carry signal)"
        if abs(young_mean) > abs(vet_mean) * 1.5:
            return f"{sign} via SYSTEM-TAX (young players carry signal)"
        return f"{sign} via BOTH mechanisms"
    if vet_n >= 5:
        return f"{sign} via SELL-HIGH (vet bucket dominant; young n={young_n})"
    return f"{sign} via SYSTEM-TAX (young bucket dominant; vet n={vet_n})"


def all_regime_summary() -> pd.DataFrame:
    """Summary table: one row per regime in REGIMES_TO_CHECK.

    Columns: regime, n_all, mean_delta_all, vet_n, vet_mean, young_n,
             young_mean, middle_n, middle_mean, mechanism
    """
    df = load_all_trades()
    rows = []
    for regime in REGIMES_TO_CHECK:
        d = regime_decomposition(df, regime)
        if not d:
            continue
        all_ = d["ALL"]
        vet = d.get("VET-AT-PEAK", {})
        young = d.get("YOUNG-PROSPECT", {})
        mid = d.get("MIDDLE", {})
        rows.append({
            "regime": regime,
            "n_all": all_["n"],
            "mean_delta_all": all_["mean_delta"],
            "vet_n": vet.get("n", 0),
            "vet_mean": vet.get("mean_delta", float("nan")),
            "young_n": young.get("n", 0),
            "young_mean": young.get("mean_delta", float("nan")),
            "middle_n": mid.get("n", 0),
            "middle_mean": mid.get("mean_delta", float("nan")),
            "mechanism": classify_mechanism(d),
        })
    return pd.DataFrame(rows).sort_values("mean_delta_all")
