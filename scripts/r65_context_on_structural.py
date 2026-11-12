"""R-65: does club context add anything on top of the structural model?

Pre-registered before any spec was scored. Target: captured_war. Base: the
structural two-part model (``modeling/structural.py``). Context is limited to the
five team-level columns with at least 96% coverage, because the acquired-player
context features are almost entirely mean-imputed (FanGraphs FV 1%, Statcast 6%):

  contention  receiver_contention_window_score  (pyth% x (1 - payroll % of cap))
  quality     receiver_prior_year_pyth_pct
  payroll     receiver_payroll_pct_of_cap
  dev_hit     receiver_dev_fit_hitting
  dev_pit     receiver_dev_fit_pitching

Context is z-scored with each fold's training statistics. The mechanisms are
multiplicative: a club's context changes how much of a player's talent it
captures (playing time) or keeps after control ends (retention).

Specs:
  S0  structural baseline
  S1  S0 + the five context columns, additive
  S2  S0 + the five context columns x held WAR (playing time)
  S3  S0 + the five context columns x post-control held WAR (retention)
  S4  S0 + contention x held WAR            (the thesis headline)
  S5  S0 + payroll x post-control held WAR  (the retention headline)

Decision rule: a spec earns a single look at the 2018-2021 holdout only if its
paired per-side CRPS gain over S0 on the pre-2018 folds has a 99% interval above
zero (five comparisons, so alpha = 0.01) and it improves in at least 3 of the 4
folds. Otherwise the answer is that context adds nothing detectable, and the
holdout is not touched.

Run:
  uv run python scripts/r65_context_on_structural.py
"""

# pyright: reportCallIssue=false, reportArgumentType=false, reportReturnType=false

from __future__ import annotations

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling import structural
from savage_trade_evaluator.modeling.metrics import crps_empirical
from savage_trade_evaluator.modeling.v3 import assemble_v3_combined

TARGET = structural.TARGET
KEYS = structural.KEYS
BASE = list(structural.FEATURES)
CONTEXT = {
    "contention": "receiver_contention_window_score",
    "quality": "receiver_prior_year_pyth_pct",
    "payroll": "receiver_payroll_pct_of_cap",
    "dev_hit": "receiver_dev_fit_hitting",
    "dev_pit": "receiver_dev_fit_pitching",
}
HOLDOUT = (2018, 2021)
CV_TEST_SEASONS = (2014, 2015, 2016, 2017)
N_DRAWS = 400
Z_99 = 2.576


def design(train: pd.DataFrame, test: pd.DataFrame, spec: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Feature matrices for one spec; context is z-scored on ``train`` only."""
    out = []
    for frame in (train, test):
        x = frame[BASE].astype("float64").copy()
        held = frame["held_ctrl_war"] + frame["held_post_war"]
        for name, col in CONTEXT.items():
            z = (frame[col].astype("float64") - train[col].mean()) / train[col].std()
            z = z.fillna(0.0)
            if spec == "S1":
                x[name] = z
            elif spec == "S2":
                x[f"{name}_x_held"] = z * held
            elif spec == "S3":
                x[f"{name}_x_post"] = z * frame["held_post_war"]
            elif spec == "S4" and name == "contention":
                x["contention_x_held"] = z * held
            elif spec == "S5" and name == "payroll":
                x["payroll_x_post"] = z * frame["held_post_war"]
        out.append(x)
    return out[0], out[1]


def side_crps(y: np.ndarray, draws: np.ndarray) -> np.ndarray:
    """Per-side CRPS, so specs can be compared as paired differences."""
    return np.array([crps_empirical(y[i : i + 1], draws[i : i + 1]) for i in range(len(y))])


def run(train: pd.DataFrame, test: pd.DataFrame, spec: str) -> tuple[np.ndarray, np.ndarray]:
    """Fit one spec on ``train``; return per-side CRPS and 90% coverage flags on ``test``."""
    x_train, x_test = design(train, test, spec)
    y_train = train[TARGET].to_numpy(dtype="float64")
    model = structural.fit(x_train, y_train)
    draws, _ = structural.predict(model, x_test, np.random.default_rng(137), N_DRAWS)
    y = test[TARGET].to_numpy(dtype="float64")
    lo, hi = np.percentile(draws, [5, 95], axis=1)
    return side_crps(y, draws), ((y >= lo) & (y <= hi)).astype(float)


def main() -> None:
    df = assemble_v3_combined().dropna(subset=[TARGET])
    df = df[df["trade_season"] <= HOLDOUT[1]].merge(
        structural.side_features(structural.TRAIN_START_SEASON, HOLDOUT[1]), on=KEYS, how="left"
    )
    # DuckDB row order is not stable; the inner CV splits depend on it.
    df = df.sort_values(KEYS).reset_index(drop=True)
    dev = df[df["trade_season"] < HOLDOUT[0]]
    folds = [(dev[dev["trade_season"] < s], dev[dev["trade_season"] == s]) for s in CV_TEST_SEASONS]
    specs = ["S0", "S1", "S2", "S3", "S4", "S5"]

    crps: dict[str, list[np.ndarray]] = {}
    cover: dict[str, list[np.ndarray]] = {}
    for spec in specs:
        parts = [run(train, test, spec) for train, test in folds]
        crps[spec] = [c for c, _ in parts]
        cover[spec] = [v for _, v in parts]

    base = crps["S0"]
    rows = []
    for spec in specs:
        pooled = np.concatenate(crps[spec])
        gain = np.concatenate(base) - pooled  # positive = better than S0
        half = Z_99 * gain.std(ddof=1) / np.sqrt(len(gain)) if spec != "S0" else 0.0
        fold_gain = [float((b - c).mean()) for b, c in zip(base, crps[spec], strict=True)]
        rows.append(
            {
                "spec": spec,
                "CRPS": pooled.mean(),
                "gain vs S0": gain.mean(),
                "99% half-width": half,
                "folds better": sum(g > 0 for g in fold_gain) if spec != "S0" else None,
                "Cov90": np.concatenate(cover[spec]).mean(),
                "earns holdout": bool(
                    spec != "S0" and gain.mean() - half > 0 and sum(g > 0 for g in fold_gain) >= 3
                ),
            }
        )
    table = pd.DataFrame(rows).set_index("spec")
    n = sum(len(t) for _, t in folds)
    print(f"WALK-FORWARD, test seasons {CV_TEST_SEASONS}, n={n} sides, paired per-side CRPS")
    print(table.round(4).to_string())

    winners = [r["spec"] for r in rows if r["earns holdout"]]
    if not winners:
        print("\nNo spec earned a holdout look: club context adds nothing detectable.")
        return
    best = max(winners, key=lambda s: table.loc[s, "gain vs S0"])
    holdout = df[df["trade_season"] >= HOLDOUT[0]]
    out = {s: run(dev, holdout, s) for s in ("S0", best)}
    print(f"\nHOLDOUT {HOLDOUT[0]}-{HOLDOUT[1]}, n={len(holdout)} sides, {best} chosen on folds")
    for s, (c, v) in out.items():
        print(f"  {s}  CRPS {c.mean():.4f}  Cov90 {v.mean():.3f}")
    gain = out["S0"][0] - out[best][0]
    print(
        f"  paired gain {gain.mean():+.4f}  95% half-width {1.96 * gain.std(ddof=1) / np.sqrt(len(gain)):.4f}"
    )


if __name__ == "__main__":
    main()
