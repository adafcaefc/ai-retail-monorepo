"""Agent 4 · Promotion Effectiveness — the rows the board aggregates.

Returns the same shape the fixture builder writes, so the board's selectors run
over it unchanged. See `retail/common/warehouse.py` for why the aggregation
stays in the browser: a second implementation of the same arithmetic is a thing
this project has spent a phase removing, and the promo KPI rollups are no
exception.

FOUR SOURCES, ONE GRAIN EACH
-----------------------------
`items` are the promo-eligible SKUs, chain-net (one row per item, 800 of which
roughly a quarter carry the promo flag). Each carries the chain-net margin_rp
and funding_rp the workbook's ENGINE_STORE holds, plus the cannibalisation,
margin and price inputs behind f13-incremental-promotion-margin.

`campaigns` are the 48 Promotion & Discount Detail rows verbatim, with their
vertical resolved to vertical_id through dim_vertical.dashboard_label. Their
`expected_uplift_pct` is a campaign-planned figure distinct from the modeled
net uplift on the KPI cards, and the board says so.

`stores` is a plain dim_store dimension read (no fact join): store_id, name,
vertical_id, cluster, channel, size_index. The frontend selectors turn this
into by-store/cluster/channel incremental margin by scaling each item's own
incremental_margin by `store.size_index / item.store_size` — exact, not an
approximation, because f01 is multiplicative in store_size and f13 is linear
in ads (see selectors.js for the proof). No formula is re-evaluated here.

`reference_by_vertical` is the A4 Promotion sheet pivoted wide — the six
headline KPIs per vertical every computed figure reconciles against.
"""

from __future__ import annotations

from typing import Any

from src.formulas import repository
from src.formulas.expression import evaluate, parse
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import (
    SCHEMA,
    SNAPSHOT_DATE,
    SUPPORTED_FILTERS,
    _rows,
    _scope_clause,
    agent_reference,
    envelope,
    filter_options,
    formulas,
    get_engine,
)

AGENT_ID = "retail.promotion_effectiveness"

# The incremental promotion margin is computed from f13 (not read from the
# chain margin_rp column, which is a different measure — the chain's total
# weekly margin). Parsed once, lazily, on first use — NOT at import time.
# Every other retail board only touches the DB inside build(); importing this
# module (e.g. via the agent registry at process start) must not require a
# live connection either. _f13_margin runs once per chain row rather than
# once per request, so the AST is cached across calls instead of re-parsed.
_f13_ast_cache: Any | None = None


def _f13_ast() -> Any:
    global _f13_ast_cache
    if _f13_ast_cache is None:
        catalogue = {entry["id"]: entry["expression"] for entry in repository.load()}
        _f13_ast_cache = parse(catalogue["f13-incremental-promotion-margin"])
    return _f13_ast_cache


def _f13_margin(row: dict) -> float:
    """Incremental promotion margin for one chain row, via the f13 formula.

    `cannibalisation_pct` and `funding_pct` both live on dim_item as fractions
    (0.1596, 0.4862); f13 takes them as fractions. This matches the fixture
    builder, which reads the same sku_master columns. `margin_rp`/`funding_rp`
    on the chain fact are a different measure (total weekly margin / funding)
    and are NOT used for the incremental margin.
    """
    return evaluate(
        _f13_ast(),
        {
            "ads": _float(row["ads"]),
            "price": _float(row["unit_price"]),
            "margin_pct": _float(row["margin_pct"]),
            "cannibalization": _float(row["cannibalisation_pct"]),
            "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
            "promo_funding": _float(row.get("funding_pct") or 0),
        },
    )

# The rules this board's What-If engine evaluates — the same two the fixture
# ships. f01 sizes the base daily rate the promo uplift multiplies; f13 is the
# incremental promotion margin the cards and charts reconcile against. Keep
# these in lockstep with CATALOGUE_FORMULAS in build_promotion_effectiveness_fixture.py.
ENGINE_FORMULAS = (
    "f01-ads-per-store",
    "f13-incremental-promotion-margin",
)

CHAIN = f"{SCHEMA}.fact_inventory_chain_daily"
ITEM = f"{SCHEMA}.dim_item"
PROMO_DETAIL = f"{SCHEMA}.promotion_detail"
PROMO_KPI = f"{SCHEMA}.promotion_vertical_kpi"
VERTICAL = f"{SCHEMA}.dim_vertical"

NOTE = (
    "Workbook demonstration data, not a live ERP or D365 Commerce position. "
    "ROI is a stored KPI; no separate promo-investment column is exposed."
)

# The promoClassify thresholds (A4 spec section 7). Mirrored in the fixture
# builder and the frontend contract so all three agree on what "high ROI",
# "funding gap" and "pre-buy required" mean.
THRESHOLDS = {
    "roi_target": 2,
    "uplift_target_pct": 20,
    "funding_guardrail_pct": 35,
    "cannib_cap_pct": 25,
    "pre_buy_material_units": 2000,
}


def _arch_horizon_factor(
    ads: float, base_ads: float, seasonality: float, store_size: float
) -> float:
    """Recover f01's archetype/horizon factor from the row it was applied to.

    Same reconstruction as `inventory_risk/dashboard.py`'s helper of the same
    name: the warehouse stores the finished `ads` and the three inputs beside
    it, but not the factor between them (no table persists v8.5's `archhz`
    column), so it is divided back out. At the workbook's own lever setting
    f01 reduces to

        ads = base_ads x seasonality x arch_horizon_factor x store_size

    because the promo branch returns 1 when `Constants` B17 is zero. The
    division is therefore exact, not a fit.

    Without this, the browser's What-If engine feeds f01
    `arch_horizon_factor: undefined` the moment a lever moves or the Store
    filter is used (both re-run f01 unconditionally), and the formula
    evaluator throws "Operator '*' needs a number, got undefined".

    A zero denominator means the row carries no usable inputs; 1.0 keeps it
    arithmetically neutral rather than emitting a NaN that would spread
    through every KPI the moment a lever moved.
    """
    denominator = base_ads * seasonality * store_size
    return ads / denominator if denominator else 1.0


def build_items(rows: list[dict]) -> list[dict]:
    """One promo-eligible SKU per row, chain-net, with its promo economics.

    `incremental_margin` is the f13-computed incremental promotion margin, not
    the chain margin_rp — a different measure (see `_f13_margin`). This matches
    what the fixture builder ships, so the API and the fixture agree.
    `cannibalisation_pct` / `promo_funding` are carried as display percentages
    (26 meaning 26%); the frontend What-If engine divides by 100 when feeding f13.

    `state` / `inventory_value` ride along from `fact_inventory_chain_daily`
    for the inventory-state-exposure chart (spec section 6): that measure is
    inventory value, not incremental margin, and intentionally does not
    reconcile to the headline (spec section 11).
    """
    items = []
    for row in rows:
        cannib = _float(row["cannibalisation_pct"])
        funding = _float(row.get("funding_pct") or 0)
        ads = _float(row["ads"])
        base_ads = _float(row["base_ads"])
        seasonality = _float(row["seasonality_index"])
        store_size = _float(row.get("store_size") or 0)
        items.append(
            {
                "sku_id": row["item_key"],
                "name": row["name"],
                "vertical_id": row["vertical_id"],
                "category_id": row["category_id"],
                "category_label": row["category_name"],
                "brand": row["brand"],
                "price": _float(row["unit_price"]),
                "margin_pct": _float(row["margin_pct"]),
                "ads": ads,
                "incremental_margin": _f13_margin(row),
                "supplier_funding": _float(row["funding_rp"]),
                "supplier_funding_pct": funding * 100.0,
                "cannibalisation_pct": cannib * 100.0,
                "state": row.get("state"),
                "inventory_value": _float(row.get("inventory_value")),
                # What-If inputs the browser re-evaluates f01 / f13 against.
                "base_ads": base_ads,
                "seasonality": seasonality,
                "arch_horizon_factor": _arch_horizon_factor(ads, base_ads, seasonality, store_size),
                "store_size": store_size,
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": cannib * 100.0,
                "promo_funding": funding * 100.0,
            }
        )
    return items


def build_stores(rows: list[dict]) -> list[dict]:
    """One row per store, for the by-store/cluster/channel dimension charts.

    A plain `dim_store` dimension read — no fact-table join. `f01` is purely
    multiplicative in `store_size` and `f13` is linear in `ads`, so a store's
    incremental margin is exactly `item.incremental_margin * (store.size_index
    / item.store_size)`; the frontend selectors do that multiplication over
    this dimension list rather than this backend re-evaluating f13 per store.
    """
    return [
        {
            "store_id": row["store_id"],
            "name": row["name"],
            "vertical_id": row["vertical_id"],
            "cluster": row["cluster"],
            "channel": row["channel"],
            "size_index": _float(row["size_index"]),
        }
        for row in rows
    ]


def classify_campaign(row: dict) -> str:
    """The spec's promoClassify — mirrored in the fixture builder verbatim.

    High ROI (approve) when uplift/funding/cannib are acceptable; Funding Gap
    when uplift is high but funding is below guardrail; Pre-buy Required when
    pre-buy units are material. Order matters and follows the A4 spec.
    """
    uplift = _float(row.get("expected_uplift_pct"))
    funding = _float(row.get("supplier_funding_pct"))
    pre_buy = _float(row.get("pre_buy_uplift_units"))
    if uplift >= THRESHOLDS["uplift_target_pct"] and funding < THRESHOLDS["funding_guardrail_pct"]:
        return "Negotiate supplier funding"
    if pre_buy >= THRESHOLDS["pre_buy_material_units"]:
        return "Trigger A3 pre-buy PO"
    return "Approve promo"


def build_campaigns(rows: list[dict]) -> list[dict]:
    """The 48 campaign rows, vertical resolved to vertical_id, classified."""
    campaigns = []
    for row in rows:
        campaigns.append(
            {
                "promo_id": row["promo_id"],
                "promo_name": row["promo_name"],
                "discount_type": row["discount_type"],
                "scope": row["scope"],
                "vertical_id": row["vertical_id"],
                "vertical_label": row["vertical_label"],
                "target_category": row["target_category"],
                "season": row["season"],
                "peak_month": row["peak_month"],
                "mechanism": row["mechanism"],
                "discount_pct": row["discount_pct"],
                "value_rule": row["value_rule"],
                "min_qty_threshold": row["min_qty_threshold"],
                "supplier_funding_pct": row["supplier_funding_pct"],
                "expected_uplift_pct": row["expected_uplift_pct"],
                "pre_buy_uplift_units": row["pre_buy_uplift_units"],
                "valid_from": row["valid_from"].isoformat()
                if row["valid_from"]
                else None,
                "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
                "d365_construct": row["d365_construct"],
                "recommendation": classify_campaign(row),
            }
        )
    return campaigns


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    # Promo-eligible items scope on the item's own vertical and category.
    where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
    params["day"] = SNAPSHOT_DATE

    # Campaigns scope on vertical only (their target_category is free text, not
    # a dim_item category_id, so category_group does not apply).
    camp_where, camp_params = _scope_clause(scope, "v.vertical_id", None)

    with get_engine().connect() as connection:
        items_rows = _rows(
            connection,
            f"""
            SELECT c.item_key, c.ads, c.unit_price, c.margin_rp, c.funding_rp,
                   c.state, c.inventory_value,
                   i.name, i.vertical_id, i.category_id, i.category_name, i.brand,
                   i.margin_pct, i.base_ads, i.seasonality_index,
                   i.is_promo_eligible, i.cannibalisation_pct, i.funding_pct,
                   sz.total AS store_size
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            JOIN {VERTICAL} vt ON vt.vertical_id = i.vertical_id
            JOIN (
                SELECT vertical_id, sum(size_index) AS total
                FROM {SCHEMA}.dim_store GROUP BY vertical_id
            ) sz ON sz.vertical_id = i.vertical_id
            WHERE c.cal_date = :day AND i.is_promo_eligible = 1{where}
            ORDER BY vt.sort_order, c.margin_rp DESC
            """,
            params,
        )

        campaign_rows = _rows(
            connection,
            f"""
            SELECT p.promo_id, p.promo_name, p.discount_type, p.scope,
                   v.vertical_id, p.vertical_label, p.target_category,
                   p.season, p.peak_month, p.mechanism, p.discount_pct,
                   p.value_rule, p.min_qty_threshold, p.supplier_funding_pct,
                   p.expected_uplift_pct, p.pre_buy_uplift_units,
                   p.valid_from, p.valid_to, p.d365_construct
            FROM {PROMO_DETAIL} p
            JOIN {VERTICAL} v ON v.dashboard_label = p.vertical_label
            JOIN {VERTICAL} vt ON vt.vertical_id = v.vertical_id
            WHERE 1 = 1{camp_where}
            ORDER BY vt.sort_order,
                     CASE WHEN p.expected_uplift_pct IS NULL THEN 1 ELSE 0 END,
                     p.expected_uplift_pct DESC,
                     p.pre_buy_uplift_units DESC
            """,
            camp_params,
        )

        # A plain dimension read for the by-store/cluster/channel charts.
        # Vertical-only scope, matching filter_options.stores.
        store_where, store_params = _scope_clause(scope, "vertical_id", None)
        store_rows = _rows(
            connection,
            f"""
            SELECT store_id, name, vertical_id, cluster, channel, size_index
            FROM {SCHEMA}.dim_store
            WHERE 1 = 1{store_where}
            ORDER BY store_id
            """,
            store_params,
        )

        options = filter_options(connection)
        reference = agent_reference(connection, AGENT_ID)

    return {
        **envelope(AGENT_ID, NOTE),
        "thresholds": THRESHOLDS,
        "formulas": formulas(ENGINE_FORMULAS),
        "filter_options": {
            key: options[key] for key in ("legal_entities", "categories", "stores")
        },
        "items": build_items(items_rows),
        "campaigns": build_campaigns(campaign_rows),
        "stores": build_stores(store_rows),
        "reference_by_vertical": reference,
    }


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


__all__ = ["SUPPORTED_FILTERS", "build"]
