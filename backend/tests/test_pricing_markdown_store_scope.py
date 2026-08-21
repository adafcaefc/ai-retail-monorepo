"""`store_id` scoping for Agent 5 · Pricing & Markdown -- pure functions only.

`items` is one row per `fact_inventory_daily` record (SKU x store) -- see
`dashboard.py`'s module docstring. `store_id` is therefore a plain filter on
an intrinsic field, the same as `legal_entity_id`/`category_group`: no
SKU-level rollup, no separate recompute path. These tests exercise
`build_items()` directly (a pure function of the rows handed to it) rather
than through a live connection or `build()`'s own scoping, which is one-line
filters over exactly this same shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from src.llm.agents.retail.pricing_markdown import dashboard as d  # noqa: E402

ROW_DEFAULTS = {
    "vertical_id": "GRC",
    "category_id": "C1",
    "category_name": "Cat1",
    "brand": "",
    "vendor_account": "",
    "cluster": "Flagship",
    "channel": "Physical",
    "position_qty": 10,
    "rop_qty": 5,
    "max_qty": 20,
    "days_cover": 3,
    "ads": 1,
    "price": 100,
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
    "arch_horizon_factor": 1,
    "size_index": 100,
    "stock_factor": 1,
    "onhand_days": 1,
    "is_promo_eligible": False,
    "cannibalisation_pct": 0,
    "safety_days": 0,
    "lead_time_days": 3,
}


def _row(
    sku_id: str, store_id: str, name: str, state: str, at_risk: float, recoverable: float, gross: float = 0.0
) -> dict:
    return {
        "item_key": sku_id, "store_key": store_id, "name": name, "state": state,
        "at_risk": at_risk, "recoverable": recoverable, "gross": gross,
        **ROW_DEFAULTS,
    }


# SKU A sits at S1 (Overstock, at-risk 100) and S2 (Healthy, no exposure).
# SKU B sits only at S2 (Expiry, at-risk 50).
# `gross` (f23's at-risk-PORTION output, distinct from `at_risk`/f12's full
# position value) isn't exercised by these store-scoping tests, so it's set
# arbitrarily below `at_risk` -- only build_items()'s KeyError-free passthrough
# into `at_risk_gross` matters here, not its actual value.
STORE_MONEY_ROWS = [
    _row("A", "S1", "Item A", "Overstock", 100.0, 30.0, gross=20.0),
    _row("A", "S2", "Item A", "Healthy", 0.0, 0.0, gross=0.0),
    _row("B", "S2", "Item B", "Expiry", 50.0, 40.0, gross=45.0),
]


def _population(store_money_rows: list[dict]) -> dict[str, dict]:
    items = d.build_items(store_money_rows)
    # Keyed by (sku, store): unlike the old SKU rollup, a SKU can legitimately
    # appear more than once (at different stores) in this population.
    return {(item["sku_id"], item["store_id"]): item for item in items}


def test_every_row_keeps_its_own_state_and_candidacy() -> None:
    items = _population(STORE_MONEY_ROWS)
    assert items[("A", "S1")]["at_risk_value"] == 100.0
    assert items[("A", "S1")]["is_markdown_candidate"] is True
    assert items[("A", "S1")]["state"] == "Overstock"
    assert items[("A", "S2")]["at_risk_value"] == 0.0
    assert items[("A", "S2")]["is_markdown_candidate"] is False
    assert items[("A", "S2")]["state"] == "Healthy"
    assert items[("B", "S2")]["at_risk_value"] == 50.0
    assert items[("B", "S2")]["is_markdown_candidate"] is True


def test_store_scope_drops_a_sku_the_store_does_not_stock() -> None:
    """This is the bug: A used to show its S1-only Overstock exposure even
    when the board was scoped to S2, where A carries none at all."""
    rows_at_s2 = [r for r in STORE_MONEY_ROWS if r["store_key"] == "S2"]
    items = _population(rows_at_s2)

    assert {sku for sku, _store in items} == {"A", "B"}
    assert items[("A", "S2")]["at_risk_value"] == 0.0
    assert items[("A", "S2")]["is_markdown_candidate"] is False
    assert items[("B", "S2")]["at_risk_value"] == 50.0
    assert items[("B", "S2")]["is_markdown_candidate"] is True
    # A's S1-only Overstock exposure must not leak into the S2 scope.
    assert ("A", "S1") not in items


def test_store_scope_excludes_skus_not_stocked_there() -> None:
    rows_at_s1 = [r for r in STORE_MONEY_ROWS if r["store_key"] == "S1"]
    items = _population(rows_at_s1)

    assert {sku for sku, _store in items} == {"A"}
    assert items[("A", "S1")]["at_risk_value"] == 100.0


def test_pricing_markdown_declares_store_id_supported() -> None:
    """`ignored_filters` on the response depends on this: a caller that sets
    `store_id` should see it actually applied, not silently reported back as
    ignored the way the shared Retail default (legal_entity_id/
    category_group only) would still claim."""
    assert "store_id" in d.SUPPORTED_FILTERS
    assert "legal_entity_id" in d.SUPPORTED_FILTERS
    assert "category_group" in d.SUPPORTED_FILTERS
