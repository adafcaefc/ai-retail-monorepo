"""Agent 4 · Promotion Effectiveness — the rows the board aggregates.

Returns the same shape the fixture builder writes, so the board's selectors run
over it unchanged. See `retail/common/warehouse.py` for why the aggregation
stays in the browser: a second implementation of the same arithmetic is a thing
this project has spent a phase removing, and the promo KPI rollups are no
exception.

THREE SOURCES, ONE GRAIN EACH
-----------------------------
`items` are the promo-eligible SKUs, chain-net (one row per item, 800 of which
roughly a quarter carry the promo flag). Each carries the chain-net margin_rp
and funding_rp the workbook's ENGINE_STORE holds, plus the cannibalisation,
margin and price inputs behind f13-incremental-promotion-margin.

`campaigns` are the 48 Promotion & Discount Detail rows verbatim, with their
vertical resolved to vertical_id through dim_vertical.dashboard_label. Their
`expected_uplift_pct` is a campaign-planned figure distinct from the modeled
net uplift on the KPI cards, and the board says so.

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
# weekly margin). Parsed once at import; the catalogue is small and stable.
_catalogue = {entry["id"]: entry["expression"] for entry in repository.load()}
_F13_AST = parse(_catalogue["f13-incremental-promotion-margin"])


def _f13_margin(row: dict) -> float:
    """Incremental promotion margin for one chain row, via the f13 formula.

    `cannibalisation_pct` and `funding_pct` both live on dim_item as fractions
    (0.1596, 0.4862); f13 takes them as fractions. This matches the fixture
    builder, which reads the same sku_master columns. `margin_rp`/`funding_rp`
    on the chain fact are a different measure (total weekly margin / funding)
    and are NOT used for the incremental margin.
    """
    return evaluate(
        _F13_AST,
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
    "Incremental margin is chain-net gross (one row per item, surplus in one "
    "store already netted against shortage in another). ROI is a stored KPI; "
    "no separate promo-investment column is exposed."
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


def build_items(rows: list[dict]) -> list[dict]:
    """One promo-eligible SKU per row, chain-net, with its promo economics.

    `incremental_margin` is the f13-computed incremental promotion margin, not
    the chain margin_rp — a different measure (see `_f13_margin`). This matches
    what the fixture builder ships, so the API and the fixture agree.
    `cannibalisation_pct` / `promo_funding` are carried as display percentages
    (26 meaning 26%); the frontend What-If engine divides by 100 when feeding f13.
    """
    items = []
    for row in rows:
        cannib = _float(row["cannibalisation_pct"])
        funding = _float(row.get("funding_pct") or 0)
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
                "ads": _float(row["ads"]),
                "incremental_margin": _f13_margin(row),
                "supplier_funding": _float(row["funding_rp"]),
                "supplier_funding_pct": funding * 100.0,
                "cannibalisation_pct": cannib * 100.0,
                # What-If inputs the browser re-evaluates f01 / f13 against.
                "base_ads": _float(row["base_ads"]),
                "seasonality": _float(row["seasonality_index"]),
                "store_size": _float(row.get("store_size") or 0),
                "promo_eligible": "Y" if row["is_promo_eligible"] else "N",
                "promo_depth": cannib * 100.0,
                "promo_funding": funding * 100.0,
            }
        )
    return items


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
            WHERE c.cal_date = :day AND i.is_promo_eligible{where}
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
            ORDER BY vt.sort_order, p.expected_uplift_pct DESC NULLS LAST,
                     p.pre_buy_uplift_units DESC
            """,
            camp_params,
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
        "reference_by_vertical": reference,
    }


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


__all__ = ["SUPPORTED_FILTERS", "build"]
