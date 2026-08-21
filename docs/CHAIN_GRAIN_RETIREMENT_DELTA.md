# Retiring the chain-net table: what the numbers did

Date: 2026-08-21. Companion to
[A2_ENGINE_STORE_GRAIN.md](./A2_ENGINE_STORE_GRAIN.md), which recorded Agent 2
making this move alone. This file records the other five agents following it,
and answers the question that was asked before any code changed: **if every
board reads one table, which numbers move and by how much.**

Every figure below is measured, not estimated. Reproduce them with:

```
cd backend
../.venv/Scripts/python.exe ../scripts/measure_chain_migration_delta.py
```

That script is read-only and still runs — the chain table was deliberately left
in the database, still seeded by `build_inventory_chain()` and still fresh. It
is a standing reconciliation between the two grains, not a one-shot report.

## The problem

Two tables, two loads of the same workbook, two answers:

| Table | Sheet | Rows | What one row is |
|---|---|---|---|
| `fact_inventory_chain_daily` | `ENGINE` | 800 | one SKU, netted across its stores |
| `fact_inventory_daily` | `ENGINE_STORE` | 16,000 | one SKU **at one store** |

They are not derivable from each other, and
[seed_retail_facts_from_json.py](../scripts/seed_retail_facts_from_json.py) says
why: each store row rounds independently, so twenty rounded values summed drift
from one value rounded once (up to 4.5% on `rop`), and `state` is computed on
chain-level inputs rather than voted across stores.

So "SKUs to reorder" was **345** or **524** depending on which table the author
of a given board happened to query. Both were defensible; having both was not.

## What changed

Application code now reads `fact_inventory_daily` only. Chain grain was dropped
outright rather than rebuilt behind a view, because a view would have preserved
the ambiguity under a new name.

**The database was not touched.** No migration, no `DROP`, no `ALTER`, no edit
to `retail.formula` or `retail.agent_kpi_reference`. The chain table is still
there and still loaded; nothing reads it. Rollback is `git revert`.

## The shape of the answer

> **Money is flat. Counts go up.**

Anything linear in `ads` sums exactly across stores, so it lands unchanged.
What moves is every *count*, because a SKU that nets out healthy chain-wide can
be broken in six of its twenty stores — and `at_risk_value`, which is gated on
`state` and therefore inherits the count behaviour.

### Flat, as predicted

| Metric | Chain | Store | Ratio |
|---|---|---|---|
| `ads_total` | 242,838.55 | 242,838.55 | 1.000000 |
| `forecast_7d` | 1,809,147.22 | 1,809,147.22 | 1.000000 |
| `weekly_gmv` | 1,964,802,647,353.00 | 1,964,802,647,353.01 | 1.000000 |
| `margin_rp` | 485,800,885,016.76 | 485,800,885,016.76 | 1.000000 |
| `funding_rp` | 817,917,796,038.14 | 817,917,796,038.14 | 1.000000 |
| `inventory_value` | 2,223,726,280,600 | 2,223,869,209,600 | 1.000064 |
| `sku_count` | 800 | 800 | 1.000000 |

`funding_rp` reproducing to the cent is the load-bearing result here. It is
derived at store grain as `ads × 7 × price × dim_item.funding_pct`, and the
exactness confirms that `dim_item` is the right source. **ENGINE_STORE's own
`fund` column is rounded to 3 decimals and reconstructs `funding_rp` wrongly on
723 of 800 SKUs** — the reason the loader was left alone rather than extended to
pull it in. Same argument retired `margin`, `price` and `expiry`.

### Moved

| Metric | Chain | Store | Ratio |
|---|---|---|---|
| `skus_to_reorder` | 345 | **524** (7,090 rows) | 1.519 |
| `stockout_skus` | 130 | 247 | 1.900 |
| `overstock_skus` | 26 | 104 | 4.000 |
| `slow_mover_skus` | 37 | 75 | 2.027 |
| `expiry_skus` | 9 | 12 | 1.333 |
| `at_risk_value` | 739,163,141,900 | 873,041,521,900 | 1.181 |
| `order_value` | 735,273,193,800 | 765,815,946,400 | 1.042 |
| `order_units` | 700,120 | 731,191 | 1.044 |
| `expiry_units` | 5,562 | 5,787 | 1.040 |

Independently corroborated: `at_risk_value`, `inventory_value`, `524`/`7,090`,
`104` and `75` match the figures
[A2_ENGINE_STORE_GRAIN.md](./A2_ENGINE_STORE_GRAIN.md) derived from the workbook
by hand, months earlier and by a different route.

**`expiry_skus` 9 → 12 is not the A2 doc's 8 → 11.** Different definition, not a
contradiction: this row counts SKUs with `f22` expiry units above zero, while
the board counts SKUs *labelled* Expiry by `f07`, whose branches are priority-
ordered — a SKU can carry expiry units and still be labelled Stockout.

### Not uniformly upward

`overstock_skus` at ×4.0 is the largest mover, driven by ELC at ×14.0 (1 → 14).

Two verticals moved **down**, which is worth stating because "counts go up" is
otherwise easy to over-generalise into an assumption:

| Metric | Vertical | Chain | Store | Ratio |
|---|---|---|---|---|
| `order_value` | HNL | 50,864,636,700 | 48,242,665,200 | 0.948 |
| `order_units` | HNL | 17,670 | 17,401 | 0.985 |

Order quantities are `max(0, Max − Position)` per row. Netting across stores
lets one store's surplus cancel another's shortfall in both directions, so the
per-store total can land either side of the chain figure. It usually lands
above; in HNL it does not.

## What this deliberately broke

**The workbook's chain-net summary sheets no longer match the boards.** They are
still carried as `reference_by_vertical` and still asserted — as a benchmark
from the other grain, not a target. This is the same trade
[A2_ENGINE_STORE_GRAIN.md](./A2_ENGINE_STORE_GRAIN.md) recorded; it now applies
chain-wide.

`retail.agent_kpi_reference` was left holding the workbook's chain figures. It
is transcribed from the A-sheets rather than computed, and it is passed through
`replace_all` on every seed — so re-baselining it by `UPDATE` would not have
survived the next run, and computing it from the fact tables would have made it
reconcile with itself and check nothing.

**Ad-hoc access to the chain table was withdrawn.** The table still exists, so
removing it from the six allowlists in
[freeform_query.py](../backend/src/llm/agents/common/tools/freeform_query.py) is
a policy block rather than a consequence: an agent able to query it ad-hoc is
exactly how a second answer walks back into the conversation after the boards
have agreed on one.

## The trap, restated

Counts are **distinct SKUs**; money sums **rows**. `count(*)` where
`count(DISTINCT item_key)` was meant is wrong by roughly 20× and looks entirely
plausible — 7,090 below-ROP rows against 524 below-ROP SKUs.

The subtlest instance is in
[demand_data.py](../backend/src/llm/agents/retail/demand_forecasting/tools/demand_data.py):
`viral_skus` and `growing_skus` filter on `dim_item` attributes, which are
replicated across all twenty of a SKU's rows. Counted with `DISTINCT` they are
flat; counted without, they are ×20 and wrong in a way no reconciliation would
catch, because both grains would agree the SKU qualifies.
