"""Systematic web-probe of candidate data sources we haven't ingested.

Tests HTTP accessibility for ~20 sources we've referenced but never confirmed.
For each: HEAD or small GET, classify as accessible / blocked / 404 / format-issue.
Output as markdown for `docs/DATA_SOURCE_PROBE.md`.

Categories tested:
- Direct CSV / data downloads (Lahman, Chadwick, Retrosheet)
- HTML scrape targets (Wikipedia GM history, BR team pages, MLB Trade Rumors)
- API endpoints (MLB Stats API less-used routes)
- Statcast leaderboards we haven't pulled
- FanGraphs alt endpoints (sometimes CSV works when HTML doesn't)
- Salary / contract aggregators (Spotrac, Cot's)
"""

# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/json,text/csv;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class Probe:
    """One source to probe."""

    name: str
    category: str
    url: str
    method: str = "HEAD"  # or "GET" if HEAD is unreliable
    notes: str = ""


PROBES: tuple[Probe, ...] = (
    # === Direct data downloads ===
    Probe(
        "Lahman baseballdatabank (GitHub)",
        "direct-csv",
        "https://github.com/chadwickbureau/baseballdatabank/raw/master/contrib/People.csv",
        "GET",
        "Lahman People.csv via Chadwick Bureau's GitHub. Birth dates, debut, debut team.",
    ),
    Probe(
        "Chadwick Register people.csv",
        "direct-csv",
        "https://github.com/chadwickbureau/register/raw/master/data/people.csv",
        "GET",
        "26K player register: retro_id, mlbam_id, bref_id, fg_id cross-walk.",
    ),
    Probe(
        "Retrosheet game logs index",
        "direct-html",
        "https://www.retrosheet.org/gamelogs/index.html",
        "GET",
        "Per-game logs back to 1871. Big zip files per decade.",
    ),
    Probe(
        "Retrosheet event files index",
        "direct-html",
        "https://www.retrosheet.org/game.htm",
        "GET",
        "Pitch-by-pitch event logs (gigabytes). For Pinheiro-Szymanski mean-variance.",
    ),
    Probe(
        "Sean Lahman site (direct)",
        "direct-csv",
        "https://www.seanlahman.com/baseball-archive/statistics/",
        "GET",
        "Original Lahman host. Sometimes has CSVs not on GitHub.",
    ),
    # === Wikipedia ===
    Probe(
        "Wikipedia — General manager (MLB)",
        "wiki",
        "https://en.wikipedia.org/wiki/General_manager_(baseball)",
        "GET",
        "Long-tenured GM articles often linked from here.",
    ),
    Probe(
        "Wikipedia — list of MLB GMs (Houston Astros example)",
        "wiki",
        "https://en.wikipedia.org/wiki/Houston_Astros",
        "GET",
        "Per-team articles list all GMs with tenure dates. Cleaner regime boundaries.",
    ),
    # === MLB Trade Rumors / sources ===
    Probe(
        "MLB Trade Rumors home",
        "html-scrape",
        "https://www.mlbtraderumors.com/",
        "GET",
        "Annual international-signing-tracker posts archived here.",
    ),
    Probe(
        "MLB Trade Rumors international tracker (2024)",
        "html-scrape",
        "https://www.mlbtraderumors.com/2024/01/2024-international-signings-tracker.html",
        "GET",
        "Annual list of every MLB international signing with bonuses.",
    ),
    Probe(
        "MLB.com transactions",
        "html-scrape",
        "https://www.mlb.com/transactions",
        "GET",
        "Daily transaction feed. Different shape than the Stats API.",
    ),
    # === Salary / contract data ===
    Probe(
        "Spotrac MLB",
        "html-scrape",
        "https://www.spotrac.com/mlb/",
        "GET",
        "Free salary/contract data; team-level pages public.",
    ),
    Probe(
        "Cot's Contracts (BaseballProspectus)",
        "html-scrape",
        "https://legacy.baseballprospectus.com/cots/",
        "GET",
        "Industry-standard contract reference. Google-sheets-backed.",
    ),
    Probe(
        "Cot's Google Sheets direct",
        "google-sheets",
        "https://docs.google.com/spreadsheets/d/1Fz9_Z3lXEX5lUKsmiQ7zHWX8YjLB6xmcM-LeOgN1FOg",
        "HEAD",
        "Public-shared Google Sheet — direct CSV export possible.",
    ),
    # === FanGraphs alt endpoints ===
    Probe(
        "FanGraphs leaders (HTML — known blocked)",
        "fangraphs",
        "https://www.fangraphs.com/leaders.aspx",
        "GET",
        "Cloudflare-gated per D-25. Confirming still blocked.",
    ),
    Probe(
        "FanGraphs CSV export (alt endpoint)",
        "fangraphs",
        "https://www.fangraphs.com/api/leaders/major-league/data?pos=all&stats=bat&lg=all&qual=y&season=2023&season1=2023",
        "GET",
        "API-style endpoint sometimes works when HTML doesn't.",
    ),
    Probe(
        "FanGraphs prospect grades 2024",
        "fangraphs",
        "https://www.fangraphs.com/prospects/the-board/2024-prospect-list/scouting-grades",
        "GET",
        "FV grades — the original D-15 gap.",
    ),
    # === Statcast additional ===
    Probe(
        "Baseball Savant sprint speed leaderboard",
        "statcast",
        "https://baseballsavant.mlb.com/sprint_speed_leaderboard",
        "GET",
        "Sprint speed (already in our batter percentile_ranks but separate page exists).",
    ),
    Probe(
        "Baseball Savant catcher framing leaderboard",
        "statcast",
        "https://baseballsavant.mlb.com/catcher_framing",
        "GET",
        "Catcher framing — pybaseball CSV-parse failed; retry with direct fetch.",
    ),
    Probe(
        "Baseball Savant pitcher leaderboard (custom CSV)",
        "statcast",
        "https://baseballsavant.mlb.com/leaderboard/custom?year=2023&type=pitcher&filter=&min=q",
        "GET",
        "Custom CSV export for pitcher leaderboards.",
    ),
    # === MiLB / minor league ===
    Probe(
        "MiLB.com prospects landing page",
        "milb",
        "https://www.mlb.com/milb/prospects",
        "GET",
        "Top-100 list lazy-loaded JS (R-26 finding). Retest.",
    ),
    Probe(
        "Baseball Cube",
        "html-scrape",
        "https://www.thebaseballcube.com/",
        "GET",
        "Minor league stats. Public-access player pages.",
    ),
    # === Baseball Reference ===
    Probe(
        "Baseball Reference team transactions (LAD example)",
        "br-scrape",
        "https://www.baseball-reference.com/teams/LAD/2023.shtml",
        "GET",
        "Per-team-season page with transactions section. We scrape front-office from BR.",
    ),
    # === MLB Stats API less-used endpoints ===
    Probe(
        "MLB Stats API — awards",
        "mlb-api",
        "https://statsapi.mlb.com/api/v1/awards",
        "GET",
        "Awards list. Possible feature for prospect-pedigree work.",
    ),
    Probe(
        "MLB Stats API — schedule + game data",
        "mlb-api",
        "https://statsapi.mlb.com/api/v1/schedule?sportId=1&season=2023",
        "GET",
        "Per-game schedule. Alternative path to game logs.",
    ),
)


def probe_one(client: httpx.Client, p: Probe) -> dict[str, Any]:
    """Hit one URL, return status info."""
    try:
        if p.method == "HEAD":
            r = client.head(p.url, follow_redirects=True, timeout=15.0)
        else:
            # Truncate GET response — only need to know it works
            r = client.get(p.url, follow_redirects=True, timeout=15.0)
        return {
            "name": p.name,
            "category": p.category,
            "url": p.url,
            "status": r.status_code,
            "content_type": r.headers.get("content-type", "—")[:50],
            "content_length": (
                r.headers.get("content-length")
                or (str(len(r.content)) if hasattr(r, "content") else "—")
            ),
            "final_url": str(r.url)[:80] if str(r.url) != p.url else "",
            "ok": 200 <= r.status_code < 300,
            "blocked": r.status_code in (403, 406, 429, 503),
            "notes": p.notes,
        }
    except httpx.TimeoutException:
        return {
            "name": p.name,
            "category": p.category,
            "url": p.url,
            "status": "TIMEOUT",
            "content_type": "—",
            "content_length": "—",
            "final_url": "",
            "ok": False,
            "blocked": False,
            "notes": p.notes,
        }
    except Exception as e:
        return {
            "name": p.name,
            "category": p.category,
            "url": p.url,
            "status": f"ERR: {type(e).__name__}",
            "content_type": "—",
            "content_length": "—",
            "final_url": "",
            "ok": False,
            "blocked": False,
            "notes": p.notes,
        }


def classify(result: dict[str, Any]) -> str:
    """Plain-English status."""
    if result["ok"]:
        return "✅ accessible"
    if result["blocked"]:
        return "⛔ blocked"
    if result["status"] in (404,):
        return "❌ 404"
    if isinstance(result["status"], str) and result["status"].startswith("ERR"):
        return f"⚠️  {result['status']}"
    if result["status"] == "TIMEOUT":
        return "⏱  timeout"
    return f"❓ {result['status']}"


def main() -> None:
    """Run the full probe sweep."""
    print(f"Probing {len(PROBES)} data sources...\n")
    results: list[dict[str, Any]] = []
    with httpx.Client(headers=BROWSER_HEADERS) as client:
        for p in PROBES:
            r = probe_one(client, p)
            results.append(r)
            status_emoji = classify(r)
            print(f"  {status_emoji:<25} {p.category:<14} {p.name[:50]}")

    # Group and summarize
    print("\n" + "=" * 88)
    print("SUMMARY BY STATUS")
    print("=" * 88)
    accessible = [r for r in results if r["ok"]]
    blocked = [r for r in results if r["blocked"]]
    not_found = [r for r in results if r["status"] == 404]
    errors = [r for r in results if isinstance(r["status"], str) and r["status"].startswith("ERR")]
    print(f"  ✅ accessible: {len(accessible)}")
    print(f"  ⛔ blocked:    {len(blocked)}")
    print(f"  ❌ 404:        {len(not_found)}")
    print(f"  ⚠️  errors:     {len(errors)}")

    # Print accessible ones with content-type detail
    print("\n" + "=" * 88)
    print("ACCESSIBLE — ready to investigate further")
    print("=" * 88)
    for r in accessible:
        print(
            f"  {r['name'][:45]:<45}  {r['content_type'][:30]:<30}  "
            f"{r['content_length'][:10]:>10} bytes"
        )
        print(f"    URL: {r['url']}")
        if r["notes"]:
            print(f"    Note: {r['notes']}")
        print()

    if blocked:
        print("=" * 88)
        print("BLOCKED — known-bad or rate-limited")
        print("=" * 88)
        for r in blocked:
            print(f"  ⛔ {r['name']} → {r['status']}")
            print(f"     {r['url']}")
            print(f"     Note: {r['notes']}")
            print()


if __name__ == "__main__":
    main()
