"""Phase 4: retroactive V3 scoring of historical trades (2018-2021 holdout).

Shows where the model's posterior mean diverged most from realized outcomes,
segmented into: accurate calls, false optimism (model said +WAR, got negative),
and hidden value (model said -WAR, team actually gained).

Run:
  uv run python scripts/case_studies.py [--top-n 15] [--out case_studies.csv]
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.production_fit import get_fit
from savage_trade_evaluator.modeling.v3 import assemble_v3_combined, predict
from savage_trade_evaluator.storage import db

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

HOLDOUT_START = 2018
HOLDOUT_END = 2021
OUTCOME = "war_delta"
N_SAMPLES_SUBSAMPLE = 10  # keep every 10th draw for efficiency (600 of 6000)


def _load_player_names(trade_ids: list[int]) -> dict[int, str]:
    """Return {trade_event_id: 'Name1, Name2'} for the receiving side of each trade."""
    if not trade_ids:
        return {}
    placeholders = ",".join(["?"] * len(trade_ids))
    with db.connect(read_only=True) as conn:
        rows = conn.execute(
            f"""
            SELECT tp.trade_event_id, tp.to_team_bref, tp.from_team_bref,
                   STRING_AGG(mp.full_name, ', ' ORDER BY mp.full_name) AS players
            FROM trade_player_unified tp
            LEFT JOIN mlb_people mp ON mp.mlb_player_id = tp.mlb_player_id
            WHERE tp.trade_event_id IN ({placeholders})
            GROUP BY tp.trade_event_id, tp.to_team_bref, tp.from_team_bref
            """,
            trade_ids,
        ).fetchdf()
    # there may be multiple receiver sides per trade; take first
    deduped = rows.drop_duplicates(subset="trade_event_id", keep="first")
    result: dict[int, dict] = {}
    for _, r in deduped.iterrows():
        result[int(r["trade_event_id"])] = {
            "players": str(r["players"] or "—"),
            "to_team": str(r["to_team_bref"]),
            "from_team": str(r["from_team_bref"]),
        }
    return result


def score_holdout() -> pd.DataFrame:
    """Score the 2018-2021 holdout rows; return DataFrame with predictions + realized."""
    df = assemble_v3_combined()
    held_out = (
        df[(df["trade_season"] >= HOLDOUT_START) & (df["trade_season"] <= HOLDOUT_END)]
        .dropna(subset=[OUTCOME])
        .copy()
    )

    fit = get_fit(OUTCOME)
    feat_cols = list(fit.feature_cols)
    scored = pd.DataFrame(index=held_out.index)
    for c in feat_cols:
        if c in held_out.columns:
            scored[c] = held_out[c].astype("float64")
        else:
            scored[c] = float(fit.feature_means.get(c, 0.0))
        scored[c] = scored[c].fillna(float(fit.feature_means.get(c, 0.0)))

    samples = predict(fit, scored)  # (n, n_samples)
    sub = samples[:, ::N_SAMPLES_SUBSAMPLE]

    held_out = held_out.copy()
    held_out["predicted_mean"] = samples.mean(axis=1)
    held_out["predicted_p5"] = np.percentile(samples, 5, axis=1)
    held_out["predicted_p95"] = np.percentile(samples, 95, axis=1)
    held_out["p_positive"] = (sub > 0).mean(axis=1)
    held_out["abs_error"] = np.abs(held_out[OUTCOME] - held_out["predicted_mean"])
    held_out["error"] = held_out[OUTCOME] - held_out["predicted_mean"]

    # Model was bullish (predicted > 0) but result was negative => false optimism
    held_out["false_optimism"] = (held_out["predicted_mean"] > 0.5) & (held_out[OUTCOME] < 0)
    # Model was bearish (predicted < 0) but result was positive => hidden value
    held_out["hidden_value"] = (held_out["predicted_mean"] < -0.3) & (held_out[OUTCOME] > 1.0)

    return held_out.reset_index(drop=True)


def _print_section(
    title: str,
    df: pd.DataFrame,
    meta: dict[int, dict],
    n: int,
) -> None:
    sep = "─" * 90
    print()
    print(f"  ── {title} ──")
    print(f"  {sep}")
    print(
        f"  {'Season':>6}  {'Receiver':>8}  {'Pred':>6}  {'Actual':>7}  "
        f"{'Error':>6}  {'P(+)':>5}  {'Players':<34}"
    )
    print(f"  {sep}")
    for _, r in df.head(n).iterrows():
        tid = int(r["trade_event_id"])
        m = meta.get(tid, {})
        players = (m.get("players") or "—")[:33]
        print(
            f"  {int(r['trade_season']):>6}  {r['receiver_bref']:>8}  "
            f"{r['predicted_mean']:>+6.2f}  {r[OUTCOME]:>+7.2f}  "
            f"{r['error']:>+6.2f}  {r['p_positive']:>4.0%}  {players:<34}"
        )
    print(f"  {sep}")


def main(top_n: int = 15, out: str | None = None) -> None:
    print("Loading V3 combined dataset and scoring holdout…")
    results = score_holdout()

    trade_ids = results["trade_event_id"].astype(int).tolist()
    print(f"Fetching player names for {len(trade_ids)} trades…")
    meta = _load_player_names(trade_ids)

    realized = results[OUTCOME].values
    pred = results["predicted_mean"].values
    mae = float(np.abs(realized - pred).mean())
    hit_rate = float(np.mean(np.sign(pred) == np.sign(realized)))

    print()
    print("=" * 90)
    print(f"  CASE STUDIES -- V3 Holdout {HOLDOUT_START}-{HOLDOUT_END}  (n={len(results)})")
    print("=" * 90)
    print(f"  MAE: {mae:.3f} WAR    Directional accuracy: {hit_rate:.1%}")

    # 1. Highest-confidence wins (model optimistic and correct)
    true_pos = results[(results["predicted_mean"] > 0.5) & (results[OUTCOME] > 0.5)].sort_values(
        "predicted_mean", ascending=False
    )
    _print_section(
        "HIGH-CONFIDENCE WINS  (model optimistic -> got positive WAR)",
        true_pos,
        meta,
        top_n,
    )

    # 2. False optimism (model predicted well, outcome was bad)
    false_opt = results[results["false_optimism"]].sort_values("abs_error", ascending=False)
    _print_section(
        "FALSE OPTIMISM  (model predicted +WAR, realized negative)",
        false_opt,
        meta,
        top_n,
    )

    # 3. Hidden value (model bearish, outcome strong)
    hidden = results[results["hidden_value"]].sort_values(OUTCOME, ascending=False)
    _print_section(
        "HIDDEN VALUE  (model was bearish, team actually gained >=1 WAR)",
        hidden,
        meta,
        top_n,
    )

    # 4. Largest absolute errors overall
    big_err = results.sort_values("abs_error", ascending=False)
    _print_section("LARGEST ABSOLUTE ERRORS  (all sign directions)", big_err, meta, top_n)

    print()

    if out:
        cols = [
            "trade_event_id",
            "receiver_bref",
            "trade_season",
            OUTCOME,
            "predicted_mean",
            "predicted_p5",
            "predicted_p95",
            "p_positive",
            "abs_error",
            "error",
        ]
        results[cols].to_csv(out, index=False)
        print(f"  Wrote {len(results)} rows → {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V3 case studies (holdout 2018-2021).")
    parser.add_argument("--top-n", type=int, default=15, help="Rows per section.")
    parser.add_argument("--out", type=str, default=None, help="Optional CSV output path.")
    args = parser.parse_args()
    main(top_n=args.top_n, out=args.out)
