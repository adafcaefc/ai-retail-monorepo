"""The three Retail builders against the fixtures the boards ship today.

This is the guard that makes the cutover safe. Both paths run the same
selectors (`frontend/src/agents/retail/*/data/selectors.js`) over the same
rows, so if the payload these builders return matches the checked-in fixture,
switching a board from its fixture to the API cannot change a figure on screen.

Skips without a seeded database rather than failing, so CI without Postgres
stays green — the fixture path is still covered by the frontend suite.

FLOATS ARE COMPARED WITH A TOLERANCE, FOR ONE REASON
----------------------------------------------------
`store_size` is the sum of 20 store size indices. Postgres holds them as
NUMERIC and adds them exactly, giving 20.8445; the fixture builder added IEEE
doubles and got 20.844499999999996. The database is the more accurate of the
two, so the fixture is not corrected to match it — the difference is 4e-15
relative, it reaches only a What-If parameter, and asserting exact equality
would mean writing accumulated float error into the expected value.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "frontend" / "src" / "agents" / "retail"

# (agent folder, builder module, the list blocks and their key)
AGENTS = [
    (
        "demand_forecasting",
        "src.llm.agents.retail.demand_forecasting.dashboard",
        [("items", "sku_id"), ("stores", "store_id"),
         ("reference_by_vertical", "legal_entity_id")],
    ),
    (
        "inventory_risk",
        "src.llm.agents.retail.inventory_risk.dashboard",
        [("items", "sku_id"), ("stores", "store_id")],
    ),
    (
        "replenishment",
        "src.llm.agents.retail.replenishment.dashboard",
        [("lines", "sku_id"), ("stores", "store_id"), ("vendors", "vendor")],
    ),
    (
        "promotion_effectiveness",
        "src.llm.agents.retail.promotion_effectiveness.dashboard",
        [("items", "sku_id"), ("campaigns", "promo_id"), ("stores", "store_id"),
         ("reference_by_vertical", "legal_entity_id")],
    ),
    (
        "assortment_optimization",
        "src.llm.agents.retail.assortment_optimization.dashboard",
        [("items", "sku_id"), ("stores", "store_id"),
         ("by_state_value", "state"),
         ("reference_by_vertical", "legal_entity_id")],
    ),
]

# Metadata that describes the load rather than the data, and one block the
# fixture carries that no selector reads.
# Metadata describing the load rather than the data.
#
# `uom_summary` used to be listed here, and that is precisely why nobody
# noticed the fixture carried it while the API did not return it at all. A
# block that no selector reads does not belong in the fixture; one that is read
# belongs in both. Either way it should not be skipped.
SKIP_BLOCKS = {
    "generated_at",
    "source_workbook",
    "note",
    "what_if_reference",
}


def _builder_or_skip(module_path: str):
    sys.path.insert(0, str(REPO / "backend"))
    try:
        import importlib

        module = importlib.import_module(module_path)
        module.build()
        return module
    except Exception as error:  # noqa: BLE001 - any failure means "not seeded here"
        pytest.skip(f"no seeded retail database: {error}")


def _fixture(folder: str) -> dict:
    path = FIXTURES / folder / "data" / "fixture.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _same(got, want) -> bool:
    """Exact for everything except floats, which get a relative tolerance."""
    if isinstance(want, bool) or isinstance(got, bool):
        return got is want
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return abs(float(got) - float(want)) <= max(abs(float(want)), 1.0) * 1e-9
    if isinstance(want, list) and isinstance(got, list):
        return len(got) == len(want) and all(
            _same(a, b) for a, b in zip(got, want)
        )
    if isinstance(want, dict) and isinstance(got, dict):
        return set(got) == set(want) and all(_same(got[k], want[k]) for k in want)
    return got == want


@pytest.mark.parametrize(("folder", "module_path", "blocks"), AGENTS)
class TestBuildersReproduceTheFixtures:
    def test_every_row_matches_field_for_field(
        self, folder: str, module_path: str, blocks
    ) -> None:
        module = _builder_or_skip(module_path)
        built, fixture = module.build(), _fixture(folder)

        for block, key in blocks:
            if block not in fixture or not fixture[block]:
                continue
            got = {row[key]: row for row in built[block]}
            want = {row[key]: row for row in fixture[block]}

            assert set(got) == set(want), f"{folder}.{block}: different row set"
            for row_key, expected in want.items():
                for column, value in expected.items():
                    assert _same(got[row_key].get(column), value), (
                        f"{folder}.{block}[{row_key}].{column}: "
                        f"{got[row_key].get(column)!r} != {value!r}"
                    )

    def test_row_order_follows_the_workbook(
        self, folder: str, module_path: str, blocks
    ) -> None:
        """Grocery first, then General Merch — not alphabetical.

        The order reaches the screen: it is the order of the dropdown and of
        every table that does not sort itself. Ordering by id would open every
        board on Digital, which is not where these readers start.
        """
        module = _builder_or_skip(module_path)
        built, fixture = module.build(), _fixture(folder)

        for block, key in blocks:
            if block not in fixture or not fixture[block]:
                continue
            assert [row[key] for row in built[block]] == [
                row[key] for row in fixture[block]
            ], f"{folder}.{block} is in a different order"

    def test_the_non_row_blocks_match(
        self, folder: str, module_path: str, blocks
    ) -> None:
        """Filters, formulas, constants, derivation — everything else."""
        module = _builder_or_skip(module_path)
        built, fixture = module.build(), _fixture(folder)

        row_blocks = {block for block, _ in blocks}
        for block, expected in fixture.items():
            if block in SKIP_BLOCKS or block in row_blocks:
                continue
            assert _same(built.get(block), expected), f"{folder}.{block} differs"

    def test_scoping_to_one_vertical_narrows_the_rows(
        self, folder: str, module_path: str, blocks
    ) -> None:
        """The two filters SQL applies really do reach the query.

        Without this the builder could return the whole chain under a scoped
        heading — which is the exact failure the scope object was introduced to
        stop, one layer up.
        """
        from src.llm.agents.common.dashboard_scope import DashboardScope

        module = _builder_or_skip(module_path)
        scoped = module.build(DashboardScope(legal_entity_id="GRC"))

        block, _ = blocks[0]
        assert scoped[block], f"{folder}.{block} came back empty for GRC"
        assert all(row["vertical_id"] == "GRC" for row in scoped[block])
        assert len(scoped[block]) < len(module.build()[block])

        # The dropdowns keep every option: one that only offers what is already
        # selected cannot be used to change the selection.
        assert len(scoped["filter_options"]["legal_entities"]) == 8
