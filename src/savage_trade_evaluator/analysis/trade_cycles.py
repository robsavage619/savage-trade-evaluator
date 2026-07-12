"""Trade-cycle solver: find positive-sum 2- and 3-team trade loops.

The value of a player is a tensor — it differs per acquiring club. That makes
something possible that no scalar model can do: a 3-team deal where every club
gains by its own context valuation. This module searches for those loops.

Math:
  value(p, C)  = prior_war(p) + war_delta_mean(p, C)
  keep(p)      = value(p, sender(p))  — the diagonal of the matrix
  uplift(p, C) = value(p, C) - keep(p)

A cycle is valid iff every club's gain >= min_gain. Ranked by total_gain.

Usage:
  # 1 — build the matrix once (≈11 min serial for 100 players x 29 clubs)
  df = build_value_matrix(season=2025, min_war=2.0, pool_size=100)
  path = save_matrix(df, season=2025)

  # 2 — search for cycles from the cached matrix
  df = load_matrix(2025)
  cycles = find_cycles(df, max_len=3, min_gain=0.25)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from savage_trade_evaluator.config import DATA_DIR
from savage_trade_evaluator.modeling.feature_assembler import assemble_hypothetical
from savage_trade_evaluator.modeling.scenario_engine import score_hypothetical
from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

MATRIX_DIR = DATA_DIR / "trade_value_matrix"


@dataclass(frozen=True)
class Cycle:
    """A positive-sum multi-team trade loop.

    ``clubs[i]`` sends ``players[i]`` to ``clubs[(i+1) % len(clubs)]``.
    ``gains[club]`` is the expected WAR delta for that club in the deal.
    """

    clubs: tuple[str, ...]
    players: tuple[tuple[int, str], ...]  # (mlb_id, name) per sending leg
    gains: dict[str, float] = field(hash=False)
    total_gain: float


def build_value_matrix(
    season: int,
    min_war: float = 2.0,
    pool_size: int = 100,
) -> pd.DataFrame:
    """Score every candidate player against all clubs with org context.

    Also scores each player against their own club (the keep-value diagonal).
    Logs progress every 10 players; warns about skipped pairs — never silent.

    Args:
        season: Trade season (features pulled from season-1 bWAR).
        min_war: Minimum prior-season WAR to include in the candidate pool.
        pool_size: Max candidates; sorted by WAR desc so top players are covered.

    Returns:
        DataFrame with columns: mlb_id, player_name, sender_bref, receiver_bref,
        prior_war, war_delta_mean, war_delta_p5, war_delta_p95, p_positive,
        dollar_surplus_mean, surplus_wins_mean, coverage_grade.
    """
    lookup_season = season - 1

    with db.connect(read_only=True) as conn:
        receivers = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT bref_code FROM team_season_features WHERE season = ? ORDER BY 1",
                [season],
            ).fetchall()
        ]

        candidates_raw = conn.execute(
            """
            SELECT
                COALESCE(b.mlb_id, p.mlb_id)                    AS mlb_id,
                COALESCE(mp.full_name, b.name_common, p.name_common) AS full_name,
                COALESCE(b.team_id, p.team_id)                   AS team_id,
                COALESCE(b.war, 0.0) + COALESCE(p.war, 0.0)     AS total_war
            FROM (
                SELECT mlb_id, name_common, team_id, SUM(war) AS war
                FROM bwar_batting
                WHERE year_id = ? AND mlb_id IS NOT NULL
                GROUP BY mlb_id, name_common, team_id
            ) b
            FULL OUTER JOIN (
                SELECT mlb_id, name_common, team_id, SUM(war) AS war
                FROM bwar_pitching
                WHERE year_id = ? AND mlb_id IS NOT NULL
                GROUP BY mlb_id, name_common, team_id
            ) p ON p.mlb_id = b.mlb_id
            LEFT JOIN mlb_people mp ON mp.mlb_player_id = COALESCE(b.mlb_id, p.mlb_id)
            WHERE COALESCE(b.war, 0.0) + COALESCE(p.war, 0.0) >= ?
              AND COALESCE(b.team_id, p.team_id) IS NOT NULL
            ORDER BY total_war DESC
            LIMIT ?
            """,
            [lookup_season, lookup_season, min_war, pool_size],
        ).fetchdf()

    rows: list[dict[str, Any]] = []
    n_candidates = len(candidates_raw)
    n_skipped = 0

    mlb_id_col: list[Any] = candidates_raw["mlb_id"].tolist()
    team_id_col: list[Any] = candidates_raw["team_id"].tolist()
    full_name_col: list[Any] = candidates_raw["full_name"].tolist()
    total_war_col: list[Any] = candidates_raw["total_war"].tolist()

    for i, (mlb_id_raw, team_id_raw, full_name_raw, total_war_raw) in enumerate(
        zip(mlb_id_col, team_id_col, full_name_col, total_war_col, strict=True)
    ):
        pid = int(mlb_id_raw)
        sender = str(team_id_raw or "")
        name = str(full_name_raw or f"#{pid}")
        prior_war = float(total_war_raw or 0.0)

        if (i + 1) % 10 == 0:
            logger.info("matrix build: %d/%d candidates processed", i + 1, n_candidates)

        # Score against all known receivers + keep-value diagonal (sender == receiver).
        score_clubs: list[str] = list(receivers)
        if sender not in score_clubs:
            score_clubs.append(sender)

        for receiver in score_clubs:
            try:
                feats = assemble_hypothetical(receiver, sender, [pid], season)
                scored = score_hypothetical(
                    feats,
                    receiver_bref=receiver,
                    sender_bref=sender,
                    trade_season=season,
                )
                wd = scored.get("war_delta", {})
                ds = scored.get("dollar_surplus", {})
                sw = scored.get("surplus_wins", {})
                rows.append(
                    {
                        "mlb_id": pid,
                        "player_name": name,
                        "sender_bref": sender,
                        "receiver_bref": receiver,
                        "prior_war": prior_war,
                        "war_delta_mean": wd.get("mean", float("nan")),
                        "war_delta_p5": wd.get("p5", float("nan")),
                        "war_delta_p95": wd.get("p95", float("nan")),
                        "p_positive": wd.get("p_positive", float("nan")),
                        "dollar_surplus_mean": ds.get("mean", float("nan")),
                        "surplus_wins_mean": sw.get("mean", float("nan")),
                        "coverage_grade": scored.get("data_coverage", {}).get("grade", "?"),
                    }
                )
            except Exception as exc:
                logger.warning("skipped player %d (%s) @ %s: %s", pid, name, receiver, exc)
                n_skipped += 1

    if n_skipped:
        logger.warning(
            "SKIPPED: %d player-club pairs failed (out of %d attempted)",
            n_skipped,
            n_candidates * len(score_clubs),
        )

    logger.info(
        "matrix complete: %d rows for %d candidates x %d clubs",
        len(rows),
        n_candidates,
        len(score_clubs),
    )
    return pd.DataFrame(rows)


def save_matrix(df: pd.DataFrame, season: int) -> Path:
    """Write the value matrix to data/trade_value_matrix/matrix_{season}.parquet."""
    MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    path = MATRIX_DIR / f"matrix_{season}.parquet"
    df.to_parquet(path, index=False)
    logger.info("saved value matrix: %s (%d rows)", path, len(df))
    return path


def load_matrix(season: int) -> pd.DataFrame:
    """Load a previously saved value matrix.

    Raises FileNotFoundError with a clear action message if not built yet.
    """
    path = MATRIX_DIR / f"matrix_{season}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"No value matrix for season {season}. "
            f"Build it first: ste build-value-matrix --season {season}"
        )
    return pd.read_parquet(path)


def find_cycles(
    matrix: pd.DataFrame,
    max_len: int = 3,
    min_gain: float = 0.25,
    top_k_per_edge: int = 3,
) -> list[Cycle]:
    """Search the value matrix for positive-sum trade cycles.

    Args:
        matrix: Output of ``build_value_matrix`` or ``load_matrix``.
        max_len: Maximum clubs in a cycle (2 or 3).
        min_gain: Minimum WAR gain required for *each* club to accept.
        top_k_per_edge: Players to consider per (sender, receiver) pair.

    Returns:
        List of valid cycles, sorted by total_gain descending. Deduplicated:
        each unique set of clubs appears at most once (best rotation kept).
    """
    if matrix.empty:
        return []

    # Keep-value: row where receiver == sender (diagonal).
    diagonal = matrix[matrix["receiver_bref"] == matrix["sender_bref"]].copy()
    diagonal["keep_value"] = diagonal["prior_war"] + diagonal["war_delta_mean"]
    keep: dict[int, float] = diagonal.set_index("mlb_id")["keep_value"].to_dict()

    # Uplift edges: (sender, receiver) → top-k players by uplift, uplift > 0 only.
    non_diag = matrix[matrix["receiver_bref"] != matrix["sender_bref"]].copy()
    non_diag = non_diag[pd.notna(non_diag["war_delta_mean"])]  # type: ignore[index]
    non_diag["value"] = non_diag["prior_war"] + non_diag["war_delta_mean"]  # type: ignore[index]
    non_diag["keep"] = non_diag["mlb_id"].apply(  # type: ignore[union-attr]
        lambda pid: keep.get(int(pid), 0.0)
    )
    non_diag["uplift"] = non_diag["value"] - non_diag["keep"]  # type: ignore[index]
    non_diag = non_diag[non_diag["uplift"] > 0]  # type: ignore[index]

    edges: dict[tuple[str, str], list[tuple[int, str, float]]] = {}
    for key, group in non_diag.groupby(["sender_bref", "receiver_bref"]):  # type: ignore[union-attr]
        top = group.nlargest(top_k_per_edge, "uplift")  # type: ignore[arg-type,union-attr]
        key_s = str(key[0]), str(key[1])  # type: ignore[index]
        edges[key_s] = [
            (int(mid), str(name), float(upl))
            for mid, name, upl in zip(
                top["mlb_id"].tolist(),
                top["player_name"].tolist(),
                top["uplift"].tolist(),
                strict=False,
            )
        ]

    clubs = sorted(set(matrix["sender_bref"].unique()) | set(matrix["receiver_bref"].unique()))
    all_cycles: list[Cycle] = []

    # 2-cycles: A→B and B→A both have positive uplift.
    if max_len >= 2:
        for i, ca in enumerate(clubs):
            for cb in clubs[i + 1 :]:
                ab = edges.get((ca, cb), [])
                ba = edges.get((cb, ca), [])
                if not ab or not ba:
                    continue
                pid_ab, name_ab, uplift_b = ab[0]  # B acquires from A
                pid_ba, name_ba, uplift_a = ba[0]  # A acquires from B
                gains = {ca: uplift_a, cb: uplift_b}
                if all(g >= min_gain for g in gains.values()):
                    all_cycles.append(
                        Cycle(
                            clubs=(ca, cb),
                            players=((pid_ba, name_ba), (pid_ab, name_ab)),
                            gains=gains,
                            total_gain=sum(gains.values()),
                        )
                    )

    # 3-cycles: A sends P_AB to B, B sends P_BC to C, C sends P_CA to A.
    if max_len >= 3:
        for ca in clubs:
            for cb in clubs:
                if cb == ca:
                    continue
                ab = edges.get((ca, cb), [])
                if not ab:
                    continue
                for cc in clubs:
                    if cc in (ca, cb):
                        continue
                    bc = edges.get((cb, cc), [])
                    ca_in = edges.get((cc, ca), [])
                    if not bc or not ca_in:
                        continue
                    pid_ab, name_ab, uplift_b = ab[0]
                    pid_bc, name_bc, uplift_c = bc[0]
                    pid_ca, name_ca, uplift_a = ca_in[0]
                    gains = {ca: uplift_a, cb: uplift_b, cc: uplift_c}
                    if all(g >= min_gain for g in gains.values()):
                        all_cycles.append(
                            Cycle(
                                clubs=(ca, cb, cc),
                                players=((pid_ab, name_ab), (pid_bc, name_bc), (pid_ca, name_ca)),
                                gains=gains,
                                total_gain=sum(gains.values()),
                            )
                        )

    # Sort by total_gain descending, then deduplicate by club-set (keep best rotation).
    all_cycles.sort(key=lambda c: c.total_gain, reverse=True)
    seen: set[frozenset[str]] = set()
    deduped: list[Cycle] = []
    for c in all_cycles:
        key = frozenset(c.clubs)
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    logger.info(
        "found %d valid cycles (min_gain=%.2f, max_len=%d)", len(deduped), min_gain, max_len
    )
    return deduped
