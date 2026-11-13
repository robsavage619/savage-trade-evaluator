"""The daily refresh: ingest, gate, export, build the site, publish.

Order matters. Ingests run first and their failures are collected, not fatal. Then
the quality gates read what the database actually holds. Only if no fail-gate failed
do the exports run and the site get rebuilt; the new build replaces the old one with
two renames, so a failed run leaves the last good site serving. Every outcome writes a
status file, and the site shows it, so a refresh that did nothing cannot look healthy.

Modes:
  (default)      full run
  --gates-only   read-only: run the gates against the database now, change nothing
  --build-only   rebuild and swap the site (used by the deploy script)
"""

# pyright: reportOptionalSubscript=false, reportGeneralTypeIssues=false

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from savage_trade_evaluator import quality
from savage_trade_evaluator.config import DATA_DIR, PROJECT_ROOT
from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

STATE_DIR = DATA_DIR / "refresh"
STATUS_PATH = STATE_DIR / "status.json"
LAST_GOOD_PATH = STATE_DIR / "last_good.json"
FRONTEND = PROJECT_ROOT / "frontend"
ZERO_ROWS = re.compile(r"\bingested 0\b")


@dataclass(frozen=True)
class Step:
    """One command, and how much its failure matters.

    Attributes:
        name: Label shown in the status.
        argv: The command, run from the project root.
        severity: ``fail`` blocks publishing, ``warn`` only degrades.
        timeout: Seconds before the command is killed.
    """

    name: str
    argv: tuple[str, ...]
    severity: str = "fail"
    timeout: int = 3600


def _ste(*args: str) -> tuple[str, ...]:
    return (str(Path(sys.executable).parent / "ste"), *args)


def _script(name: str) -> tuple[str, ...]:
    return (sys.executable, str(PROJECT_ROOT / "scripts" / name))


def ingest_steps(season: int) -> list[Step]:
    """Everything after bWAR, which has already run and fixed ``season``."""
    s = str(season)
    return [
        Step("transactions", _ste("ingest", "transactions", "--season", s)),
        Step("rosters", _ste("ingest", "rosters", "--start", s, "--end", s)),
        Step("statcast", _ste("ingest", "statcast", "--season", s)),
        Step("statcast-extended", _ste("ingest", "statcast-extended", "--year", s)),
        Step("statcast-sprint-speed", _ste("ingest", "statcast-sprint-speed", "--year", s)),
        Step("statcast-exit-velo", _ste("ingest", "statcast-exit-velo", "--year", s)),
        Step("pitch-movement", _ste("ingest", "pitch-movement", "--start", s, "--end", s)),
        Step("team-season-stats", _ste("ingest", "team-season-stats", "--start", s, "--end", s)),
        Step("standings", _ste("ingest", "standings", "--season", s)),
        Step("catcher-framing", _ste("ingest", "catcher-framing", "--year", s), "warn"),
        Step("bref-contracts", _ste("ingest", "bref-contracts"), "warn"),
        Step(
            "mlb-free-agents",
            _ste("ingest", "mlb-free-agents", "--start", str(season - 1), "--end", s),
            "warn",
        ),
        Step("fangraphs-projections", _ste("ingest", "fangraphs-projections"), "warn"),
        Step("spotrac", _ste("ingest", "spotrac", "--year", s), "warn"),
        Step("spotrac-terms", _ste("ingest", "spotrac-terms", "--year", s), "warn"),
    ]


BWAR = Step("bwar", _ste("ingest", "bwar"))
EXPORT_STEPS = (
    Step("export:rosters", _script("refresh_rosters.py")),
    Step("export:projection", _script("enrich_player_projection.py")),
    Step("export:structural", _script("export_structural.py")),
    Step("export:contract-flags", _script("export_contract_flags.py")),
    Step("export:contract-dollars", _script("export_contract_dollars.py")),
    Step("export:warroom", _script("export_warroom.py"), "warn"),
)


def run_step(step: Step) -> quality.Gate:
    """Run one command and report it as a gate.

    A command that exits 0 but says it ingested 0 rows counts as failed: several
    ingests log per-item failures and still exit cleanly.
    """
    started = time.monotonic()
    try:
        proc = subprocess.run(
            step.argv,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=step.timeout,
            check=False,
        )
        output = (proc.stdout + proc.stderr).strip()
        ok = proc.returncode == 0 and not ZERO_ROWS.search(output)
        last = output.splitlines()[-1] if output else ""
        detail = f"{time.monotonic() - started:.0f}s; " + (
            last[:160] if ok else f"exit {proc.returncode}: {last[:160]}"
        )
    except subprocess.TimeoutExpired:
        ok, detail = False, f"timed out after {step.timeout}s"
    logger.info("%s %s: %s", "ok  " if ok else "FAIL", step.name, detail)
    return quality.Gate(f"step:{step.name}", step.severity, ok, detail)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    os.replace(tmp, path)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def latest_season() -> int:
    """The newest season bWAR holds; in the offseason that is the season just played."""
    with db.connect(read_only=True) as conn:
        return int(conn.execute("SELECT MAX(year_id) FROM bwar_batting").fetchone()[0])


def build_site() -> None:
    """Build into ``dist.next``, carry over runtime briefs, and swap it in with two renames.

    Raises:
        subprocess.CalledProcessError: If the build fails; ``dist`` is left as it was.
    """
    dist, nxt, prev = FRONTEND / "dist", FRONTEND / "dist.next", FRONTEND / "dist.prev"
    shutil.rmtree(nxt, ignore_errors=True)
    subprocess.run(
        ["npm", "run", "build", "--", "--outDir", "dist.next", "--emptyOutDir"],
        cwd=FRONTEND, check=True, capture_output=True, text=True,
    )  # fmt: skip
    if (dist / "brief-inbox").exists():
        shutil.copytree(dist / "brief-inbox", nxt / "brief-inbox", dirs_exist_ok=True)
    shutil.rmtree(prev, ignore_errors=True)
    if dist.exists():
        dist.rename(prev)
    nxt.rename(dist)


def publish_status(status: dict[str, Any]) -> None:
    """Write the full status, and the compact copy the site reads if a build exists."""
    _write_json(STATUS_PATH, status)
    if (FRONTEND / "dist").exists():
        site = {k: status[k] for k in ("status", "finished", "data_as_of", "published", "problems")}
        _write_json(FRONTEND / "dist" / "status.json", site)


def _problems(gates: list[quality.Gate]) -> list[str]:
    return [f"{g.name}: {g.detail}" for g in gates if not g.ok]


def main(argv: list[str] | None = None) -> int:
    """Run the refresh. Returns the process exit code: 0 ok or degraded, 1 failed."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--gates-only", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--since", help="ISO time the 'fresh' gates measure from (default: now)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    started = datetime.now()
    previous = _load(LAST_GOOD_PATH)
    data_as_of = previous["finished"] if previous else None
    gates: list[quality.Gate] = []

    if args.build_only:
        build_site()
        # A rebuild proves nothing about the data: keep the last refresh's verdict.
        publish_status(_load(STATUS_PATH) or {
            "started": started.isoformat(), "finished": started.isoformat(), "status": "degraded",
            "data_as_of": data_as_of, "published": True, "gates": [],
            "problems": ["no refresh has completed on this machine yet"],
        })  # fmt: skip
        return 0

    since = datetime.fromisoformat(args.since) if args.since else started
    if not args.gates_only:
        gates.append(run_step(BWAR))
    season = latest_season()
    if not args.gates_only:
        gates += [run_step(step) for step in ingest_steps(season)]

    with db.connect(read_only=True) as conn:
        found, metrics = quality.run_gates(
            conn,
            season=season,
            since=since,
            today=since.date(),
            baseline=previous["metrics"] if previous else None,
        )
    gates += found
    state = quality.overall(gates)

    if args.gates_only:
        for g in gates:
            print(f"{'PASS' if g.ok else g.severity.upper():<5} {g.name:<40} {g.detail}")
        print(f"\noverall: {state}")
        return 1 if state == "failed" else 0

    published = False
    if state != "failed":
        exports = [run_step(step) for step in EXPORT_STEPS]
        gates += exports
        state = quality.overall(gates)
        if state != "failed":
            try:
                build_site()
                published = True
            except subprocess.CalledProcessError as exc:
                gates.append(quality.Gate("step:build", "fail", False, (exc.stderr or "")[-200:]))
                state = "failed"

    finished = datetime.now()
    if published:
        _write_json(
            LAST_GOOD_PATH, {"finished": finished.isoformat(), "status": state, "metrics": metrics}
        )
        data_as_of = finished.isoformat()
    publish_status({
        "started": started.isoformat(), "finished": finished.isoformat(), "status": state,
        "data_as_of": data_as_of, "published": published, "season": season,
        "problems": _problems(gates),
        "gates": [asdict(g) for g in gates],
    })  # fmt: skip
    logger.info("refresh %s (published=%s); %d problem(s)", state, published, len(_problems(gates)))
    return 1 if state == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
