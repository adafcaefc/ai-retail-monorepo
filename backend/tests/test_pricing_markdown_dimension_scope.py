"""`category_group`/`state` scoping of the `stores` rollup for Agent 5 ·
Pricing & Markdown -- pure functions only.

Regression for the gap where selecting a Category or State filter left
"At-risk value by store/cluster/channel/legal entity" completely unchanged:
`build_stores()` was always handed the full, unscoped `store_money_rows`, so
those four dimension charts kept showing each store's full all-category/
all-state total no matter what the caller filtered on -- unlike `store_id`,
which the sibling test_pricing_markdown_store_scope.py already covers.

No database needed: `build_stores` is a pure function of the rows handed to
it, so this exercises the same category/state pre-filtering `dashboard.py`'s
`build()` now does before calling it, rather than through a live connection.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from src.llm.agents.retail.pricing_markdown import dashboard as d  # noqa: E402

# S1 stocks one C1/Overstock SKU and one C2/Expiry SKU.
# S2 stocks one C1/Overstock SKU and one C2/Healthy SKU.
STORE_MONEY_ROWS = [
    {
        "store_key": "S1", "store_name": "Store 1", "store_vertical_id": "GRC",
        "cluster": "Express", "channel": "Physical",
        "category_id": "C1", "state": "Overstock",
        "at_risk": 100.0, "position_qty": 10.0, "price": 10.0,
    },
    {
        "store_key": "S1", "store_name": "Store 1", "store_vertical_id": "GRC",
        "cluster": "Express", "channel": "Physical",
        "category_id": "C2", "state": "Expiry",
        "at_risk": 50.0, "position_qty": 5.0, "price": 10.0,
    },
    {
        "store_key": "S2", "store_name": "Store 2", "store_vertical_id": "GRC",
        "cluster": "Super", "channel": "Physical",
        "category_id": "C1", "state": "Overstock",
        "at_risk": 200.0, "position_qty": 20.0, "price": 10.0,
    },
    {
        "store_key": "S2", "store_name": "Store 2", "store_vertical_id": "GRC",
        "cluster": "Super", "channel": "Physical",
        "category_id": "C2", "state": "Healthy",
        "at_risk": 0.0, "position_qty": 1.0, "price": 5.0,
    },
]


def _scoped_stores(rows: list[dict], category_group: str | None = None, state: str | None = None) -> dict[str, dict]:
    """Mirrors the pre-filtering `build()` now does before calling `build_stores`."""
    scoped = rows
    if category_group:
        scoped = [r for r in scoped if r["category_id"] == category_group]
    if state:
        scoped = [r for r in scoped if r["state"] == state]
    return {row["store_id"]: row for row in d.build_stores(scoped)}


def test_unscoped_sums_at_risk_across_every_category_and_state() -> None:
    stores = _scoped_stores(STORE_MONEY_ROWS)
    assert stores["S1"]["at_risk_value"] == 150.0
    assert stores["S1"]["sku_count"] == 2
    assert stores["S2"]["at_risk_value"] == 200.0


def test_category_filter_narrows_the_store_rollup() -> None:
    """This is the fix: picking a category used to leave both stores' totals
    unchanged (150 and 200); it should now drop each store's other-category
    exposure instead of ignoring the filter."""
    stores = _scoped_stores(STORE_MONEY_ROWS, category_group="C1")
    assert stores["S1"]["at_risk_value"] == 100.0
    assert stores["S1"]["sku_count"] == 1
    assert stores["S2"]["at_risk_value"] == 200.0
    assert stores["S2"]["sku_count"] == 1


def test_category_filter_drops_a_store_with_no_matching_rows() -> None:
    stores = _scoped_stores(STORE_MONEY_ROWS, category_group="C2")
    assert set(stores) == {"S1", "S2"}
    assert stores["S1"]["at_risk_value"] == 50.0
    assert stores["S2"]["at_risk_value"] == 0.0


def test_state_filter_narrows_the_store_rollup_and_can_drop_a_store_entirely() -> None:
    """S2 carries no Expiry rows at all, so it should disappear from the
    rollup rather than keep showing its full all-state total."""
    stores = _scoped_stores(STORE_MONEY_ROWS, state="Expiry")
    assert set(stores) == {"S1"}
    assert stores["S1"]["at_risk_value"] == 50.0
    assert stores["S1"]["expiry_count"] == 1


def test_category_and_state_filters_compose() -> None:
    stores = _scoped_stores(STORE_MONEY_ROWS, category_group="C1", state="Overstock")
    assert stores["S1"]["at_risk_value"] == 100.0
    assert stores["S2"]["at_risk_value"] == 200.0

    stores = _scoped_stores(STORE_MONEY_ROWS, category_group="C2", state="Overstock")
    assert set(stores) == set()
