"""One-time parse script: convert Firecrawl-scraped FanGraphs Board JSON → CSVs.

Run once to populate data/prospect_fv_cache/fangraphs_{year}.csv for 2017-2024.

Column layout by era:
  2021+:     rank | org_rank | name | org | pos | level | eta | fv | risk | trend | ...
  2017-2020: rank | org_rank | name | org | pos | level | trend | fv | eta | risk | ...
FV is always at split-index 7 (0-indexed after stripping pipe boundaries).
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

TOOL_RESULTS = Path(
    "/Users/robsavage/.claude/projects"
    "/-Users-robsavage-Projects-savage-trade-evaluator"
    "/8a2a7a63-10c2-48dd-8d99-304ee5da19e0/tool-results"
)

SCRAPED_FILES: dict[int, str] = {
    2024: "mcp-firecrawl-firecrawl_scrape-1779751492026.txt",
    2023: "mcp-firecrawl-firecrawl_scrape-1779751495172.txt",
    2022: "mcp-firecrawl-firecrawl_scrape-1779751497986.txt",
    2021: "mcp-firecrawl-firecrawl_scrape-1779751500496.txt",
    2020: "mcp-firecrawl-firecrawl_scrape-1779751503434.txt",
    2019: "mcp-firecrawl-firecrawl_scrape-1779751506039.txt",
    2018: "mcp-firecrawl-firecrawl_scrape-1779751508638.txt",
    2017: "mcp-firecrawl-firecrawl_scrape-1779751511316.txt",
}

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "prospect_fv_cache"

FIELDNAMES = [
    "rank_year",
    "rank",
    "player_name",
    "player_name_norm",
    "fangraphs_player_id",
    "org",
    "position",
    "level",
    "fv",
    "risk",
    "eta",
]

NAME_URL_RE = re.compile(
    r"\[([^\]]+)\]\(https://www\.fangraphs\.com/players/[^/]+/([^/]+)/stats/[^\)]+\)"
)


def normalize_name(name: str) -> str:
    """Lowercase, strip diacritics and punctuation, keep a-z0-9 and spaces."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", ascii_only.lower()).strip()


def parse_year(year: int, markdown: str) -> list[dict]:
    rows: list[dict] = []
    new_fmt = year >= 2021  # eta at col 6; old format has trend at col 6

    seen_fg_ids: set[str] = set()
    first_fg_id: str | None = None

    for line in markdown.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Skip separator rows (| --- | --- | ...)
        if "---" in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        # Split produces empty strings at [0] and [-1] — remove them
        parts = parts[1:-1]

        if len(parts) < 9:
            continue
        if not parts[0].isdigit():
            continue

        rank = int(parts[0])
        name_cell = parts[2]

        m = NAME_URL_RE.search(name_cell)
        if not m:
            continue

        player_name = m.group(1).strip()
        fg_id = m.group(2).strip()

        # The page renders the table twice (responsive layout).
        # Stop when the first player's FG ID reappears.
        if first_fg_id is None:
            first_fg_id = fg_id
        elif fg_id == first_fg_id:
            break

        # A player can legitimately appear twice (different org), keep first.
        if fg_id in seen_fg_ids:
            continue
        seen_fg_ids.add(fg_id)

        fv_raw = parts[7]
        try:
            fv = int(fv_raw)
        except ValueError:
            continue

        if new_fmt:
            eta_raw = parts[6]
            risk = parts[8] if len(parts) > 8 else ""
        else:
            eta_raw = parts[8] if len(parts) > 8 else ""
            risk = parts[9] if len(parts) > 9 else ""

        try:
            eta = int(eta_raw) if eta_raw else None
        except ValueError:
            eta = None

        rows.append(
            {
                "rank_year": year,
                "rank": rank,
                "player_name": player_name,
                "player_name_norm": normalize_name(player_name),
                "fangraphs_player_id": fg_id,
                "org": parts[3],
                "position": parts[4],
                "level": parts[5],
                "fv": fv,
                "risk": risk or None,
                "eta": eta,
            }
        )

    return rows


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for year, fname in sorted(SCRAPED_FILES.items()):
        fpath = TOOL_RESULTS / fname
        if not fpath.exists():
            print(f"MISSING: {fpath}")
            continue

        with open(fpath) as f:
            data = json.load(f)

        rows = parse_year(year, data["markdown"])

        out_path = OUTPUT_DIR / f"fangraphs_{year}.csv"
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

        fv_range = f"FV {min(r['fv'] for r in rows)}-{max(r['fv'] for r in rows)}" if rows else "empty"
        print(f"{year}: {len(rows):3d} rows  {fv_range}  → {out_path.name}")


if __name__ == "__main__":
    main()
