from __future__ import annotations

from savage_trade_evaluator.ingest.bref_contracts import (
    ContractYear,
    guaranteed_through,
    parse_contracts_page,
    parse_year_cell,
)

# Cell shapes copied from a real Padres page: option with buyout and tooltip,
# an arbitration estimate whose tooltip contains markup, guaranteed dollars, FA.
TEAM_OPTION = (
    '$200k <span class="tooltip" data-tip="$2.5M Team Option"><small>[FA-*]</small></span>'
)
PLAYER_OPTION = (
    '$5M <span class="tooltip" data-tip="$28M Player Option"><small>[FA-*]</small></span>'
)
MUTUAL_OPTION = (
    '$3M <span class="tooltip" data-tip="$20M Mutual Option"><small>[Arb-3-*]</small></span>'
)
ARB = (
    'Arb-3&nbsp;<span class="small_text">(<span class="tooltip" tip="Estimated Arbitration '
    'Award<br>See Link Below">~$6.5M</span>)</span>'
)

PAGE = """
<table id="payroll"><thead><tr>
<th data-stat="player">Name</th><th data-stat="contract_summary">Contract Status</th>
<th data-stat="contract_y0">2027</th><th data-stat="contract_y1">2028</th>
<th data-stat="contract_y2">2029</th>
</tr></thead><tbody>
<tr><th scope="row" data-append-csv="musgrjo01"
 data-stat="player"><a href="/p">Joe Musgrove</a></th>
<td data-stat="age">34</td><td data-stat="service_time">10.063</td>
<td data-stat="contract_summary" csk="100000000">5 yrs/$100M (23-27)</td>
<td data-stat="contract_y0">$20M</td><td data-stat="contract_y1">FA</td></tr>
<tr><th scope="row" data-append-csv="optionpl01" data-stat="player"><a href="/p">Option Guy</a></th>
<td data-stat="age">32</td><td data-stat="service_time">7.004</td>
<td data-stat="contract_summary">3 yrs/$75M (26-28)</td>
<td data-stat="contract_y0">$12M</td><td data-stat="contract_y1">PLAYER_OPTION</td>
<td data-stat="contract_y2">$30M</td></tr>
<tr><th data-stat="player">Name</th><td data-stat="contract_summary">Contract Status</td></tr>
</tbody></table>
""".replace("PLAYER_OPTION", PLAYER_OPTION)


def test_option_cells_keep_type_value_buyout_and_fallback() -> None:
    team = parse_year_cell(2027, TEAM_OPTION)
    assert team == ContractYear(2027, "option", 200_000, "team", 2_500_000, "FA", "$200k [FA-*]")
    player = parse_year_cell(2027, PLAYER_OPTION)
    assert player and (player.option_type, player.option_value, player.amount) == (
        "player",
        28_000_000,
        5_000_000,
    )
    mutual = parse_year_cell(2027, MUTUAL_OPTION)
    assert mutual and (mutual.option_type, mutual.status_if_declined) == ("mutual", "Arb-3")


def test_other_cell_shapes() -> None:
    assert parse_year_cell(2027, "") is None
    assert parse_year_cell(2027, "FA").kind == "fa"  # type: ignore[union-attr]
    assert parse_year_cell(2027, "$25.71M") == ContractYear(
        2027, "guaranteed", 25_710_000, raw_text="$25.71M"
    )
    arb = parse_year_cell(2027, ARB)
    assert arb and arb.kind == "arb" and "<" not in arb.raw_text and ">" not in arb.raw_text
    odd = parse_year_cell(2027, "Retired")
    assert odd and odd.kind == "other" and odd.raw_text == "Retired"


def test_parse_page_skips_repeated_header_rows_and_reads_summary() -> None:
    players = parse_contracts_page(PAGE)
    assert [p.name for p in players] == ["Joe Musgrove", "Option Guy"]
    musgrove = players[0]
    assert (musgrove.service_time, musgrove.summary_years, musgrove.summary_total) == (
        10.063,
        5,
        100_000_000,
    )
    assert (musgrove.summary_first_season, musgrove.summary_last_season) == (2023, 2027)
    assert [(y.season, y.kind) for y in musgrove.years] == [(2027, "guaranteed"), (2028, "fa")]


def test_guaranteed_through_stops_at_the_first_option() -> None:
    guy = parse_contracts_page(PAGE)[1]
    assert [y.kind for y in guy.years] == ["guaranteed", "option", "guaranteed"]
    assert guaranteed_through(guy.years) == 2027  # the 2029 $30M is behind a player option


def test_template_change_fails_loudly() -> None:
    try:
        parse_contracts_page("<html><body>no table</body></html>")
    except ValueError as exc:
        assert "payroll table" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_spotrac_conflicts_flags_options_absent_and_expired_but_not_matches() -> None:
    from datetime import date

    import duckdb

    from savage_trade_evaluator.ingest.bref_contracts import DDL, spotrac_conflicts

    conn = duckdb.connect()
    for ddl in DDL:
        conn.execute(ddl)
    conn.execute("CREATE TABLE mlb_people (mlb_player_id INTEGER, full_name VARCHAR)")
    conn.execute(
        "CREATE TABLE spotrac_contract_terms (mlb_player_id INTEGER, season INTEGER, "
        "contract_years INTEGER, contract_total BIGINT, aav BIGINT, free_agent_year INTEGER)"
    )
    day = date(2026, 11, 12)
    # id, name, spotrac free-agent year, BR cells (season, kind) or None for absent
    cases = [
        (1, "Option Guy", 2029, [(2027, "guaranteed"), (2028, "option"), (2029, "guaranteed")]),
        (2, "Clean Deal", 2029, [(2027, "guaranteed"), (2028, "guaranteed"), (2029, "fa")]),
        (3, "Left Club", 2029, None),
        (4, "Rental Over", 2027, None),
        (5, "No FA Year", None, [(2027, "guaranteed")]),
    ]
    for pid, name, fa, cells in cases:
        conn.execute("INSERT INTO mlb_people VALUES (?, ?)", [pid, name])
        conn.execute(
            "INSERT INTO spotrac_contract_terms VALUES (?, 2026, 3, 75000000, 25000000, ?)",
            [pid, fa],
        )
        if cells is not None:
            conn.execute(
                "INSERT INTO bref_contract_players "
                "(team_bref, as_of, bref_id, mlb_player_id, player_name, source) "
                "VALUES ('SDP', ?, ?, ?, ?, 't')",
                [day, f"id{pid}", pid, name],
            )
            for season, kind in cells:
                conn.execute(
                    "INSERT INTO bref_contract_years "
                    "(team_bref, as_of, bref_id, season, kind, option_type) "
                    "VALUES ('SDP', ?, ?, ?, ?, ?)",
                    [day, f"id{pid}", season, kind, "player" if kind == "option" else None],
                )
    flagged = spotrac_conflicts(conn).set_index("player")["issue"].to_dict()
    assert flagged == {
        "Option Guy": "option_inside_window",
        "Left Club": "absent_from_bref",
        "Rental Over": "expired",
        "No FA Year": "spotrac_missing_fa_year",
    }
