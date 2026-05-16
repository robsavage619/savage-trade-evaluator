"""Tests for the Baseball Reference front-office parser.

We test the parser against representative HTML fragments (no network) to
guard against regressions when BR changes its template.
"""

from __future__ import annotations

from savage_trade_evaluator.ingest.front_office import parse_front_office

# Realistic fragment with the multi-role-per-<p> edge case (Manager + President
# in the same <p>, separated by &nbsp;) plus Manager's W-L parens.
HTML_LAD_2018 = """
<p>
    <strong>Manager:</strong>
    <a href="/managers/x.shtml">Dave Roberts</a>
    (92-71)
    &nbsp;&nbsp;
    <strong>President:</strong>
    Andrew Friedman
    (President of Baseball Operations)
</p>
<p>
    <strong>General Manager:</strong>
    Farhan Zaidi
</p>
<p>
    <strong>Farm Director:</strong>
    <a href="/x.shtml">Brandon Gomes</a>
</p>
<p>
    <strong>Scouting Director:</strong>
    <a href="/y.shtml">Billy Gasparino</a>
</p>
"""


def test_parses_lad_2018_canonical() -> None:
    pairs = parse_front_office(HTML_LAD_2018)
    assert ("Manager", "Dave Roberts") in pairs
    assert ("President", "Andrew Friedman") in pairs
    assert ("General Manager", "Farhan Zaidi") in pairs
    assert ("Farm Director", "Brandon Gomes") in pairs
    assert ("Scouting Director", "Billy Gasparino") in pairs


def test_strips_wl_record_from_manager() -> None:
    """Manager names come with W-L records in parens; we must strip them."""
    pairs = parse_front_office(HTML_LAD_2018)
    managers = [name for role, name in pairs if role == "Manager"]
    assert managers == ["Dave Roberts"]
    assert all("(" not in name for _, name in pairs)


def test_ignores_unknown_roles() -> None:
    html = """
    <p><strong>Ballpark:</strong> Dodger Stadium</p>
    <p><strong>Attendance:</strong> 3,857,500</p>
    <p><strong>General Manager:</strong> Farhan Zaidi</p>
    """
    pairs = parse_front_office(html)
    assert pairs == [("General Manager", "Farhan Zaidi")]


def test_handles_multiple_people_per_role() -> None:
    """Mid-season GM swap: BR sometimes lists both."""
    html = """
    <p><strong>General Manager:</strong> A.J. Preller, Dayton Moore</p>
    """
    pairs = parse_front_office(html)
    assert ("General Manager", "A.J. Preller") in pairs
    assert ("General Manager", "Dayton Moore") in pairs


def test_handles_president_canonical_case() -> None:
    """LAD 2018-style: President (=POBO) is the executive above the GM."""
    pairs = parse_front_office(HTML_LAD_2018)
    titles = {role for role, _ in pairs}
    assert "President" in titles
    assert "General Manager" in titles
