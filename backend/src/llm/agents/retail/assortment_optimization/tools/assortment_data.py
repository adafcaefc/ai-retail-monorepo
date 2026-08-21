"""Agent 6 · Assortment Optimization — the snapshots its chat and monitors read.

ENGINE_STORE grain throughout, from `fact_inventory_daily`: one row per SKU per
store, 16,000 of them, matching the board's own cards. It was chain-net (800
netted rows, from `fact_inventory_chain_daily`) until that table was retired
from application code -- see docs/CHAIN_GRAIN_RETIREMENT_DELTA.md.

TWO COUNTS, AND THEY ANSWER DIFFERENT QUESTIONS
`*_lines` count SKU-store rows and partition exactly: every line is delist,
grow or hold, and the three sum to `line_count`. `*_skus` count DISTINCT SKUs
and DO NOT partition -- a SKU delisted in six stores and held in fourteen
appears in both, so the three SKU counts sum to more than `sku_count`. That is
not a defect; it is the fact chain-netting used to hide, and it is the whole
reason a per-store decision is more actionable than a netted one. Money always
sums rows.

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
)

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
# A row is one SKU IN ONE STORE. It was chain-net until the chain table was
# retired from application code, so `store_size` was the vertical's summed
# store-size index; it is now the row's own store weighting, which is what f01
# takes at this grain. The vertical sum would inflate every ADS by ~20x.
#
# What that moved is in docs/CHAIN_GRAIN_RETIREMENT_DELTA.md: the percentile
# cutoffs below recompute over the new population automatically -- which is
# exactly why they were written as `percentile_cont` rather than constants --
# so delist/grow/hold become per-store decisions and their counts rise with the
# row count while the money they describe does not move.
_PRODUCTIVITY_CTE = f"""
WITH base AS (
    SELECT c.item_key, c.store_key, c.state, c.position_qty, c.days_cover,
           -- `price` is identical in dim_item; `inventory_value` is f21.
           -- Both were columns on the retired chain table.
           i.price                  AS unit_price,
           c.position_qty * i.price AS inventory_value,
           i.name, i.vertical_id, i.category_id, i.category_name,
           i.brand, i.vendor_account, i.margin_pct, i.growth_index,
           i.base_ads * i.seasonality_index * s.size_index AS ads
    FROM {PER_STORE} c
    JOIN {ITEM} i  ON i.item_id  = c.item_key
    JOIN {STORE} s ON s.store_id = c.store_key
    WHERE c.cal_date = :day{{clause}}
),
productivity AS (
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
    FROM productivity
),
-- Grow compares against the HEALTHY subset, not the chain. In this dataset high
-- GMROI concentrates in Stockout/Low SKUs -- fast movers running short -- so a
-- chain-wide P75 intersected with `state = 'Healthy'` comes back empty. Same
-- reasoning, and the same two cutoffs, as `dashboard.classify`.
healthy_cuts AS (
    SELECT DISTINCT
           percentile_cont(0.75) WITHIN GROUP (ORDER BY gmroi)                OVER () AS p75_gmroi_healthy,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY contribution_per_day) OVER () AS p75_contribution_healthy
    FROM productivity
    WHERE state = 'Healthy'
),
scored AS (
    SELECT c.*, k.p25_gmroi, k.p25_contribution,
           h.p75_gmroi_healthy, h.p75_contribution_healthy,
           CASE WHEN c.contribution_per_day <= k.p25_contribution THEN 1 ELSE 0 END AS is_tail,
           CASE WHEN c.state IN {DELIST_STATES_SQL}
                     OR c.gmroi <= k.p25_gmroi
                     OR c.contribution_per_day <= k.p25_contribution
                THEN 1 ELSE 0 END AS is_delist,
           CASE WHEN c.state = 'Healthy'
                     AND c.contribution_per_day >= h.p75_contribution_healthy
                     AND c.gmroi >= h.p75_gmroi_healthy
                     AND c.growth_index >= 1.0
                THEN 1 ELSE 0 END AS is_grow_candidate
    FROM productivity c
    CROSS JOIN cuts k
    -- LEFT, not CROSS: a scope with no Healthy SKU leaves `healthy_cuts` empty,
    -- and a CROSS JOIN would then return no rows at all rather than no grow
    -- candidates. NULL cutoffs make every comparison NULL, so is_grow lands on
    -- 0 -- which is what `percentile([], 0.75) == 0.0` does on the Python side.
    LEFT JOIN healthy_cuts h ON 1 = 1
),
verdict AS (
    -- Delist wins over grow, so the three classes stay mutually exclusive and
    -- sum to the SKU count. `dashboard.classify` resolves the same tie the same
    -- way: "grow if (is_grow and not is_delist)".
    SELECT s.*,
           CASE WHEN s.is_grow_candidate = 1 AND s.is_delist = 0
                THEN 1 ELSE 0 END AS is_grow,
           CASE WHEN s.is_delist = 0 AND s.is_grow_candidate = 0
                THEN 1 ELSE 0 END AS is_hold
    FROM scored s
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
    return _PRODUCTIVITY_CTE.format(clause=clause), params, clause, entity, category


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

    Every figure is measured over SKU x store rows -- a decision here is
    "delist this line in this store", not "delist this SKU everywhere".
    `*_lines` partition the population; `*_skus` count DISTINCT SKUs and
    overlap, because a SKU can be delisted in some stores and held in others.

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
            SELECT count(DISTINCT item_key)                            AS sku_count,
                   count(*)                                            AS line_count,
                   -- Lines partition; SKUs do not. See the module docstring.
                   count(DISTINCT CASE WHEN is_delist = 1 THEN item_key END)
                                                                       AS delist_skus,
                   count(DISTINCT CASE WHEN is_grow = 1 THEN item_key END)
                                                                       AS grow_skus,
                   sum(is_delist)                                      AS delist_candidates,
                   sum(is_grow)                                        AS grow_candidates,
                   sum(is_hold)                                        AS hold_skus,
                   sum(is_tail)                                        AS tail_skus,
                   round(avg(gmroi), 4)                                AS avg_gmroi,
                   round(sum(contribution_per_day), 0)                 AS contribution_per_day,
                   round(sum(inventory_value), 0)                      AS inventory_value,
                   round(sum(CASE WHEN is_delist = 1 THEN inventory_value ELSE 0 END), 0)
                                                                       AS capital_freed,
                   round(sum(CASE WHEN is_tail = 1 THEN contribution_per_day ELSE 0 END), 0)
                                                                       AS tail_contribution,
                   round(min(p25_gmroi), 6)                            AS cutoff_gmroi_p25,
                   round(min(p25_contribution), 2)                     AS cutoff_contribution_p25,
                   round(min(p75_gmroi_healthy), 6)                    AS cutoff_gmroi_p75_healthy,
                   round(min(p75_contribution_healthy), 2)             AS cutoff_contribution_p75_healthy
            FROM verdict
            """,
            params,
        )
        by_vertical = snapshot._rows(
            connection,
            cte
            + """
            SELECT vertical_id,
                   count(DISTINCT item_key)            AS sku_count,
                   count(*)                            AS line_count,
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
            SELECT state,
                   count(DISTINCT item_key)       AS sku_count,
                   count(*)                       AS line_count,
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
        # Where the decision stops being per-SKU. A group earns its place by
        # being OVER-REPRESENTED in the delist list -- its own delist rate above
        # the chain's -- which is the same rule, and the same cutoff, the
        # board's action tabs use. There is no stored threshold on either side:
        # `chain` below is computed from the rows in scope, so the tool and the
        # board move together when a filter changes.
        by_vendor = snapshot._rows(
            connection,
            cte
            + """
            , chain_rate AS (SELECT avg(CAST(is_delist AS float)) AS rate FROM verdict)
            SELECT v.vendor_account,
                   count(DISTINCT v.item_key)                AS sku_count,
                   count(*)                                  AS line_count,
                   sum(v.is_delist)                          AS delist_candidates,
                   round(avg(CAST(v.is_delist AS float)), 4) AS delist_rate,
                   round(sum(CASE WHEN v.is_delist = 1 THEN v.inventory_value ELSE 0 END), 0)
                                                             AS capital_freed
            FROM verdict v CROSS JOIN chain_rate c
            GROUP BY v.vendor_account, c.rate
            HAVING avg(CAST(v.is_delist AS float)) > min(c.rate)
            ORDER BY capital_freed DESC
            """,
            params,
        )
        by_category = snapshot._rows(
            connection,
            cte
            + """
            , chain_rate AS (SELECT avg(CAST(is_delist AS float)) AS rate FROM verdict)
            SELECT v.category_id, v.category_name,
                   count(DISTINCT v.item_key)                AS sku_count,
                   count(*)                                  AS line_count,
                   sum(v.is_delist)                          AS delist_candidates,
                   round(avg(CAST(v.is_delist AS float)), 4) AS delist_rate,
                   round(sum(CASE WHEN v.is_delist = 1 THEN v.inventory_value ELSE 0 END), 0)
                                                             AS capital_freed
            FROM verdict v CROSS JOIN chain_rate c
            GROUP BY v.category_id, v.category_name, c.rate
            HAVING avg(CAST(v.is_delist AS float)) > min(c.rate)
            ORDER BY capital_freed DESC
            """,
            params,
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
            "A vendor or category is listed when its own delist rate is above "
            "the chain's delist rate for the same scope -- it carries more than "
            "its share of the delist list. Nothing here is a fixed count: the "
            "cutoff is recomputed from the rows in scope, so it moves with the "
            "filters, and it is the same rule behind the board's Vendor Review "
            "and Rebalance Space tabs."
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
        #
        # `cume_dist`, not `percent_rank`, and `<=`, not `<`. percent_rank puts
        # the first row at 0 and the LAST row at 1.0, so `worst_rank < 1.0`
        # silently dropped one SKU from a 100% rationalization -- the whole
        # candidate list came back one short of `delist_candidates`, and the
        # capital freed disagreed with the snapshot's own headline. cume_dist
        # puts row k of n at k/n, so `<= share` is exactly "the worst share of
        # the population" at every value including 1.0.
        rows = snapshot._rows(
            connection,
            cte
            + """
            , ranked AS (
                SELECT v.*,
                       cume_dist() OVER (ORDER BY v.inventory_value DESC) AS worst_rank
                FROM verdict v
                WHERE v.is_delist = 1
            )
            SELECT count(DISTINCT item_key)                  AS skus_acted_on,
                   count(*)                                  AS lines_acted_on,
                   round(sum(inventory_value), 0)            AS capital_freed,
                   round(sum(weekly_gmv), 0)                 AS weekly_gmv_given_up,
                   round(sum(margin_rp), 0)                  AS weekly_margin_given_up,
                   round(sum(contribution_per_day), 0)       AS contribution_given_up
            FROM ranked
            WHERE worst_rank <= :share
            """,
            {**params, "share": share / 100.0},
        )
        kept = snapshot._rows(
            connection,
            cte
            + """
            SELECT count(DISTINCT item_key)        AS skus_kept,
                   count(*)                        AS lines_kept,
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
