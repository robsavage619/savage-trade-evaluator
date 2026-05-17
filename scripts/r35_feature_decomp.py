"""R-35: separate player-level features from team-aggregate features.

R-34 showed the multilevel structure adds nothing because team-aggregate
features (receiver_org_*_jump_3yr, receiver_dev_fit_*, receiver_prior_year_*)
already encode team context — the team intercept is collinear and steals
variance.

R-35 tests whether multilevel pooling is *genuinely* useless or merely
shadowed by feature engineering. Splits the feature space:

  PLAYER_ONLY = ACQUIRED_PLAYER_FEATURES (8 features, vary within team)
  TEAM_AGG    = RECEIVER_TEAM_FEATURES + ORIGIN_FEATURES (8 features, team-level)

Three models per outcome:
  V0_all      = pop + 16 features                  (R-34 baseline)
  V0_player   = pop + 8 player features
  V1_player   = pop + team intercept + 8 player features

If V1_player > V0_player by a real margin → team pooling pays off when
not collinear with team-aggregate features. If V1_player ≈ V0_player →
team pooling adds nothing even when the architectural setup is clean,
and multilevel should be dropped entirely.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.modeling.v2.backtest import (
    _crps_empirical,
    assemble_combined,
)
from savage_trade_evaluator.modeling.v2.features import (
    ACQUIRED_PLAYER_FEATURES,
    ALL_FEATURES,
)


def _impute_and_split(
    outcome: str, feature_cols: tuple[str, ...],
    train_end: int = 2020, test_end: int = 2024, min_present: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    combined = assemble_combined()
    combined = combined[combined[outcome].notna()].copy()
    present = combined[list(feature_cols)].notna().sum(axis=1)
    complete = combined[present >= min_present].copy()
    for c in feature_cols:
        complete[c] = complete[c].astype("float64")
        complete[c] = complete[c].fillna(complete[c].mean())
    train = complete[complete["trade_season"] <= train_end].reset_index(drop=True)
    test = complete[
        (complete["trade_season"] > train_end) & (complete["trade_season"] <= test_end)
    ].reset_index(drop=True)
    return train, test


def _fit_v0(
    train: pd.DataFrame, outcome: str, feature_cols: tuple[str, ...]
) -> dict:
    """Pop intercept + features only."""
    means = train[list(feature_cols)].mean()
    stds = train[list(feature_cols)].std().replace(0, 1.0)
    x = ((train[list(feature_cols)] - means) / stds).to_numpy(dtype=float)
    y = train[outcome].to_numpy(dtype=float)
    y_mean = float(y.mean())
    y_std = float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    coords = {"feature": list(feature_cols)}
    with pm.Model(coords=coords):
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, dims="feature")
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha0 + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            draws=1500, tune=2000, chains=4, random_seed=137,
            progressbar=False, target_accept=0.99,
        )
    return {
        "trace": trace, "feature_cols": feature_cols, "means": means, "stds": stds,
        "y_mean": y_mean, "y_std": y_std, "kind": "v0",
    }


def _fit_v1_team(
    train: pd.DataFrame, outcome: str, feature_cols: tuple[str, ...]
) -> dict:
    """Pop + team intercept + features."""
    teams = tuple(sorted(train["receiver_bref"].unique()))
    team_to_idx = {t: i for i, t in enumerate(teams)}
    team_idx = np.array([team_to_idx[t] for t in train["receiver_bref"]])

    means = train[list(feature_cols)].mean()
    stds = train[list(feature_cols)].std().replace(0, 1.0)
    x = ((train[list(feature_cols)] - means) / stds).to_numpy(dtype=float)
    y = train[outcome].to_numpy(dtype=float)
    y_mean = float(y.mean())
    y_std = float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    coords = {"team": list(teams), "feature": list(feature_cols)}
    with pm.Model(coords=coords):
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        tau_team = pm.HalfNormal("tau_team", sigma=1.0)
        alpha_team_z = pm.Normal("alpha_team_z", mu=0.0, sigma=1.0, dims="team")
        alpha_team = pm.Deterministic("alpha_team", alpha_team_z * tau_team, dims="team")
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, dims="feature")
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha0 + alpha_team[team_idx] + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            draws=1500, tune=2000, chains=4, random_seed=137,
            progressbar=False, target_accept=0.99,
        )
    return {
        "trace": trace, "teams": teams, "team_to_idx": team_to_idx,
        "feature_cols": feature_cols, "means": means, "stds": stds,
        "y_mean": y_mean, "y_std": y_std, "kind": "v1",
    }


def _predict(fit: dict, df: pd.DataFrame) -> np.ndarray:
    cols = list(fit["feature_cols"])
    x_test = ((df[cols] - fit["means"]) / fit["stds"]).to_numpy(dtype=float)
    post = fit["trace"].posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n_samples)
    sigma_s = post["sigma"].values.reshape(n_samples)
    beta_s = post["beta"].values.reshape(n_samples, len(cols))
    if fit["kind"] == "v1":
        alpha_team_s = post["alpha_team"].values.reshape(n_samples, len(fit["teams"]))
        team_idx = np.array([fit["team_to_idx"].get(t, -1) for t in df["receiver_bref"]])
    out = np.zeros((len(df), n_samples))
    for i in range(len(df)):
        team_a = 0.0
        if fit["kind"] == "v1":
            tidx = team_idx[i]
            team_a = alpha_team_s[:, tidx] if tidx >= 0 else 0.0
        mu = alpha0_s + team_a + beta_s @ x_test[i]
        rng = np.random.default_rng(137 + i)
        noise = rng.normal(0.0, sigma_s)
        out[i] = (mu + noise) * fit["y_std"] + fit["y_mean"]
    return out


def _credible_count(trace, feature_cols: tuple[str, ...]) -> int:
    beta = trace.posterior["beta"].values.reshape(-1, len(feature_cols))
    n = 0
    for i in range(len(feature_cols)):
        v = beta[:, i]
        p05 = float(np.percentile(v, 5))
        p95 = float(np.percentile(v, 95))
        mass = max((v > 0).mean(), (v < 0).mean())
        ci_excludes_zero = (p05 > 0 and p95 > 0) or (p05 < 0 and p95 < 0)
        if ci_excludes_zero and mass >= 0.95:
            n += 1
    return n


def _score(fit: dict, test: pd.DataFrame, outcome: str) -> dict:
    y = test[outcome].to_numpy(dtype=float)
    pred = _predict(fit, test)
    mae = float(np.mean(np.abs(pred.mean(axis=1) - y)))
    crps = _crps_empirical(y, pred)
    p05 = np.percentile(pred, 5, axis=1)
    p95 = np.percentile(pred, 95, axis=1)
    cov = float(((y >= p05) & (y <= p95)).mean())
    cred = _credible_count(fit["trace"], fit["feature_cols"])
    return {"mae": mae, "crps": crps, "cov90": cov, "credible": cred}


def main() -> None:
    """Three-way bracket: V0_all vs V0_player vs V1_player."""
    rows = []
    for o in ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus"):
        print()
        print("#" * 88)
        print(f"# {o.upper()}")
        print("#" * 88)

        # V0_all: 16 features, no team
        train_all, test_all = _impute_and_split(o, ALL_FEATURES, min_present=5)
        if len(train_all) < 50:
            print(f"  SKIPPED: only {len(train_all)} train rows")
            continue
        v0_all = _fit_v0(train_all, o, ALL_FEATURES)
        s_v0_all = _score(v0_all, test_all, o)

        # V0_player: 8 player features, no team
        train_p, test_p = _impute_and_split(o, ACQUIRED_PLAYER_FEATURES, min_present=3)
        v0_p = _fit_v0(train_p, o, ACQUIRED_PLAYER_FEATURES)
        s_v0_p = _score(v0_p, test_p, o)

        # V1_player: 8 player features + team intercept
        v1_p = _fit_v1_team(train_p, o, ACQUIRED_PLAYER_FEATURES)
        s_v1_p = _score(v1_p, test_p, o)

        print(f"  V0_all     (16f, no team):  MAE={s_v0_all['mae']:.4f}  "
              f"CRPS={s_v0_all['crps']:.4f}  cov={s_v0_all['cov90']:.1%}  "
              f"cred={s_v0_all['credible']}")
        print(f"  V0_player  ( 8f, no team):  MAE={s_v0_p['mae']:.4f}  "
              f"CRPS={s_v0_p['crps']:.4f}  cov={s_v0_p['cov90']:.1%}  "
              f"cred={s_v0_p['credible']}")
        print(f"  V1_player  ( 8f + team):    MAE={s_v1_p['mae']:.4f}  "
              f"CRPS={s_v1_p['crps']:.4f}  cov={s_v1_p['cov90']:.1%}  "
              f"cred={s_v1_p['credible']}")

        rows.append({
            "outcome": o,
            "v0_all_mae": s_v0_all["mae"], "v0_p_mae": s_v0_p["mae"], "v1_p_mae": s_v1_p["mae"],
            "v0_all_crps": s_v0_all["crps"], "v0_p_crps": s_v0_p["crps"], "v1_p_crps": s_v1_p["crps"],
            "v0_all_cred": s_v0_all["credible"], "v0_p_cred": s_v0_p["credible"],
            "v1_p_cred": s_v1_p["credible"],
        })

    print()
    print("=" * 88)
    print("R-35 SUMMARY")
    print("=" * 88)
    if rows:
        print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
