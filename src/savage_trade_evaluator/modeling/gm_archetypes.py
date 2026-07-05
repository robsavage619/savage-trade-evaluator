"""GM archetype clustering — behavioral fingerprints → named archetypes.

Reads ``gm_behavioral_profiles``, scales the feature matrix, runs KMeans,
and assigns interpretable archetype labels based on cluster centroids.

Archetypes are intentionally descriptive, not evaluative. A "Deadline Buyer"
is not better or worse than an "Asset Recycler" — they're different styles
that interact differently with player type and context.

Stable label assignment: clusters are re-labeled after each fit by matching
centroid coordinates against the interpretation table, so labels survive
re-clustering as long as the feature space doesn't shift dramatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from savage_trade_evaluator.storage import db, schemas

logger = logging.getLogger(__name__)

# Feature columns used for clustering (must exist in gm_behavioral_profiles)
CLUSTER_FEATURES = [
    "war_buyer_bias",  # positive = buy WAR, negative = sell WAR
    "avg_age_received",  # higher = buy experience
    "deadline_pct",  # higher = deadline-concentration style
    "pct_pitchers_received",  # higher = pitching focus
    "trades_per_season",  # higher = high-activity GM
]

N_CLUSTERS = 5
RANDOM_STATE = 42


@dataclass
class ArchetypeLabel:
    """Named archetype with description."""

    name: str
    description: str


# Archetype interpretations keyed by dominant centroid signature.
# Matching logic: find the cluster whose centroid has the highest value on the
# "signature feature" for each archetype, then assign.
# Signature features must be distinct across archetypes.
ARCHETYPE_SIGNATURES: dict[str, tuple[str, str]] = {
    # (signature_feature, direction): the cluster that maximizes/minimizes this feature
    "Veteran Buyer": ("avg_age_received", "max"),  # buys experience + WAR
    "Youth Builder": ("avg_age_received", "min"),  # sells WAR for youth
    "Asset Recycler": ("trades_per_season", "max"),  # high volume
    "Pitching Factory": ("pct_pitchers_received", "max"),
    "Deadline Dealer": ("deadline_pct", "max"),  # concentrates at deadline
}

ARCHETYPE_DESCRIPTIONS: dict[str, str] = {
    "Veteran Buyer": "Acquires older, higher-WAR players; win-now orientation.",
    "Youth Builder": "Trades proven talent for youth and cost-control; rebuilder profile.",
    "Asset Recycler": "High volume, mixed direction; treats roster as fluid.",
    "Pitching Factory": "Disproportionately acquires pitching; arm-acquisition focus.",
    "Deadline Dealer": "Concentrates activity at the trade deadline; buyer or seller.",
}


def _assign_labels(centroids: np.ndarray, feature_names: list[str]) -> list[str]:
    """Map cluster indices to archetype names.

    Uses a greedy assignment: for each archetype in ``ARCHETYPE_SIGNATURES``
    order, assign the remaining unassigned cluster that best matches its
    signature feature. Ties broken by centroid magnitude.

    Args:
        centroids: (n_clusters, n_features) scaled centroid array.
        feature_names: Column names matching centroid axis 1.

    Returns:
        List of archetype names, length n_clusters, index = cluster id.
    """
    n = centroids.shape[0]
    assigned: dict[int, str] = {}
    used_clusters: set[int] = set()

    for archetype, (feat, direction) in ARCHETYPE_SIGNATURES.items():
        if feat not in feature_names:
            continue
        col = feature_names.index(feat)
        vals = centroids[:, col].copy()
        # mask already-assigned
        for idx in used_clusters:
            vals[idx] = float("nan")
        best = int(np.nanargmax(vals)) if direction == "max" else int(np.nanargmin(vals))
        if not np.isnan(vals[best]):
            assigned[best] = archetype
            used_clusters.add(best)

    # fill any unassigned clusters with a generic label
    labels = []
    generic_idx = 0
    for i in range(n):
        if i in assigned:
            labels.append(assigned[i])
        else:
            labels.append(f"Mixed Style {generic_idx + 1}")
            generic_idx += 1
    return labels


def cluster_gms(profiles: pd.DataFrame | None = None) -> pd.DataFrame:
    """Cluster GMs into archetypes from their behavioral profiles.

    Args:
        profiles: Output of ``gm_profiles.build_gm_profiles()``. Loaded
            from DB if None.

    Returns:
        DataFrame with all profile columns plus ``archetype``,
        ``archetype_description``, and one ``cluster_*`` column per feature
        showing distance to centroid.
    """
    if profiles is None:
        with db.connect(read_only=True) as conn:
            profiles = conn.execute("SELECT * FROM gm_behavioral_profiles").fetchdf()

    df = profiles.copy()

    feat_cols = [c for c in CLUSTER_FEATURES if c in df.columns]
    x_raw = df[feat_cols].fillna(df[feat_cols].median())

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_raw)

    n_clust = min(N_CLUSTERS, len(df))
    km = KMeans(n_clusters=n_clust, n_init=20, random_state=RANDOM_STATE)
    km.fit(x_scaled)

    labels = _assign_labels(km.cluster_centers_, feat_cols)
    df["archetype"] = [labels[c] for c in km.labels_]
    df["archetype_description"] = df["archetype"].map(ARCHETYPE_DESCRIPTIONS).fillna("")
    df["cluster_id"] = km.labels_

    logger.info(
        "clustered %d GMs into %d archetypes: %s",
        len(df),
        n_clust,
        {v: (df["archetype"] == v).sum() for v in set(labels)},
    )
    return df


def persist_archetypes(df: pd.DataFrame) -> None:
    """Write archetype assignments to ``gm_archetypes`` table.

    Args:
        df: Result of ``cluster_gms()``.
    """
    out = df[
        [
            "regime_id",
            "decision_maker",
            "bref_code",
            "regime_start",
            "regime_end",
            "archetype",
            "archetype_description",
            "cluster_id",
        ]
    ].copy()
    with db.connect() as conn:
        schemas.initialize(conn)
        conn.execute("DELETE FROM gm_archetypes")
        conn.register("_gm_arc", out)
        try:
            conn.execute(
                """
                INSERT INTO gm_archetypes
                    (regime_id, decision_maker, bref_code, regime_start, regime_end,
                     archetype, archetype_description, cluster_id)
                SELECT regime_id, decision_maker, bref_code, regime_start, regime_end,
                       archetype, archetype_description, cluster_id
                FROM _gm_arc
                """
            )
        finally:
            conn.unregister("_gm_arc")
    logger.info("persisted %d GM archetype assignments", len(out))


def lookup_archetype(gm_name: str, team_bref: str, season: int) -> str | None:
    """Return the archetype for a GM at a given team and season.

    Args:
        gm_name: GM name as stored in ``gm_archetypes.decision_maker``.
        team_bref: Baseball Reference team code.
        season: Trade season.

    Returns:
        Archetype label, or ``None`` if not found.
    """
    with db.connect(read_only=True) as conn:
        try:
            row = conn.execute(
                """
                SELECT archetype FROM gm_archetypes
                WHERE decision_maker = ?
                  AND bref_code = ?
                  AND regime_start <= ?
                  AND regime_end >= ?
                LIMIT 1
                """,
                [gm_name, team_bref, season, season],
            ).fetchone()
        except Exception:
            return None
    return row[0] if row else None
