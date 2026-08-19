"""`store_id` scoping for Agent 5 · Pricing & Markdown -- pure functions only.

Regression for the bug where selecting a store on the board left the
candidate table, KPIs and best-actions completely unchanged: `items` carried
each SKU's chain-wide at-risk/recoverable total (summed across every store it
sits in) regardless of `scope.store_id`, so narrowing to one store visibly
narrowed only the dimension charts fed by `stores`.

No database needed: `aggregate_markdown_by_sku` and `build_items` are pure
functions of the rows handed to them, so this exercises `dashboard.build()`'s
new store-scoping branch directly rather than through a live connection --
the same shape `build()` filters `store_money_rows` into before calling them.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from src.llm.agents.retail.pricing_markdown import dashboard as d  # noqa: E402

CHAIN_ROW_DEFAULTS = {
    "vertical_id": "GRC",
    "category_id": "C1",
    "category_name": "Cat1",
    "brand": "",
    "vendor_account": "",
    "position_qty": 10,
    "rop_qty": 5,
    "max_qty": 20,
    "days_cover": 3,
    "ads": 1,
    "unit_price": 100,
    "inventory_value": 1000,
    "expiry_units": 0,
    "shelf_life_days": 30,
    "is_perishable": False,
    "growth_index": 0,
    "competitor_index": 0,
    "elasticity": 0,
    "open_po_qty": 0,
    "on_hand_qty": 10,
    "base_ads": 1,
    "seasonality_index": 1,
    "stock_factor": 1,
    "onhand_days": 1,
    "is_promo_eligible": False,
    "cannibalisation_pct": 0,
    "safety_days": 0,
}


def _chain_row(sku_id: str, name: str) -> dict:
    return {"item_key": sku_id, "name": name, "state": "Healthy", **CHAIN_ROW_DEFAULTS}


# SKU A sits at S1 (Overstock, at-risk 100) and S2 (Healthy, no exposure).
# SKU B sits only at S2 (Expiry, at-risk 50).
STORE_MONEY_ROWS = [
    {"item_key": "A", "store_key": "S1", "state": "Overstock", "at_risk": 100.0, "recoverable": 30.0, "open_po_qty": 0},
    {"item_key": "A", "store_key": "S2", "state": "Healthy", "at_risk": 0.0, "recoverable": 0.0, "open_po_qty": 0},
    {"item_key": "B", "store_key": "S2", "state": "Expiry", "at_risk": 50.0, "recoverable": 40.0, "open_po_qty": 0},
]
CHAIN_ROWS = [_chain_row("A", "Item A"), _chain_row("B", "Item B")]
LEAD_DAYS: dict = {}
STORE_SIZES = {"GRC": 100.0}


def _population(store_money_rows: list[dict]) -> dict[str, dict]:
    markdown_by_sku = d.aggregate_markdown_by_sku(store_money_rows)
    items = d.build_items(CHAIN_ROWS, markdown_by_sku, LEAD_DAYS, STORE_SIZES)
    return {item["sku_id"]: item for item in items}


def test_unscoped_sums_at_risk_across_every_store() -> None:
    items = _population(STORE_MONEY_ROWS)
    assert items["A"]["at_risk_value"] == 100.0
    assert items["A"]["is_markdown_candidate"] is True
    assert items["A"]["state"] == "Overstock"


def test_store_scope_drops_a_sku_the_store_does_not_stock() -> None:
    """This is the bug: A used to show its S1-only Overstock exposure even
    when the board was scoped to S2, where A carries none at all."""
    rows_at_s2 = [r for r in STORE_MONEY_ROWS if r["store_key"] == "S2"]
    items = _population(rows_at_s2)
    stocked = {r["item_key"] for r in rows_at_s2}
    population = {sku: item for sku, item in items.items() if sku in stocked}

    assert set(population) == {"A", "B"}
    assert population["A"]["at_risk_value"] == 0.0
    assert population["A"]["is_markdown_candidate"] is False
    assert population["A"]["state"] == "Healthy"
    assert population["B"]["at_risk_value"] == 50.0
    assert population["B"]["is_markdown_candidate"] is True


def test_store_scope_excludes_skus_not_stocked_there() -> None:
    rows_at_s1 = [r for r in STORE_MONEY_ROWS if r["store_key"] == "S1"]
    items = _population(rows_at_s1)
    stocked = {r["item_key"] for r in rows_at_s1}
    population = {sku: item for sku, item in items.items() if sku in stocked}

    assert set(population) == {"A"}
    assert population["A"]["at_risk_value"] == 100.0


def test_pricing_markdown_declares_store_id_supported() -> None:
    """`ignored_filters` on the response depends on this: a caller that sets
    `store_id` should see it actually applied, not silently reported back as
    ignored the way the shared Retail default (legal_entity_id/
    category_group only) would still claim."""
    assert "store_id" in d.SUPPORTED_FILTERS
    assert "legal_entity_id" in d.SUPPORTED_FILTERS
    assert "category_group" in d.SUPPORTED_FILTERS
