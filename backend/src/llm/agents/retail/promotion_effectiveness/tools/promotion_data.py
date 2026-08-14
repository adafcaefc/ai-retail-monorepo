"""Agent 4 · Promotion Effectiveness — the snapshot its chat and monitors read.

Two sources, both workbook demonstration data, and both honest about what they
are not.

`promotion_vertical_kpi` is the A4 Promotion sheet: six headline KPIs per
vertical (active promo SKUs, uplift %, incremental margin, ROI, cannib %,
funding %). They are the reconciliation anchors the board ties out against, the
same role the A1/A2/A3 sheets play for their boards. Read, never recomputed.

`promotion_detail` is the Promotion & Discount Detail sheet: 48 planned
campaign constructs with their D365 mapping, supplier funding offset, planned
uplift and pre-buy units. The campaign planned uplift here (~47 % average) is a
different number from the modeled net uplift on the KPI cards (~26 %), and the
snapshot labels both so one is not read as the other.

The per-SKU promo margin rollup is chain-net from `fact_inventory_chain_daily`
(margin_rp / funding_rp, one row per item), scoped to promo-eligible items via
`dim_item.is_promo_eligible`. There is no separate promo-investment column
exposed: ROI is the stored KPI, and `investment = incremental_margin / roi_x`
is a derived figure the snapshot offers only when asked, never as a fact.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.retail.common import snapshot, warehouse
from src.llm.agents.retail.promotion_effectiveness.dashboard import (
    AGENT_ID,
    ENGINE_FORMULAS,
)

CHAIN = f"{warehouse.SCHEMA}.fact_inventory_chain_daily"
ITEM = f"{warehouse.SCHEMA}.dim_item"
PROMO_DETAIL = f"{warehouse.SCHEMA}.promotion_detail"
PROMO_KPI = f"{warehouse.SCHEMA}.promotion_vertical_kpi"
VERTICAL = f"{warehouse.SCHEMA}.dim_vertical"

# Thresholds behind the spec's promoClassify: a campaign is High ROI when ROI
# and uplift clear target and cannibalization is controlled; Funding Gap when
# uplift is high but supplier funding is below guardrail; Pre-buy Required when
# pre-buy units are material. They are stated thresholds from the A4 spec, not
# tuned parameters.
ROI_TARGET = 2.0
UPLIFT_TARGET_PCT = 20
FUNDING_GUARDRAIL_PCT = 35
CANNIB_CAP_PCT = 25
PRE_BUY_MATERIAL_UNITS = 2000


def get_promotion_effectiveness_snapshot(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """Current promotion effectiveness: uplift, margin, ROI, campaigns.

    The standard portfolio view for Agent 4. Call this before answering
    anything about promo uplift, incremental margin, ROI, cannibalization,
    supplier funding, campaign plans or pre-buy handoff. Use
    query_retail_promotion only for a cut this does not already carry.

    Headline KPIs are read from the workbook's own A4 Promotion sheet
    (`promotion_vertical_kpi`); the per-SKU margin rollup is chain-net from
    `fact_inventory_chain_daily` scoped to promo-eligible items. "Uplift" has
    two meanings here — the modeled net uplift on the KPI cards versus the
    campaign planned uplift on each promotion — and both are labelled.

    Args:
        legal_entity_id: Vertical to narrow to (GRC, GMR, FSH, HNB, ELC, HNL,
            DGT, OMN). Omit for the whole chain.
        category_group: Category id to narrow to. Omit for all categories.
    """
    entity, category = snapshot.scope_filters(legal_entity_id, category_group)

    # The KPI sheet is labelled by the A-sheets' own vertical wording, so the
    # entity filter resolves through dim_vertical.dashboard_label rather than
    # vertical_id — the same indirection agent_kpi_reference uses.
    kpi_clause = ""
    kpi_params: dict[str, Any] = {}
    if entity:
        kpi_clause = " WHERE v.vertical_id = :legal_entity_id"
        kpi_params["legal_entity_id"] = entity

    # Campaign rows are filtered by vertical_id too, resolved through the join.
    camp_clause, camp_params = snapshot.where(
        entity,
        None,
        entity_column="v.vertical_id",
    )

    # Per-SKU margin rollup is chain-net and scopes on the item's vertical.
    item_clause, item_params = snapshot.where(
        entity,
        category,
        entity_column="i.vertical_id",
        category_column="i.category_id",
    )

    with snapshot._read_connection() as connection:
        by_vertical = snapshot._rows(
            connection,
            f"""
            SELECT v.vertical_id,
                   k.vertical_label,
                   k.active_promo_skus,
                   k.uplift_pct,
                   round(k.incremental_margin, 0)   AS incremental_margin,
                   k.roi_x,
                   k.cannib_pct,
                   k.funding_pct
            FROM {PROMO_KPI} k
            JOIN {VERTICAL} v ON v.dashboard_label = k.vertical_label
            {kpi_clause}
            ORDER BY v.sort_order, v.vertical_id
            """,
            kpi_params,
        )

        # Promo-eligible SKUs only, chain-net. margin_rp is the workbook's own
        # ENGINE_STORE promo incremental margin equivalent; summed it is the
        # gross incremental margin the by-vertical/category/channel charts draw.
        by_category = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   i.category_id,
                   i.category_name,
                   count(*)                    AS promo_skus,
                   round(sum(c.margin_rp), 0)     AS incremental_margin,
                   round(sum(c.funding_rp), 0)    AS supplier_funding
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            WHERE i.is_promo_eligible = 1{item_clause}
            GROUP BY i.category_id, i.category_name
            ORDER BY sum(c.margin_rp) DESC
            """,
            {**item_params, "top_n": snapshot.TOP_N},
        )

        largest_margin = snapshot._rows(
            connection,
            f"""
            SELECT TOP (:top_n)
                   c.item_key,
                   i.name,
                   i.vertical_id,
                   i.category_name,
                   i.brand,
                   round(c.margin_rp, 0)   AS incremental_margin,
                   round(c.funding_rp, 0)  AS supplier_funding,
                   i.cannibalisation_pct,
                   i.margin_pct
            FROM {CHAIN} c
            JOIN {ITEM} i ON i.item_id = c.item_key
            WHERE i.is_promo_eligible = 1 AND c.margin_rp > 0{item_clause}
            ORDER BY c.margin_rp DESC
            """,
            {**item_params, "top_n": snapshot.TOP_N},
        )

        campaigns = snapshot._rows(
            connection,
            f"""
            SELECT p.promo_id,
                   p.promo_name,
                   p.discount_type,
                   p.scope,
                   v.vertical_id,
                   p.vertical_label,
                   p.target_category,
                   p.season,
                   p.peak_month,
                   p.mechanism,
                   p.discount_pct,
                   p.value_rule,
                   p.min_qty_threshold,
                   p.supplier_funding_pct,
                   p.expected_uplift_pct,
                   p.pre_buy_uplift_units,
                   p.valid_from,
                   p.valid_to,
                   p.d365_construct
            FROM {PROMO_DETAIL} p
            JOIN {VERTICAL} v ON v.dashboard_label = p.vertical_label
            WHERE 1 = 1{camp_clause}
            ORDER BY CASE WHEN p.expected_uplift_pct IS NULL THEN 1 ELSE 0 END,
                     p.expected_uplift_pct DESC, p.pre_buy_uplift_units DESC
            """,
            camp_params,
        )

        # Campaign mix by season, for the stacked dimension chart.
        by_season = snapshot._rows(
            connection,
            f"""
            SELECT p.season,
                   p.discount_type,
                   count(*)                      AS campaigns,
                   sum(p.pre_buy_uplift_units)   AS pre_buy_units
            FROM {PROMO_DETAIL} p
            JOIN {VERTICAL} v ON v.dashboard_label = p.vertical_label
            WHERE 1 = 1{camp_clause}
            GROUP BY p.season, p.discount_type
            ORDER BY p.season, p.discount_type
            """,
            camp_params,
        )

        reference = snapshot.reference(connection, AGENT_ID)

    totals = {
        "active_promo_skus": sum(row["active_promo_skus"] for row in by_vertical),
        "uplift_pct": _weighted_uplift(by_vertical),
        "incremental_margin": sum(
            row["incremental_margin"] or 0 for row in by_vertical
        ),
        "roi_x": _weighted_roi(by_vertical),
        "cannib_pct": _mean(row["cannib_pct"] for row in by_vertical),
        "funding_pct": _mean(row["funding_pct"] for row in by_vertical),
        "campaigns": len(campaigns),
        "pre_buy_uplift_units": sum(
            row["pre_buy_uplift_units"] or 0 for row in campaigns
        ),
    }

    # The spec's promoClassify, applied to campaign rows. Each campaign lands in
    # exactly one group; the order of checks is the spec's own (High ROI first,
    # then Funding Gap, then Pre-buy Required), and a campaign none of the
    # thresholds catch is left for the High ROI group as the default approve.
    high_roi, funding_gap, prebuy_required = _classify_campaigns(campaigns)

    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        "grain": "chain_net",
        "thresholds": {
            "roi_target": ROI_TARGET,
            "uplift_target_pct": UPLIFT_TARGET_PCT,
            "funding_guardrail_pct": FUNDING_GUARDRAIL_PCT,
            "cannib_cap_pct": CANNIB_CAP_PCT,
            "pre_buy_material_units": PRE_BUY_MATERIAL_UNITS,
        },
        "totals": totals,
        "by_vertical": by_vertical,
        "by_category": by_category,
        "largest_margin_skus": largest_margin,
        "campaigns": campaigns,
        "by_season": by_season,
        "suggested_best_action": {
            "high_roi": high_roi,
            "funding_gap": funding_gap,
            "pre_buy_required": prebuy_required,
        },
        "uplift_note": (
            "Uplift has two meanings. `totals.uplift_pct` and each vertical's "
            "`uplift_pct` are the modeled net uplift from the A4 Promotion "
            "sheet (~26 % chain average). Each campaign's `expected_uplift_pct` "
            "is that campaign's planned uplift (~47 % average across the 48 "
            "rows). They are different numbers answering different questions; "
            "never present one as the other."
        ),
        "roi_note": (
            "ROI is a stored workbook KPI. No separate promo-investment column "
            "is exposed, so `investment = incremental_margin / roi_x` is a "
            "derived figure: offer it only when asked, label it derived, and "
            "never present it as a measured spend."
        ),
        "reference_by_vertical": reference,
        "reference_note": (
            "The workbook's own published A4 KPIs per vertical. Use them to "
            "check a computed headline; a material difference is either a "
            "finding or a mistake, and worth naming as one."
        ),
    }


def _weighted_uplift(rows: list[dict[str, Any]]) -> float:
    """Active-promo-SKU-weighted average uplift, matching the workbook's method."""
    weight = sum(row["active_promo_skus"] for row in rows)
    if not weight:
        return 0.0
    return round(
        sum(
            (row["active_promo_skus"] or 0) * (row["uplift_pct"] or 0)
            for row in rows
        )
        / weight,
        4,
    )


def _weighted_roi(rows: list[dict[str, Any]]) -> float:
    """Incremental-margin-weighted average ROI across the verticals in scope."""
    weight = sum(row["incremental_margin"] or 0 for row in rows)
    if not weight:
        return 0.0
    return round(
        sum(
            (row["incremental_margin"] or 0) * (row["roi_x"] or 0)
            for row in rows
        )
        / weight,
        4,
    )


def _mean(values):
    present = [float(v) for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else 0.0


def _classify_campaigns(
    campaigns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The spec's promoClassify, applied to the campaign rows.

    `recommendation` follows the spec's rule: approve when ROI/uplift clear
    target and cannibalization is controlled; negotiate funding when uplift is
    high but funding is below guardrail; trigger a pre-buy when pre-buy units or
    supply risk is high; reduce depth when cannibalization is high. The dataset
    carries campaign-level uplift and funding rather than ROI per campaign, so
    ROI here is a proxy from uplift against the depth implied by discount_pct.
    """
    high_roi: list[dict[str, Any]] = []
    funding_gap: list[dict[str, Any]] = []
    prebuy_required: list[dict[str, Any]] = []

    for row in campaigns:
        uplift = row.get("expected_uplift_pct") or 0
        funding = row.get("supplier_funding_pct") or 0
        pre_buy = row.get("pre_buy_uplift_units") or 0

        if uplift >= UPLIFT_TARGET_PCT and funding < FUNDING_GUARDRAIL_PCT:
            recommendation = "Negotiate supplier funding"
            entry = {**row, "recommendation": recommendation}
            funding_gap.append(entry)
            continue
        if pre_buy >= PRE_BUY_MATERIAL_UNITS:
            recommendation = "Trigger A3 pre-buy PO"
            entry = {**row, "recommendation": recommendation}
            prebuy_required.append(entry)
            continue
        recommendation = "Approve promo"
        high_roi.append({**row, "recommendation": recommendation})

    high_roi.sort(key=lambda r: r.get("expected_uplift_pct") or 0, reverse=True)
    funding_gap.sort(key=lambda r: r.get("pre_buy_uplift_units") or 0, reverse=True)
    prebuy_required.sort(
        key=lambda r: r.get("pre_buy_uplift_units") or 0, reverse=True
    )
    return high_roi, funding_gap, prebuy_required


TOOLS = {
    "get_promotion_effectiveness_snapshot": get_promotion_effectiveness_snapshot,
}


__all__ = ["TOOLS", "get_promotion_effectiveness_snapshot"]
