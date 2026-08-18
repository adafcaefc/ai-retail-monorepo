"""Agent 6 · Assortment Optimization — the snapshots its chat and monitors read.

Chain-net throughout, from `fact_inventory_chain_daily`: one row per item, 800
of them, with surplus in one store already netted against shortage in another.
Where per-store detail appears it is named `store_gross_*`, because summing the
16,000-row grid answers a different question and a snapshot that carried both
unlabelled would invite exactly the comparison that makes two answers look like
a discrepancy.

EVERY QUERY HERE IS A CTE, AND THAT IS NOT STYLE
The productivity chain -- ADS, weekly GMV, margin, GMROI -- is four expressions
deep, and the delist verdict compares against quartiles of it. Written inline,
`GROUP BY` would have to repeat the whole chain, and repeating a `CASE` across
`SELECT` and `GROUP BY` is what breaks under parameter binding: pyodbc turns
`:threshold` into a positional `?`, the two copies get different ordinals, and
SQL Server rejects the statement with error 8120 -- "not contained in either an
aggregate function or the GROUP BY clause". `replenishment_data.py` has a live
instance of that bug. A CTE names the expression once, so there is nothing to
mismatch.

THE QUARTILES COME FROM SQL HERE, NOT FROM `dashboard.classify`
The board's cutoffs are computed in Python over the whole 800-row population,
because the browser must reproduce them exactly. These tools answer questions
rather than draw a board, and re-deriving the same population in Python to
answer "which SKUs should we delist" would mean loading 800 rows to return 12.
`PERCENTILE_CONT` over the same population gives the same boundary to well
inside any figure a person reads, and the one SKU that could sit on a cutoff is
named in the response either way.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.retail.common import snapshot, warehouse
from src.llm.agents.retail.assortment_optimization.dashboard import (
    AGENT_ID,
    ENGINE_FORMULAS,
    REBALANCE_CATEGORY_SHARE,
    VENDOR_REVIEW_THRESHOLD,
)

CHAIN = f"{warehouse.SCHEMA}.fact_inventory_chain_daily"
PER_STORE = f"{warehouse.SCHEMA}.fact_inventory_daily"
ITEM = f"{warehouse.SCHEMA}.dim_item"
STORE = f"{warehouse.SCHEMA}.dim_store"

# The delist states, spelled for SQL. Kept beside the Python frozenset in
# `dashboard.py` rather than derived from it, because a tuple interpolated into
# a query and a set tested in Python fail differently and a reader checking one
# should see the other.
DELIST_STATES_SQL = "('Slow-mover', 'Overstock', 'Expiry')"

# The productivity chain, once. Every tool below selects from this.
#
# `store_size` is the vertical's summed store-size index, NOT
# `sku_master.sum_vert_size` -- that column is rounded to four decimals and is
# not in the warehouse at all. See `warehouse.chain_store_size`.
_CHAIN_CTE = f"""
WITH size AS (
    SELECT vertical_id, sum(size_index) AS total
    FROM {STORE}
    GROUP BY vertical_id
),
base AS (
    SELECT c.item_key, c.state, c.position_qty, c.days_cover,
           c.unit_price, c.inventory_value,
           i.name, i.vertical_id, i.category_id, i.category_name,
           i.brand, i.vendor_account, i.margin_pct, i.growth_index,
           i.base_ads * i.seasonality_index * z.total AS ads
    FROM {CHAIN} c
    JOIN {ITEM} i ON i.item_id = c.item_key
    JOIN size z   ON z.vertical_id = i.vertical_id
    WHERE c.cal_date = :day{{clause}}
),
chain AS (
    SELECT b.*,
           b.ads * 7 * b.unit_price                       AS weekly_gmv,
           b.ads * 7 * b.unit_price * b.margin_pct        AS margin_rp,
           b.ads * b.unit_price * b.margin_pct            AS contribution_per_day,
           CASE WHEN b.inventory_value > 0
                THEN (b.ads * 7 * b.unit_price * b.margin_pct) / b.inventory_value
                ELSE 0 END                                AS gmroi
    FROM base b
),
cuts AS (
    SELECT DISTINCT
           percentile_cont(0.25) WITHIN GROUP (ORDER BY gmroi)                OVER () AS p25_gmroi,
           percentile_cont(0.25) WITHIN GROUP (ORDER BY contribution_per_day) OVER () AS p25_contribution
    FROM chain
),
verdict AS (
    SELECT c.*, k.p25_gmroi, k.p25_contribution,
           CASE WHEN c.contribution_per_day <= k.p25_contribution THEN 1 ELSE 0 END AS is_tail,
           CASE WHEN c.state IN {DELIST_STATES_SQL}
                     OR c.gmroi <= k.p25_gmroi
                     OR c.contribution_per_day <= k.p25_contribution
                THEN 1 ELSE 0 END AS is_delist
    FROM chain c CROSS JOIN cuts k
)
"""


def _scoped(legal_entity_id: str | None, category_group: str | None):
    """The CTE, its parameters, and the scope that was actually resolved.

    The resolved scope travels back out because `snapshot.envelope` echoes it
    into the response: a monitoring pass handed a narrowed snapshot that did
    not notice would raise a chain-wide alert from one vertical's figures.
    """
    entity, category = snapshot.scope_filters(legal_entity_id, category_group)
    clause, params = snapshot.where(
        entity,
        category,
        entity_column="i.vertical_id",
        category_column="i.category_id",
        category_name_column="i.category_name",
    )
    params["day"] = warehouse.SNAPSHOT_DATE
    return _CHAIN_CTE.format(clause=clause), params, clause, entity, category


def get_assortment_performance_snapshot(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """How the range earns its shelf space: GMROI, tail share, contribution.

    The standard portfolio view for Agent 6. Call this before answering
    anything about assortment productivity, GMROI, tail lines, delist or grow
    counts, or where contribution concentrates. Use
    `get_delist_recommendations` for the named candidates and
    `simulate_assortment_rationalization` for what a decision is worth.

    Every figure is chain-net (one row per item, netted across stores). Where
    per-store detail appears it is prefixed `store_gross_` and legitimately
    exceeds the chain-net headline.

    Args:
        legal_entity_id: Vertical to narrow to (GRC, GMR, FSH, HNB, ELC, HNL,
            DGT, OMN). Omit for the whole chain.
        category_group: Category id (e.g. "GRC-C02") or category name (e.g.
            "Vegetable") to narrow to. Omit for all categories.
    """
    cte, params, clause, entity, category = _scoped(legal_entity_id, category_group)

    with snapshot._read_connection() as connection:
        totals = snapshot._rows(
            connection,
            cte
            + """
            SELECT count(*)                                            AS sku_count,
                   sum(is_delist)                                      AS delist_candidates,
                   sum(is_tail)                                        AS tail_skus,
                   round(avg(gmroi), 4)                                AS avg_gmroi,
                   round(sum(contribution_per_day), 0)                 AS contribution_per_day,
                   round(sum(inventory_value), 0)                      AS inventory_value,
                   round(sum(CASE WHEN is_delist = 1 THEN inventory_value ELSE 0 END), 0)
                                                                       AS capital_freed,
                   round(sum(CASE WHEN is_tail = 1 THEN contribution_per_day ELSE 0 END), 0)
                                                                       AS tail_contribution,
                   round(min(p25_gmroi), 6)                            AS cutoff_gmroi_p25,
                   round(min(p25_contribution), 2)                     AS cutoff_contribution_p25
            FROM verdict
            """,
            params,
        )
        by_vertical = snapshot._rows(
            connection,
            cte
            + """
            SELECT vertical_id,
                   count(*)                            AS sku_count,
                   sum(is_delist)                      AS delist_candidates,
                   round(avg(gmroi), 4)                AS avg_gmroi,
                   round(sum(contribution_per_day), 0) AS contribution_per_day,
                   round(sum(CASE WHEN is_delist = 1 THEN inventory_value ELSE 0 END), 0)
                                                       AS capital_freed
            FROM verdict
            GROUP BY vertical_id
            ORDER BY capital_freed DESC
            """,
            params,
        )
        by_state = snapshot._rows(
            connection,
            cte
            + """
            SELECT state, count(*) AS sku_count,
                   round(sum(inventory_value), 0) AS inventory_value
            FROM verdict
            GROUP BY state
            ORDER BY inventory_value DESC
            """,
            params,
        )
        store_gross = snapshot._rows(
            connection,
            f"""
            SELECT count(DISTINCT f.store_key) AS store_count,
                   round(sum(round(f.ads * i.price * i.margin_pct, 0)), 0)
                       AS store_gross_contribution_per_day,
                   round(sum(f.position_qty * i.price), 0) AS store_gross_inventory_value
            FROM {PER_STORE} f
            JOIN {ITEM} i ON i.item_id = f.item_key
            WHERE f.cal_date = :day{clause}
            """,
            params,
        )

    head = totals[0] if totals else {}
    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        "grain_note": (
            "Chain-net: one row per item, surplus already netted against "
            "shortage across that item's stores. `store_gross_*` sums the "
            "16,000-row per-store grid and is a different question."
        ),
        "totals": head,
        "tail_share_pct": (
            round(100.0 * float(head["tail_skus"]) / float(head["sku_count"]), 1)
            if head.get("sku_count")
            else 0.0
        ),
        "by_vertical": by_vertical,
        "by_state": by_state,
        "store_gross": store_gross[0] if store_gross else {},
    }


def get_delist_recommendations(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
) -> dict[str, Any]:
    """The named SKUs that fail to earn their shelf space, worst first.

    Call this when asked which lines to delist, drop, or stop reordering, or
    which SKUs are the tail. Returns the worst candidates by the capital each
    one frees, plus why each qualified -- a SKU can qualify on its state, on
    low GMROI, or on tail contribution, and which one it was changes the
    conversation.

    Args:
        legal_entity_id: Vertical to narrow to. Omit for the whole chain.
        category_group: Category id or name to narrow to. Omit for all.
    """
    cte, params, clause, entity, category = _scoped(legal_entity_id, category_group)
    params["top_n"] = snapshot.TOP_N

    with snapshot._read_connection() as connection:
        candidates = snapshot._rows(
            connection,
            cte
            + """
            SELECT TOP (:top_n)
                   item_key, name, vertical_id, category_name, brand,
                   state, round(gmroi, 4) AS gmroi,
                   round(contribution_per_day, 0) AS contribution_per_day,
                   round(inventory_value, 0)      AS capital_freed,
                   round(days_cover, 1)           AS days_cover,
                   is_tail,
                   CASE WHEN state IN """
            + DELIST_STATES_SQL
            + """ THEN 'state'
                        WHEN gmroi <= p25_gmroi  THEN 'low GMROI'
                        ELSE 'tail contribution' END AS qualified_on
            FROM verdict
            WHERE is_delist = 1
            ORDER BY inventory_value DESC
            """,
            params,
        )
        # Where the decision stops being per-SKU. A vendor carrying enough
        # candidates is a vendor conversation; a category losing half its range
        # is a space conversation. Same thresholds the board's action tabs use.
        by_vendor = snapshot._rows(
            connection,
            cte
            + """
            SELECT vendor_account, count(*) AS delist_candidates,
                   round(sum(inventory_value), 0) AS capital_freed
            FROM verdict
            WHERE is_delist = 1
            GROUP BY vendor_account
            HAVING count(*) >= :vendor_threshold
            ORDER BY capital_freed DESC
            """,
            {**params, "vendor_threshold": VENDOR_REVIEW_THRESHOLD},
        )
        by_category = snapshot._rows(
            connection,
            cte
            + """
            SELECT category_id, category_name,
                   count(*)                                AS sku_count,
                   sum(is_delist)                          AS delist_candidates,
                   round(sum(CASE WHEN is_delist = 1 THEN inventory_value ELSE 0 END), 0)
                                                           AS capital_freed
            FROM verdict
            GROUP BY category_id, category_name
            HAVING sum(is_delist) * 1.0 / count(*) >= :share
            ORDER BY capital_freed DESC
            """,
            {**params, "share": REBALANCE_CATEGORY_SHARE},
        )

    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        "candidates": candidates,
        "vendor_review": by_vendor,
        "rebalance_categories": by_category,
        "thresholds_note": (
            f"A vendor with {VENDOR_REVIEW_THRESHOLD} or more candidates is "
            f"listed for review; a category losing "
            f"{int(REBALANCE_CATEGORY_SHARE * 100)}% or more of its range is "
            "listed for rebalancing rather than line-by-line delisting."
        ),
    }


def simulate_assortment_rationalization(
    legal_entity_id: str | None = None,
    category_group: str | None = None,
    delist_share_pct: float = 100.0,
) -> dict[str, Any]:
    """What delisting the tail is worth: capital freed against GMV given up.

    Call this when asked what a rationalization would save, how much capital
    delisting frees, or what revenue it costs. Delisting frees the inventory
    value the line is sitting on and gives up the weekly GMV it still turns --
    both are returned, because one without the other is not a decision.

    Args:
        legal_entity_id: Vertical to narrow to. Omit for the whole chain.
        category_group: Category id or name to narrow to. Omit for all.
        delist_share_pct: How much of the delist population to act on, worst
            first, as a percentage. 100 means the whole candidate list.
    """
    share = max(0.0, min(100.0, float(delist_share_pct)))
    cte, params, clause, entity, category = _scoped(legal_entity_id, category_group)

    with snapshot._read_connection() as connection:
        # Ranked so a partial action means "the worst N%", not an arbitrary N%.
        # `ranked` is a second CTE on top of `verdict` rather than a subquery,
        # for the same reason the chain is a CTE: the window function is named
        # once and the filter reads against the name.
        rows = snapshot._rows(
            connection,
            cte
            + """
            , ranked AS (
                SELECT v.*,
                       percent_rank() OVER (ORDER BY v.inventory_value DESC) AS worst_rank
                FROM verdict v
                WHERE v.is_delist = 1
            )
            SELECT count(*)                                  AS skus_acted_on,
                   round(sum(inventory_value), 0)            AS capital_freed,
                   round(sum(weekly_gmv), 0)                 AS weekly_gmv_given_up,
                   round(sum(margin_rp), 0)                  AS weekly_margin_given_up,
                   round(sum(contribution_per_day), 0)       AS contribution_given_up
            FROM ranked
            WHERE worst_rank < :share
            """,
            {**params, "share": share / 100.0},
        )
        kept = snapshot._rows(
            connection,
            cte
            + """
            SELECT count(*)                        AS skus_kept,
                   round(sum(inventory_value), 0)  AS inventory_value_kept,
                   round(avg(gmroi), 4)            AS avg_gmroi_kept
            FROM verdict
            WHERE is_delist = 0
            """,
            params,
        )

    acted = rows[0] if rows else {}
    freed = float(acted.get("capital_freed") or 0)
    gmv = float(acted.get("weekly_gmv_given_up") or 0)
    return {
        **snapshot.envelope(
            AGENT_ID,
            legal_entity_id=entity,
            category_group=category,
            formulas=ENGINE_FORMULAS,
        ),
        "delist_share_pct": share,
        "acted_on": acted,
        "retained": kept[0] if kept else {},
        # The one number the question is usually really asking: how much
        # capital comes back per rupiah of weekly revenue given up. Undefined
        # rather than infinite when nothing is given up -- a ratio against zero
        # is not a payback.
        "capital_freed_per_gmv_given_up": round(freed / gmv, 2) if gmv else None,
    }


TOOLS = {
    "get_assortment_performance_snapshot": get_assortment_performance_snapshot,
    "get_delist_recommendations": get_delist_recommendations,
    "simulate_assortment_rationalization": simulate_assortment_rationalization,
}


__all__ = [
    "TOOLS",
    "get_assortment_performance_snapshot",
    "get_delist_recommendations",
    "simulate_assortment_rationalization",
]
