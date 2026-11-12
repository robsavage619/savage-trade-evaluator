from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "export_contract_dollars",
    Path(__file__).resolve().parents[1] / "scripts" / "export_contract_dollars.py",
)
assert _SPEC and _SPEC.loader
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def test_each_cell_kind_yields_the_right_dollar_or_none() -> None:
    assert mod.pick_dollar("guaranteed", 81_900_000, None) == ("g", 81_900_000)
    # an option year is priced at the option value (exercise assumed), not the buyout
    assert mod.pick_dollar("option", 200_000, 2_500_000) == ("o", 2_500_000)
    assert mod.pick_dollar("arb", 2_500_000, None) == ("a", 2_500_000)


def test_pre_arb_years_are_marked_not_priced_by_the_export() -> None:
    assert mod.pick_dollar("pre_arb", None, None) == ("p", 0)


def test_name_bridge_ignores_accents_and_punctuation() -> None:
    assert mod.normalize("A.J. Ewing") == "aj ewing"
    assert mod.normalize("Andrés Giménez") == "andres gimenez"
    assert mod.normalize("Lourdes Gurriel Jr.") == "lourdes gurriel jr"


def test_cells_without_a_stated_figure_fall_back() -> None:
    assert mod.pick_dollar("fa", None, None) is None
    assert mod.pick_dollar("arb", None, None) is None  # 3 arb cells carry no estimate
    assert mod.pick_dollar("option", 0, None) is None
    assert mod.pick_dollar("other", 5_000_000, None) is None
