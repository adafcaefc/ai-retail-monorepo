"""Agent 5 · Pricing & Markdown — the snapshot its chat and monitors read.

Unlike Promotion Effectiveness's snapshot tool, this one does not run its own
SQL. There is no pre-aggregated at-risk/recoverable column anywhere in the
schema (see dashboard.py's module docstring) -- both figures are computed
per store row via f12/f23/f14 and rolled up to SKU grain. Re-deriving that a
third time here, in slightly different SQL, is exactly the duplicated-
arithmetic risk this project has already spent a phase removing elsewhere.
So this calls `dashboard.build()` -- the one place that math lives -- and
re-aggregates its `items`/`stores` into the totals, rankings and best-action
groups a chat turn or monitoring pass needs.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common import snapshot
from src.llm.agents.retail.pricing_markdown.dashboard import (
    AGENT_ID,
    ENGINE_FORMULAS,
    build,
)

# A5 spec's markdownClassify thresholds are all inside classify()/state
# labels themselves (a SKU either is or is not a candidate; there is no
# numeric guardrail like Promotion's ROI/funding targets) -- so, unlike the
# sibling snapshot, there are no separate THRESHOLDS to restate here.
BEST_ACTION_TABS = ("expiry_markdown", "overstock_clearance", "slow_mover_price_cut", "suppress_reorder")


def get_pricing_markdown_snapshot(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """Current markdown exposure: candidates, at-risk/recoverable value, best actions.

    The standard portfolio view for Agent 5. Call this before answering
    anything about markdown candidates, at-risk value, recoverable value,
    write-off, markdown depth, suppress-reorder conflicts, or which SKUs to
    mark down first.

    A markdown candidate is a SKU with at least one store in state Expiry,
    Overstock or Slow-mover -- Stockout and Low belong to Replenishment
    (Agent 3). At-risk and recoverable value are summed from
    `fact_inventory_daily` and computed via f23 and f14 -- see the `grain`
    dataset note.

    Args:
        legal_entity_id: Vertical to narrow to (GRC, GMR, FSH, HNB, ELC, HNL,
            DGT, OMN). Omit for the whole chain.
        category_group: Category id (e.g. "GRC-C02") or category name (e.g.
            "Vegetable") to narrow to. Omit for all categories.
    """
    entity, category = snapshot.scope_filters(legal_entity_id, category_group)
    scope = DashboardScope(legal_entity_id=entity, category_group=category)
    dashboard = build(scope)

    items = dashboard["items"]
    stores = dashboard["stores"]
    candidates = [item for item in items if item["is_markdown_candidate"]]

    totals = _totals(items, candidates)
    by_vertical = _by_vertical(candidates, dashboard["reference_by_vertical"])
    by_category = _by_category(candidates)
    top_candidates = sorted(candidates, key=lambda i: i["at_risk_value"], reverse=True)[: snapshot.TOP_N]
    best_actions = _best_action_counts(candidates)
    by_store = sorted(stores, key=lambda s: s["at_risk_value"], reverse=True)[: snapshot.TOP_N]

    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        "grain": (
            "At-risk/recoverable value are summed from fact_inventory_daily "
            "(~16,000 rows, one per SKU per store): a SKU with any non-Healthy "
            "store carries exposure there. Counts beside them are DISTINCT "
            "SKUs, so a count and a value on the same line describe the same "
            "population at different resolutions -- never present a row count "
            "as a SKU count."
        ),
        "thresholds": {},
        "totals": totals,
        "by_vertical": by_vertical,
        "by_category": by_category,
        "top_candidates": top_candidates,
        "best_action_counts": best_actions,
        "by_store": by_store,
        "reference_by_vertical": dashboard["reference_by_vertical"],
        "reference_note": (
            "avg_depth_pct per vertical, weighted by candidate at-risk value "
            "from the state-based depth table f14 itself states (Expiry 40%, "
            "Overstock 25%, Slow-mover 30%). Use it to sanity-check a "
            "computed depth; a material difference is either a finding or a "
            "mistake, and worth naming as one."
        ),
    }


def _distinct_by_sku(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per distinct SKU. `comp_idx` (like every SKU_Master field) is
    constant across a SKU's ~20 store rows, so this is the population
    SKU_Master's own AVERAGEIFS operates over -- `candidates` is a biased
    ~20% subset (only Expiry/Overstock/Slow-mover rows) and must not be used
    for a per-SKU figure like comp_idx.
    """
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        sku_id = item.get("sku_id")
        if sku_id is not None and sku_id not in seen:
            seen[sku_id] = item
    return list(seen.values())


def _totals(items: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    at_risk = sum(item["at_risk_value"] for item in candidates)
    recoverable = sum(item["recoverable_value"] for item in candidates)
    # comp_idx is a per-SKU competitiveness figure, not an at-risk metric --
    # averaged over every distinct SKU in scope (matching SKU_Master's own
    # AVERAGEIFS), not just markdown candidates. See _distinct_by_sku and the
    # matching fix in frontend/.../pricing_markdown/data/selectors.js.
    comp_idx_values = [item["comp_idx"] for item in _distinct_by_sku(items) if item.get("comp_idx")]
    return {
        "markdown_candidates": len(candidates),
        "at_risk_value": round(at_risk, 2),
        "recoverable_value": round(recoverable, 2),
        "write_off_value": round(max(0.0, at_risk - recoverable), 2),
        "recovery_rate_pct": round((recoverable / at_risk) * 100, 2) if at_risk else 0.0,
        "comp_idx": round(sum(comp_idx_values) / len(comp_idx_values), 1) if comp_idx_values else 0.0,
        "items_in_scope": len(items),
    }


def _by_vertical(candidates: list[dict[str, Any]], reference: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reference_by_id = {row["legal_entity_id"]: row for row in reference}
    groups: dict[str, dict[str, Any]] = {}
    for item in candidates:
        bucket = groups.setdefault(
            item["vertical_id"],
            {"vertical_id": item["vertical_id"], "markdown_candidates": 0, "at_risk_value": 0.0, "recoverable_value": 0.0},
        )
        bucket["markdown_candidates"] += 1
        bucket["at_risk_value"] += item["at_risk_value"]
        bucket["recoverable_value"] += item["recoverable_value"]

    rows = []
    for vertical_id, bucket in groups.items():
        ref = reference_by_id.get(vertical_id, {})
        rows.append(
            {
                "vertical_id": vertical_id,
                "vertical_label": ref.get("vertical_label", vertical_id),
                "markdown_candidates": bucket["markdown_candidates"],
                "at_risk_value": round(bucket["at_risk_value"], 2),
                "recoverable_value": round(bucket["recoverable_value"], 2),
                "write_off_value": round(max(0.0, bucket["at_risk_value"] - bucket["recoverable_value"]), 2),
                "avg_depth_pct": ref.get("avg_depth_pct", 0.0),
            }
        )
    rows.sort(key=lambda r: r["at_risk_value"], reverse=True)
    return rows


def _by_category(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in candidates:
        bucket = groups.setdefault(
            item["category_id"],
            {"category_id": item["category_id"], "category_label": item["category_label"], "markdown_candidates": 0, "at_risk_value": 0.0},
        )
        bucket["markdown_candidates"] += 1
        bucket["at_risk_value"] += item["at_risk_value"]
    rows = [{**bucket, "at_risk_value": round(bucket["at_risk_value"], 2)} for bucket in groups.values()]
    rows.sort(key=lambda r: r["at_risk_value"], reverse=True)
    return rows[: snapshot.TOP_N]


def _best_action_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts = {tab: 0 for tab in BEST_ACTION_TABS}
    for item in candidates:
        tab = item.get("best_action_tab")
        if tab in counts:
            counts[tab] += 1
    return counts


TOOLS = {"get_pricing_markdown_snapshot": get_pricing_markdown_snapshot}


__all__ = ["TOOLS", "get_pricing_markdown_snapshot"]
