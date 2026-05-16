"""Multilevel Bayesian context-aware model (Phase 2.5).

Per the planning brief (D-12) and the V0 OLS finding (-4.83% MAE — predict-zero
is hard to beat with naive linear features), the right inductive bias is
**partial pooling**: a varying-intercepts model that learns per-team deviations
from zero only where the data warrants, with strong shrinkage everywhere else.

Model spec
----------

    surplus_{i,t} ~ Normal(mu_{i,t}, sigma)

    mu_{i,t} = alpha + alpha_team[team_i] + beta @ features_{i,t}

    alpha_team[k] ~ Normal(0, tau_team)   # partial pooling per team
    tau_team    ~ HalfNormal(1.0)
    alpha       ~ Normal(0, 1)
    beta        ~ Normal(0, 0.1)          # tight prior on linear coefficients
    sigma       ~ HalfNormal(2.0)

Features are the same three as the OLS V0 model — receiver_prior_year_war,
receiver_dev_fit_pitching, receiver_dev_fit_hitting — standardized to (0, 1)
mean/sd on the training set.

Scoring on the test set:

* **MAE** of posterior-mean predictions vs realized — directly comparable to
  the OLS baseline.
* **CRPS** (Continuous Ranked Probability Score) computed empirically from
  posterior samples per D-13. CRPS rewards calibrated distributions, not
  just accurate point estimates.

CRPS for a posterior of samples `s_1..s_n` against observed `y`:

    CRPS(y, samples) = mean_i |s_i - y|  -  0.5 * mean_{i,j} |s_i - s_j|

Posteriors mostly-centered-on-zero with the right uncertainty will have lower
CRPS than the same-mean point estimates from OLS, even if MAE is similar.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportMissingImports=false

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.modeling.context_aware import FEATURE_COLUMNS
from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BayesianFitResult:
    """Output of fitting the multilevel Bayesian model."""

    train_mae: float
    test_mae: float
    test_crps: float
    test_crps_naive_zero: float
    naive_zero_test_mae: float
    n_train: int
    n_test: int
    n_teams: int
    posterior_sigma_mean: float
    posterior_tau_team_mean: float


def _load_dataset() -> pd.DataFrame:
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT trade_event_id, trade_season, receiver_bref, surplus,
                   {", ".join(FEATURE_COLUMNS)}
            FROM trade_with_context
            WHERE surplus IS NOT NULL
              AND {" AND ".join(f"{c} IS NOT NULL" for c in FEATURE_COLUMNS)}
            """
        ).df()
    return df


def _crps_empirical(observed: np.ndarray, samples: np.ndarray) -> float:
    """Empirical CRPS averaged over observations.

    Args:
        observed: 1D array of realized values, shape (n,).
        samples: 2D array of posterior predictive samples, shape (n_obs, n_samples).

    Returns:
        Mean CRPS across the n observations.
    """
    n_obs, _ = samples.shape
    out = np.empty(n_obs)
    for i in range(n_obs):
        s = samples[i]
        term1 = float(np.mean(np.abs(s - observed[i])))
        # the pairwise term — exploit symmetry; mean over all pairs (i,j)
        diffs = np.abs(s[:, None] - s[None, :])
        term2 = 0.5 * float(diffs.mean())
        out[i] = term1 - term2
    return float(out.mean())


def fit_multilevel(
    test_start_season: int = 2021,
    n_samples: int = 1000,
    n_tune: int = 1000,
    n_chains: int = 2,
    seed: int = 137,
) -> BayesianFitResult:
    """Fit the multilevel varying-intercepts model and score on a held-out test set.

    Args:
        test_start_season: First test-set season (D-10 default = 2021).
        n_samples: Posterior samples per chain.
        n_tune: Tuning steps per chain (discarded).
        n_chains: Number of independent MCMC chains.
        seed: RNG seed for reproducibility.

    Returns:
        ``BayesianFitResult`` with MAE + CRPS + posterior hyperparameters.
    """
    df = _load_dataset()
    train = df[df.trade_season < test_start_season].reset_index(drop=True)
    test = df[df.trade_season >= test_start_season].reset_index(drop=True)
    if train.empty or test.empty:
        raise RuntimeError("not enough data — run `ste backtest naive` and `ste features` first")

    teams: list[str] = sorted(set(train["receiver_bref"]) | set(test["receiver_bref"]))
    team_to_idx = {t: i for i, t in enumerate(teams)}

    feature_means = train[list(FEATURE_COLUMNS)].mean()
    feature_stds = train[list(FEATURE_COLUMNS)].std().replace(0, 1.0)

    def standardize(d: pd.DataFrame) -> np.ndarray:
        return ((d[list(FEATURE_COLUMNS)] - feature_means) / feature_stds).to_numpy(dtype=float)

    x_train = standardize(train)
    y_train = train["surplus"].to_numpy(dtype=float)
    team_idx_train = np.array([team_to_idx[t] for t in train["receiver_bref"]])

    x_test = standardize(test)
    y_test = test["surplus"].to_numpy(dtype=float)
    team_idx_test = np.array([team_to_idx[t] for t in test["receiver_bref"]])

    n_teams = len(teams)

    logger.info(
        "fitting multilevel Bayesian model: %d train, %d test, %d teams",
        len(train),
        len(test),
        n_teams,
    )

    coords = {"team": teams, "feature": list(FEATURE_COLUMNS)}
    with pm.Model(coords=coords):
        alpha = pm.Normal("alpha", mu=0.0, sigma=1.0)
        tau_team = pm.HalfNormal("tau_team", sigma=1.0)
        sigma = pm.HalfNormal("sigma", sigma=2.0)
        alpha_team = pm.Normal("alpha_team", mu=0.0, sigma=tau_team, dims="team")
        beta = pm.Normal("beta", mu=0.0, sigma=0.1, dims="feature")

        mu = alpha + alpha_team[team_idx_train] + pm.math.dot(x_train, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_train)

        trace = pm.sample(
            draws=n_samples,
            tune=n_tune,
            chains=n_chains,
            random_seed=seed,
            progressbar=False,
        )

    # Manual posterior-predictive: flatten chain x draw -> sample axis
    post = trace.posterior
    n_chains_act, n_draws_act = post["alpha"].shape
    n_total = n_chains_act * n_draws_act

    alpha_samples = post["alpha"].values.reshape(n_total)
    sigma_samples = post["sigma"].values.reshape(n_total)
    alpha_team_samples = post["alpha_team"].values.reshape(n_total, n_teams)
    beta_samples = post["beta"].values.reshape(n_total, len(FEATURE_COLUMNS))

    def predict_samples(x: np.ndarray, team_idx: np.ndarray) -> np.ndarray:
        """Return (n_obs, n_samples) of posterior-predictive draws."""
        # mu[s, i] = alpha[s] + alpha_team[s, team_idx[i]] + x[i] @ beta[s]
        team_intercepts = alpha_team_samples[:, team_idx]  # (n_samples, n_obs)
        feature_effects = beta_samples @ x.T  # (n_samples, n_obs)
        mu = alpha_samples[:, None] + team_intercepts + feature_effects  # (n_samples, n_obs)
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, sigma_samples[:, None], size=mu.shape)
        return (mu + noise).T  # (n_obs, n_samples)

    train_samples = predict_samples(x_train, team_idx_train)
    test_samples = predict_samples(x_test, team_idx_test)

    train_mean_pred = train_samples.mean(axis=1)
    test_mean_pred = test_samples.mean(axis=1)

    train_mae = float(np.mean(np.abs(train_mean_pred - y_train)))
    test_mae = float(np.mean(np.abs(test_mean_pred - y_test)))
    naive_zero_test_mae = float(np.mean(np.abs(y_test)))

    test_crps = _crps_empirical(y_test, test_samples)
    # CRPS of "predict zero with zero uncertainty" = mean |y - 0| = MAE
    test_crps_naive_zero = naive_zero_test_mae

    return BayesianFitResult(
        train_mae=train_mae,
        test_mae=test_mae,
        test_crps=test_crps,
        test_crps_naive_zero=test_crps_naive_zero,
        naive_zero_test_mae=naive_zero_test_mae,
        n_train=len(train),
        n_test=len(test),
        n_teams=n_teams,
        posterior_sigma_mean=float(post["sigma"].mean()),
        posterior_tau_team_mean=float(post["tau_team"].mean()),
    )
