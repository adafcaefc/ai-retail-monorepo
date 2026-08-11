# Inventory Risk Backend Handoff

This document is the implementation handoff for the completed frontend module
`retail.inventory_risk`. It is derived from the current frontend contract,
provider gateway, fixture provider, selector layer, and every React consumer in
`frontend/src/agents/retail/inventory_risk/`.

It is the Inventory Risk counterpart to
[`demand-forecasting-backend-handoff.md`](./demand-forecasting-backend-handoff.md)
and follows the same structure deliberately, so a backend engineer can read
both without relearning the format. Section 14 lists every place the two
modules differ on purpose — read it before assuming symmetry.

Contract terminology used below:

- **R** — required by `normalizeInventoryRiskDashboard`; the dashboard throws
  and shows an error without it.
- **P** — required for a complete populated dashboard, although the normalizer
  currently supplies an empty/default value when it is absent.
- **O** — optional metadata.
- JSON numbers must be finite JSON numbers. Do not send `NaN`, `Infinity`, or
  formatted number strings. **All money is raw IDR**, all units are raw counts;
  the frontend formats at render time in the active language.
- "Nullable" describes a valid explicit JSON `null`, not an omitted field.

The response has 15 top-level fields. Only two are validator-critical —
`schema_version` and `agent` — but a populated production dashboard must supply
the filter options, the nine KPI measures, the six breakdown arrays, the expiry
timeline, and the risk register documented below.

A complete, real example generated from the current provider is in
[`inventory-risk-api-example.json`](./inventory-risk-api-example.json)
(scope `legal_entity_id=GRC`, long arrays trimmed — see section 3).

## 1. Endpoint

```http
GET /api/html/dashboard/retail.inventory_risk
```

The frontend switches to this endpoint by changing one constant in
`frontend/src/agents/retail/inventory_risk/data/dashboardData.js`:

```js
/** @type {"fixture" | "api"} */
export const DATA_SOURCE = "fixture";   // -> "api"
```

Unlike Demand, this is a source constant rather than a Vite environment
variable, because this repository had no frontend env convention when the
module was written. Demand has since introduced
`VITE_DEMAND_FORECASTING_DATA_SOURCE`. Aligning Inventory Risk onto the same
env-var mechanism is a one-line frontend change and is listed in section 15 as
an open decision. It does not affect the backend contract either way.

API errors are surfaced to the user and never fall back to the fixture.

### Query parameters

| Parameter | Type | Allowed values / validation | Default | Required | Frontend source |
|---|---|---|---|---|---|
| `legal_entity_id` | string | `ALL` or a `filter_options.legal_entities[].value` ID | `ALL` | No | Legal Entity / Retail Vertical select, or Legal Entity chart drilldown |
| `category_group` | string | `ALL` or a `filter_options.categories[].value` ID | `ALL` | No | Category select, or Category chart drilldown |
| `store_id` | string | `ALL` or a `filter_options.stores[].value` ID | `ALL` | No | Store select — **currently disabled in the UI, see section 11** |
| `state` | string enum | `ALL`, `Stockout`, `Low`, `Expiry`, `Overstock`, `Slow-mover`, `Healthy` | `ALL` | No | State select, or At-risk-by-state chart |
| `sku` | string | SKU ID or case-insensitive item-name search text; trimmed | empty string | No | SKU search, expiry watchlist selection, or register row selection |

`serializeScope()` drops `ALL` and empty `sku` before the request is built, and
`fetchDashboard()` omits falsey values again. The default request therefore
carries **no query string at all**.

Selecting a Legal Entity resets `category_group` and `store_id` to `ALL` in the
same interaction, because the child options are scoped to the parent. The
backend will not receive a category belonging to a different entity from the UI,
but should still reject that combination if it arrives (section 12).

### Existing backend route gap

The generic FastAPI route in `backend/src/api/finance_agents_html.py` declares
only `legal_entity_id`, `period`, and `category_group`, and calls a legacy
three-argument builder positionally:

```python
build_dashboard(scoped_entity_id, scoped_period, scoped_category_group)
```

FastAPI **silently drops** `store_id`, `state`, and `sku` today — no error, no
warning, HTTP 200 with unfiltered data. The `retail.inventory_risk` descriptor
also still delegates to the shared empty Retail builder in
`src/llm/agents/retail/retail/dashboard.py`, which returns
`{"agent": "retail", "kpis": [], ...}` — a payload this module's normalizer
rejects, because `agent` does not match the canonical ID.

Backend integration must therefore extend the route/builder path to carry the
five Inventory Risk parameters and return the schema below. The public endpoint
does not need to change.

**This route is shared with Demand Forecasting, which needs eight parameters of
its own.** It must be reshaped once, by one person, for both modules — see
section 15, decision 1.

## 2. Exact Response Contract

### 2.1 Top-level metadata and scope

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `schema_version` | integer const | R | No | `1` | `normalizeInventoryRiskDashboard` | Must be exactly `1`. Any other value throws. |
| `agent` | string const | R | No | `retail.inventory_risk` | Normalizer | Must exactly match the canonical module ID. |
| `as_of` | ISO-8601 string | P | No | `2026-08-11T07:01:11+00:00` | Source label | Data snapshot time. Empty string when absent. |
| `is_mock` | boolean | P | No | `false` | Source label | `true` renders "Workbook data"/synthetic labelling; production sends `false`. |
| `note` | string | P | No | `Live D365 position as at 07:00 WIB` | Source label | Short provenance or caveat shown beside the scope row. |
| `scope` | object | P | No | `{...}` | Filter bar, scope chips | Echo of the effective normalized request. Missing keys fall back to defaults. |
| `scope.legal_entity_id` | string | P | No | `GRC` | Scope chip | Effective entity or `ALL`. |
| `scope.category_group` | string | P | No | `GRC-C01` | Scope chip | Effective category or `ALL`. |
| `scope.store_id` | string | P | No | `S001` | Scope chip | Effective store or `ALL`. |
| `scope.state` | string | P | No | `Stockout` | Scope chip | Effective state or `ALL`. |
| `scope.sku` | string | P | No | `GRC-001` | Scope chip | Effective search text, or empty. |

### 2.2 Filter options

Options must be **scope-aware**: when an entity is selected, `categories` and
`stores` must contain only that entity's rows. The frontend relies on this to
reset an invalidated child selection without a second round trip.

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `filter_options` | object | P | No | `{...}` | `InventoryRiskFilters` | Options appropriate to the current scope. |
| `filter_options.legal_entities` | array | P | No | 8 objects | Entity select | Always the full list; never filtered by scope. |
| `filter_options.legal_entities[].value` | string | P | No | `GRC` | Query ID | Stable entity ID. |
| `filter_options.legal_entities[].label` | string | P | No | `GRC · Grocery Retail (Hypermarket)` | Select option | Long display label. |
| `filter_options.legal_entities[].dashboard_label` | string | P | No | `Grocery` | Charts, reference rows | Short label used on axes and in `reference_by_vertical`. |
| `filter_options.categories` | array | P | No | 20 objects for one entity, 160 for `ALL` | Category select | Categories valid for the current entity. |
| `filter_options.categories[].value` | string | P | No | `GRC-C01` | Query ID | Stable category ID. |
| `filter_options.categories[].label` | string | P | No | `Fruit` | Select option, axis | Category name. |
| `filter_options.categories[].legal_entity_id` | string | P | No | `GRC` | Client-side reset | Owning entity. |
| `filter_options.stores` | array | P | No | 20 objects for one entity, 160 for `ALL` | Store select | Stores valid for the current entity. |
| `filter_options.stores[].value` | string | P | No | `S001` | Query ID | Stable store ID. |
| `filter_options.stores[].label` | string | P | No | `S001 · Grocery 01 · Jakarta Pusat` | Select option | Store display label. |
| `filter_options.stores[].legal_entity_id` | string | P | No | `GRC` | Client-side reset | Owning entity. |
| `filter_options.stores[].cluster` | string | P | No | `Express` | Metadata | `Flagship`, `Mall`, `Community`, or `Express`. |
| `filter_options.states` | string array | P | No | the six states | State select | Defaults to the canonical six if omitted. |

### 2.3 KPI object

**`kpis` is an object keyed by measure, not an array.** This differs from
Demand deliberately: these nine measures are fixed and never reordered, so the
frontend owns their labels, order, and formatting in `RiskKpiGrid`. The backend
sends numbers only — no labels, no units, no sparklines, no status enums.

Six are rendered as KPI cards; the remaining three are used in panel headers,
share denominators, and the empty state.

| JSON path | Type | Req. | Nullable | Rendered as | Meaning |
|---|---|---:|---:|---|---|
| `kpis` | object | P | No | — | All nine keys default to `0` when absent. |
| `kpis.stockout_risk_skus` | integer | P | No | KPI card 1 | Distinct SKUs in scope where `Position < ROP`. |
| `kpis.overstock_skus` | integer | P | No | KPI card 2 | Distinct SKUs in scope where `DoS > 15`. |
| `kpis.expiry_units` | number | P | No | KPI card 3 | Sum of units beyond shelf-life cover, in units. |
| `kpis.slow_mover_skus` | integer | P | No | KPI card 4 | Distinct SKUs where `growth < 1.0 && DoS > 10`. |
| `kpis.avg_dos` | number | P | No | KPI card 5 | Mean days of supply across scoped SKUs. |
| `kpis.inventory_value` | number | P | No | KPI card 6 | Sum of `Position × price`, raw IDR. |
| `kpis.at_risk_value` | number | P | No | Panel header, footnote | Sum of `inv_value` where `state != Healthy`. See the warning below. |
| `kpis.healthy_skus` | integer | P | No | State panel | Count where `state == Healthy`. |
| `kpis.sku_count` | integer | P | No | Register header, empty state | Rows in scope. |

> **`at_risk_value` is not an expected loss.** It is the full position value of
> every non-healthy SKU. It overstates exposure next to unit measures like
> `expiry_units`, so the UI always labels it. Do not rename it to anything that
> implies a loss estimate, and do not substitute an expected-loss figure without
> changing the label with it.

### 2.4 At-risk by state

Stacked horizontal bar, one bar per state, segmented by category.

| JSON path | Type | Req. | Nullable | Example | Meaning |
|---|---|---:|---:|---|---|
| `at_risk_by_state` | array | P | No | up to 6 objects | Ordered by the canonical severity order, not by value. States with no rows in scope must be **omitted**, not sent as zero bars. |
| `at_risk_by_state[].state` | string enum | P | No | `Stockout` | One of the six states. |
| `at_risk_by_state[].total` | number | P | No | `3520000000` | Sum of `at_risk_value` for that state. |
| `at_risk_by_state[].segments` | array | P | No | `[...]` | Category segments, **descending by value**. |
| `at_risk_by_state[].segments[].category_id` | string | P | No | `GRC-C01` | Query-compatible category ID. |
| `at_risk_by_state[].segments[].label` | string | P | No | `Fruit` | Category name. |
| `at_risk_by_state[].segments[].value` | number | P | No | `1180000000` | Segment contribution to `total`. |

Segments of one bar must sum exactly to that bar's `total`.

### 2.5 Category breakdowns

| JSON path | Type | Req. | Nullable | Example | Meaning |
|---|---|---:|---:|---|---|
| `value_by_category` | array | P | No | 20 objects | Donut of inventory-value share, **descending by value**. |
| `value_by_category[].category_id` | string | P | No | `GRC-C01` | Query-compatible ID; drilldown target. |
| `value_by_category[].label` | string | P | No | `Fruit` | Category name. |
| `value_by_category[].value` | number | P | No | `28400000000` | Sum of `inv_value` for the category. |
| `value_by_category[].share` | number | P | No | `0.184` | **Fraction in `0..1`, not a percentage.** Must be `value / sum(value)`. |
| `at_risk_by_category` | array | P | No | 20 objects | Vertical bar, **descending by value**. |
| `at_risk_by_category[].category_id` | string | P | No | `GRC-C01` | Query-compatible ID; drilldown target. |
| `at_risk_by_category[].label` | string | P | No | `Fruit` | Category name. |
| `at_risk_by_category[].value` | number | P | No | `9100000000` | Sum of `at_risk_value` for the category. |

Both arrays are regroupings of the same scoped SKU rows, so
`sum(value_by_category[].value)` must equal `kpis.inventory_value` and
`sum(at_risk_by_category[].value)` must equal `kpis.at_risk_value`.

### 2.6 Store, cluster, and legal-entity breakdowns

These three are **gross**, not chain-net. See section 8 before implementing.

| JSON path | Type | Req. | Nullable | Example | Meaning |
|---|---|---:|---:|---|---|
| `stockout_by_store` | array | P | No | 20 objects for one entity | Stacked bar, **descending by `stockout_risk_count`**. |
| `stockout_by_store[].store_id` | string | P | No | `S001` | Stable store ID. |
| `stockout_by_store[].label` | string | P | No | `Grocery 01 · Jakarta Pusat` | Store name for the axis. |
| `stockout_by_store[].cluster` | string | P | No | `Express` | Store cluster. |
| `stockout_by_store[].stockout_risk_count` | integer | P | No | `46` | SKUs below ROP at that store. |
| `stockout_by_store[].at_risk_count` | integer | P | No | `58` | SKUs in any non-healthy state. |
| `stockout_by_store[].healthy_count` | integer | P | No | `42` | Must equal `sku_count - at_risk_count`. |
| `stockout_by_store[].sku_count` | integer | P | No | `100` | SKUs carried at that store. |
| `stockout_by_store[].at_risk_value` | number | P | No | `245721700` | Gross at-risk value at that store. |
| `at_risk_by_cluster` | array | P | No | 4 objects | Vertical bar, **descending by value**. |
| `at_risk_by_cluster[].cluster` | string | P | No | `Flagship` | Cluster name. |
| `at_risk_by_cluster[].value` | number | P | No | `812000000` | Sum of member stores' `at_risk_value`. |
| `at_risk_by_cluster[].store_count` | integer | P | No | `5` | Distinct stores contributing. |
| `at_risk_by_legal_entity` | array | P | No | 1 object scoped, 8 unscoped | Vertical bar, **descending by value**. |
| `at_risk_by_legal_entity[].legal_entity_id` | string | P | No | `GRC` | Query-compatible ID; drilldown target. |
| `at_risk_by_legal_entity[].label` | string | P | No | `GRC · Grocery Retail (Hypermarket)` | Entity label. |
| `at_risk_by_legal_entity[].value` | number | P | No | `4900000000` | Sum of member stores' `at_risk_value`. |

Cluster and legal-entity totals are both rollups of the **same store rows**, so
they must equal each other:

```text
sum(at_risk_by_cluster[].value)
  = sum(at_risk_by_legal_entity[].value)
  = sum(stockout_by_store[].at_risk_value)
```

### 2.7 Expiry timeline

| JSON path | Type | Req. | Nullable | Example | Meaning |
|---|---|---:|---:|---|---|
| `expiry_timeline` | object | P | No | `{...}` | Buckets plus watchlist. Defaults to empty arrays. |
| `expiry_timeline.buckets` | array of exactly 4 | P | No | `[...]` | Shelf-life buckets, in ascending order. Send all four even when zero. |
| `expiry_timeline.buckets[].id` | string enum | P | No | `d1` | One of `d1`, `d2_3`, `d4_7`, `d8p`. |
| `expiry_timeline.buckets[].label` | string | P | No | `≤ 1 day` | Bucket label: `≤ 1 day`, `2–3 days`, `4–7 days`, `> 7 days`. |
| `expiry_timeline.buckets[].units` | number | P | No | `1840` | Units falling in that bucket. |
| `expiry_timeline.watchlist` | array of at most 4 | P | No | `[...]` | Shortest-dated SKUs first, then larger units first. |
| `expiry_timeline.watchlist[].sku_id` | string | P | No | `GRC-014` | Selecting a row sets `scope.sku`. |
| `expiry_timeline.watchlist[].name` | string | P | No | `Fruit 14` | Item name. |
| `expiry_timeline.watchlist[].shelf_life_days` | number | P | Yes | `1` | Remaining shelf-life cover in days. Primary sort key, ascending. |
| `expiry_timeline.watchlist[].units` | number | P | No | `620` | Units at expiry risk. |

Bucket assignment is by `shelf_life_days`, upper bound inclusive: `≤1` → `d1`,
`≤3` → `d2_3`, `≤7` → `d4_7`, otherwise `d8p`. Only rows with
`expiry_units > 0` participate, and `sum(buckets[].units)` must equal
`kpis.expiry_units`.

> **Do not send `null` for `shelf_life_days` on a row that has expiry units.**
> The frontend coerces a missing value to `0`, which places the row in the
> `≤ 1 day` bucket and pushes it to the top of the watchlist — a silent
> false alarm. The current provider uses the sentinel `999` for items with no
> shelf-life constraint, and those rows carry `expiry_units: 0` so they never
> reach the timeline. Either keep that convention or send a real number.

### 2.8 Risk register

The full scoped result set, sorted **severity first, then inventory value
descending**. The frontend pages it client-side at 50 rows per page and does
**not** send an offset or limit, so the backend must return the complete scoped
set. At the widest scope this is 800 rows; keep an eye on it if the real SKU
count is materially larger, and see section 15, decision 4.

| JSON path | Type | Req. | Nullable | Example | Meaning |
|---|---|---:|---:|---|---|
| `risk_register` | array | P | No | 100 objects for one entity | Every scoped SKU row. |
| `risk_register[].sku_id` | string | P | No | `GRC-001` | Stable SKU ID. |
| `risk_register[].name` | string | P | No | `Fruit 1` | Item name; also searched by `sku`. |
| `risk_register[].vertical_id` | string | P | No | `GRC` | Owning legal entity. |
| `risk_register[].category_id` | string | P | No | `GRC-C01` | Category ID. |
| `risk_register[].category_name` | string | P | No | `Fruit` | Category name. |
| `risk_register[].brand` | string | P | No | `Brava` | Brand. |
| `risk_register[].vendor` | string | P | No | `Vendor E` | Vendor. |
| `risk_register[].state` | string enum | P | No | `Low` | One of the six states. See section 7. |
| `risk_register[].severity_rank` | integer | P | No | `1` | Primary sort key; must agree with the canonical state order (see section 7). |
| `risk_register[].on_hand` | number | P | No | `1151` | Physical units on hand. |
| `risk_register[].open_po` | number | P | No | `25` | Confirmed inbound units. |
| `risk_register[].position` | number | P | No | `1176` | `on_hand + open_po`. |
| `risk_register[].rop` | number | P | No | `1491` | Reorder point. |
| `risk_register[].max` | number | P | No | `3478` | Maximum stock level. |
| `risk_register[].dos` | number | P | No | `2.3668` | Days of supply. **Send full precision**; the UI rounds. |
| `risk_register[].ads` | number | P | No | `496.869` | Average daily sales, units/day. |
| `risk_register[].price` | number | P | No | `18900` | Unit price, raw IDR. |
| `risk_register[].inv_value` | number | P | No | `22226400` | `position × price`. Secondary sort key. |
| `risk_register[].at_risk_value` | number | P | No | `22226400` | `inv_value` when not healthy, otherwise `0`. |
| `risk_register[].expiry_units` | number | P | No | `0` | Units beyond shelf-life cover. |
| `risk_register[].shelf_life_days` | number | P | Yes | `3` | Remaining cover in days. Non-perishables carry the sentinel `999`, never `null` — see the warning under section 2.7. |
| `risk_register[].is_perishable` | boolean | P | No | `true` | Drives the perishable badge. |
| `risk_register[].growth` | number | P | No | `1.1125` | Growth factor where `1.0` is flat. |
| `risk_register[].is_stockout_risk` | boolean | P | No | `true` | Pre-resolved predicate. See section 6. |
| `risk_register[].is_overstock` | boolean | P | No | `false` | Pre-resolved predicate. |
| `risk_register[].is_slow_mover` | boolean | P | No | `false` | Pre-resolved predicate. |
| `risk_register[].next_agent` | string | P | No | `3 Replenish` | Owning agent for the fix. See section 9. |

### 2.9 Reference by vertical

Per-vertical totals used to check the dashboard against the source of record.
They are **not scoped** — always send all eight verticals regardless of the
current filter, because their purpose is cross-checking, not display.

| JSON path | Type | Req. | Nullable | Example | Meaning |
|---|---|---:|---:|---|---|
| `reference_by_vertical` | array of 8 | P | No | `[...]` | One row per vertical. |
| `reference_by_vertical[].legal_entity_id` | string | P | No | `DGT` | Entity ID. |
| `reference_by_vertical[].vertical_label` | string | P | No | `Digital/Online` | Short label, matching `dashboard_label`. |
| `reference_by_vertical[].stockout_risk_skus` | integer | P | No | `40` | Source-of-record KPI. |
| `reference_by_vertical[].overstock_skus` | integer | P | No | `0` | Source-of-record KPI. |
| `reference_by_vertical[].expiry_units` | number | P | No | `0` | Source-of-record KPI. |
| `reference_by_vertical[].inventory_value` | number | P | No | `385582313300` | Source-of-record KPI. |
| `reference_by_vertical[].at_risk_value` | number | P | No | `133323852000` | Source-of-record KPI. |
| `reference_by_vertical[].avg_dos` | number | P | No | `8` | Source-of-record KPI. |

Scoping the dashboard to one vertical must reproduce that vertical's row
exactly. This is asserted by the frontend test *"scopes to one vertical and
reports that vertical's workbook numbers"*, and it is the cheapest possible
regression check on a new backend.

## 3. Full example response

[`plans/inventory-risk-api-example.json`](./inventory-risk-api-example.json) is
generated from the live provider for scope `legal_entity_id=GRC`. Long arrays
are trimmed for readability; the untrimmed cardinality at that scope is:

| Array | Trimmed to | Real length at `GRC` | Real length at `ALL` |
|---|---:|---:|---:|
| `risk_register` | 4 | 100 | 800 |
| `stockout_by_store` | 3 | 20 | 160 |
| `filter_options.categories` | 3 | 20 | 160 |
| `filter_options.stores` | 3 | 20 | 160 |
| `filter_options.legal_entities` | 3 | 8 | 8 |
| `reference_by_vertical` | 2 | 8 | 8 |
| `value_by_category` | — | 20 | 160 |
| `at_risk_by_category` | — | 20 | 160 |
| `at_risk_by_state` | — | 5 | 6 |
| `at_risk_by_cluster` | — | 4 | 4 |
| `at_risk_by_legal_entity` | — | 1 | 8 |

Use it as a shape reference for backend contract tests. Note that
`at_risk_by_state` has five entries at this scope, not six — that vertical has
no rows in one state, and empty states are omitted by design (section 2.4).

## 4. Backend source data requirements

The backend may source these semantics from D365, normalized tables, or
precomputed marts. The frontend does not require the workbook's physical
structure.

| Semantic field/domain | Business meaning | Suggested type | Grain | Source vs derived | UI dependencies | Precomputed acceptable? |
|---|---|---|---|---|---|---|
| Legal Entity / Retail Vertical | Owning company/vertical, stable ID + long and short labels | string IDs + dimension row | entity | Source master | Filter, entity chart, reference rows | Yes |
| Category | Product category ID/name under an entity | string IDs + dimension row | category | Source master | Filter, donut, category bars, state segments | Yes |
| Store | Store ID/name, owning entity, cluster, channel | string IDs + dimension row | store | Source master | Filter, store bar, cluster rollup | Yes |
| Cluster | `Flagship`, `Mall`, `Community`, `Express` | enum/string | store | Source attribute | Cluster chart | Yes |
| SKU/item | Stable SKU ID, item name, brand, vendor | strings | SKU | Source master | Search, register, watchlist | No substitute for stable IDs |
| Inventory on hand | Physical available units at as-of time | decimal units | SKU/store | Source snapshot | `on_hand`, position, all states | Yes |
| Open purchase orders | Confirmed inbound units | decimal units | SKU/store | Source transactional | `open_po`, position | Yes |
| Reorder point | Threshold covering lead time plus safety | decimal units | SKU/store | Derived or source policy | Stockout-risk predicate | Yes; otherwise send the inputs |
| Maximum stock level | Upper policy bound | decimal units | SKU/store | Source policy | Overstock context | Yes |
| Average daily sales | Recent normalized daily unit velocity | decimal units/day | SKU/store | Derived | `ads`, DoS denominator | Yes |
| Days of supply | Cover in days at current velocity | decimal days | SKU/store | Derived | `dos`, overstock and slow-mover predicates | Yes |
| Unit price | Selling or valuation price | decimal IDR | SKU | Source master | `inv_value`, all value measures | Yes |
| Growth signal | Forward vs prior demand change, `1.0` flat | decimal factor | SKU | Derived/model | Slow-mover predicate | Yes |
| Shelf life / expiry | Remaining cover in days and units beyond it | decimal days + units | SKU/store/batch | Source + derived | Expiry KPI, buckets, watchlist | Yes |
| Perishability | Whether the item is shelf-life managed | boolean | SKU | Source master | Perishable badge, expiry eligibility | Yes |
| As-of metadata | Data cutoff and provenance | timestamp + string | dashboard run | Source metadata | `as_of`, `note`, auditability | Yes |

At minimum this implies six logical source domains: organization master,
product/category master, store/cluster master, inventory position snapshots,
inbound/open-PO facts, and supply policy (ROP, max, safety, lead time).

## 5. Interim source of record

Until D365 supplies live positions, the numbers come from the workbook
`Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx` through this chain:

```text
workbook
  → scripts/extract_workbook_schema.py   → resources/dbtemp/schema_with_data.json
  → scripts/build_inventory_risk_fixture.py
  → frontend/src/agents/retail/inventory_risk/data/fixture.json
```

The relevant tables are `engine_store` (16,000 rows, SKU × store),
`sku_master` (800 rows), `stores`, `categories`, `verticals`, and the
`a2_inventory_risk` summary sheet used for reconciliation.

The pipeline is deterministic: re-running it reproduces the fixture byte for
byte apart from `generated_at`. A backend builder should preserve that
property — same inputs, same output — so a diff means a real change.

**On-hand in the workbook is pseudo-random in the SKU ID**
(`stockFactor = 0.4 + ((id*37) % 100) / 58`). That is why `is_mock` is `true`
today and why the board labels its figures rather than presenting them as a
live ERP position. Send `is_mock: false` only when the numbers are genuinely
live.

## 6. KPI calculation requirements

The frontend needs the derived values, not a mandated production algorithm.
The predicates below are the workbook's, and they must be **documented and
owned by the backend**, not re-derived in JavaScript.

| KPI | Predicate / formula | Required output | Production requirement |
|---|---|---|---|
| Stockout-risk SKUs | `Position < ROP` | Distinct scoped SKU count | Count SKUs whose position cannot cover demand within the lead/safety window. Exact policy must be documented. |
| Overstock SKUs | `DoS > 15` | Distinct scoped SKU count | Threshold is a policy decision; 15 days is the workbook's. Document whatever is chosen. |
| Expiry-risk units | Sum of units beyond shelf-life cover | Units | Must equal `sum(expiry_timeline.buckets[].units)`. |
| Slow-moving SKUs | `growth < 1.0 && DoS > 10` | Distinct scoped SKU count | Both conditions required; a slow mover is not merely overstocked. |
| Avg days of supply | Mean `dos` across scoped SKUs | Days | Unweighted mean over rows in scope. |
| Inventory value | `sum(position × price)` | Raw IDR | Must equal `sum(value_by_category[].value)`. |
| At-risk value | `sum(inv_value)` where `state != Healthy` | Raw IDR | Full position value, **not** an expected loss (section 2.3). |
| Healthy SKUs | Count where `state == Healthy` | Count | Complement of the at-risk set. |
| SKU count | Rows in scope | Count | Must equal `risk_register.length`. |

Every duplicated representation must stay consistent: KPI values, panel
headers, chart totals, and register sums must derive from the same scoped rows.

## 7. State classification requirements

Each register row carries exactly one `state` and a matching `severity_rank`.
The rank is the register's primary sort key and must agree with this order:

| `severity_rank` | `state` | Counts as at risk? |
|---:|---|---|
| 0 | `Stockout` | Yes |
| 1 | `Low` | Yes |
| 2 | `Expiry` | Yes |
| 3 | `Overstock` | Yes |
| 4 | `Slow-mover` | Yes |
| 5 | `Healthy` | No |

Anything that is not `Healthy` counts as at risk. The state is resolved
**once, in the backend**, and delivered alongside the three `is_*` booleans.
The frontend only counts flags and sums columns.

> A threshold implemented in both the backend and the frontend is two
> definitions of one rule, and the JavaScript copy is the one nobody notices
> drifting. Keep every predicate on the backend side of this contract.

## 8. Gross versus net reconciliation rules

This is the single most important semantic in this contract, and the one most
likely to be reported as a bug.

**`kpis` are chain-net.** A surplus at one store nets off a shortage at
another, so the headline describes the chain as one pool.

**`stockout_by_store` and `at_risk_by_cluster` are gross.** They sum local
pockets of risk and will therefore total **higher** than the headline.

```text
sum(stockout_by_store[].at_risk_value)   >=   kpis.at_risk_value
sum(at_risk_by_cluster[].value)          >=   kpis.at_risk_value
```

That gap is intentional and must not be reconciled away. The UI already carries
a footnote saying so. What must reconcile exactly:

```text
sum(value_by_category[].value)            = kpis.inventory_value
sum(at_risk_by_category[].value)          = kpis.at_risk_value
sum(at_risk_by_state[].total)             = kpis.at_risk_value
sum(at_risk_by_state[].segments[].value)  = at_risk_by_state[].total   (per bar)
sum(expiry_timeline.buckets[].units)      = kpis.expiry_units
risk_register.length                      = kpis.sku_count
sum(at_risk_by_cluster[].value)           = sum(at_risk_by_legal_entity[].value)
                                          = sum(stockout_by_store[].at_risk_value)
value_by_category[].share                 = value / sum(value), in 0..1
```

`value_by_category[].share` additionally sums to `1` across the array.

Use a deterministic rounding method so displayed integers reconcile exactly.

Every equality above was machine-checked against the current provider at four
scopes — unfiltered, one entity, one state, and an entity/state combination
that matches zero rows — and all of them hold, including the empty case. They
are therefore requirements a backend must meet, not aspirations. A backend
contract test asserting the same list is the cheapest way to keep them true.

## 9. Next-agent routing

Each register row names the agent that owns the fix:

| `state` | `next_agent` |
|---|---|
| `Stockout`, `Low` | `3 Replenish` |
| everything else | `5 Markdown` |

This is display-only today — the frontend renders it as a label and the control
is disabled. It is not a workflow trigger, and no routing action is invoked.

## 10. Search semantics

`sku` is a single field matching **either** the SKU ID **or** the item name,
case-insensitively, as a substring. `GRC-0` and `fruit` are both valid queries.
The frontend applies no client-side filtering in API mode, so the backend owns
the match. Keep it a substring match, not a prefix or exact match, or the
search box will appear to break.

## 11. Store scope — the one deliberate gap

`scope.store_id` is accepted, echoed, and part of the contract, but the store
select is **disabled in the UI today** with the tooltip *"Store scope needs the
per-store dataset, not yet available."*

The reason is delivery, not availability. `fixture.items` is chain-net — one
row per SKU across the whole chain, with no store dimension. Scoping the
register to one store needs the 16,000-row SKU × store grid, roughly 163 KB
gzipped on top of the current fixture, shipped to every browser for interim
data.

**A backend builder removes this constraint entirely.** It can query the grid
server-side and return only the scoped slice. When the API honours `store_id`:

1. Set `SUPPORTS_STORE_SCOPE = true` in
   `frontend/src/agents/retail/inventory_risk/data/selectors.js`.
2. The select enables itself; no contract change, no component change.

The store and cluster charts are unaffected either way — they already read
pre-aggregated per-store rows.

## 12. Error contract

The shared frontend client reads JSON error fields in this order: `detail`,
then `error`; otherwise it displays `Dashboard request failed (<status>)`.

| Condition | Expected HTTP/result | Repository convention and frontend behaviour |
|---|---|---|
| Invalid type/range | `422` with `{"detail":"..."}` | Visible dashboard error; no fixture fallback. |
| Unknown filter value or inconsistent hierarchy | `400` with `{"detail":"..."}` | The dashboard route maps builder `ValueError` to 400. Examples: store not in the selected entity, category from another entity, `state` outside the six. |
| Unknown agent | `404` with `{"detail":"..."}` | Registry lookup failure. |
| Source unavailable | `503` with `{"detail":"Dashboard data unavailable: ..."}` | Do not return fabricated zeros as live data. |
| Malformed response | Prevent with backend contract tests | If HTTP 200 reaches the frontend, `normalizeInventoryRiskDashboard` throws a visible error. Wrong `schema_version` or wrong `agent` fail immediately. |
| No matching data | `200` with a valid empty-state payload | Empty arrays and zero KPIs are acceptable. `filter_options` must still be populated so the user can widen the scope, and `reference_by_vertical` must still contain all eight rows. |

Do not expose confidential source exception text in 503 details; keep the
operator-facing detail in logs.

## 13. Calculation ownership

| Concern | Backend | Frontend |
|---|---|---|
| Data retrieval | Owns | None |
| Source authorization and scoping | Owns | Sends query only |
| State classification | Owns | Renders badge |
| KPI predicates and thresholds | Owns | Counts pre-resolved flags |
| Category/store/cluster/entity aggregation | Owns | Renders and drills down |
| Gross vs net semantics | Owns | Labels the difference |
| Expiry bucketing and watchlist ranking | Owns | Renders |
| Register sorting (severity, then value) | Owns | Pages at 50 rows |
| Next-agent routing | Owns | Displays label |
| Search matching | Owns in API mode | Owns input state |
| Raw numeric response | Owns | Must receive finite numbers |
| Number/currency/localization formatting | None | Owns |
| Chart rendering, tooltips, colours | None | Owns |
| Responsive layout | None | Owns |
| Filter control state and dependent resets | Returns scoped options | Owns interaction |
| Loading/error/retry UI | Returns HTTP status/detail | Owns |
| Transactional actions, chat, ERP | Out of scope | Disabled |

## 14. Where this differs from the Demand handoff

Both modules share one route and one client, but their contracts differ on
purpose. Do not port an assumption from one to the other.

| Concern | Demand Forecasting | Inventory Risk |
|---|---|---|
| `schema_version` | `2` | `1` |
| Source switch | `VITE_DEMAND_FORECASTING_DATA_SOURCE=api` | `DATA_SOURCE` constant in `dashboardData.js` |
| Query parameters | 8 | 5 |
| `kpis` shape | **Array** of objects with labels, units, sparklines | **Object** keyed by measure; numbers only |
| Server-side paging | `detail_offset` / `detail_limit`, max 100 rows | None; full scoped set, paged client-side at 50 |
| Time dimension | Central — grain, horizon, series, confidence | None |
| Gross vs net | Not applicable; all dimensions reconcile exactly | Store and cluster are gross and exceed the headline by design |
| Simulation / What-If | In contract | Not in contract |
| Suggested actions | In contract | Not in contract; `next_agent` is a display label only |
| Interim data | Invented in JavaScript | Workbook-derived and reconciled |

Two fields carry the same name in both contracts and **must agree** at the same
scope, because a user can compare them by switching boards:

- `stockout_risk_skus` — present in both `a1_demand_forecasting` and
  `a2_inventory_risk` in the workbook, with identical values across all eight
  verticals (46, 31, 39, 42, 35, 32, 40, 37).
- Dimension IDs — `legal_entity_id`, `category_group`, `store_id` must use the
  same code space in both modules.

## 15. Backend implementation checklist

- [ ] Keep `GET /api/html/dashboard/retail.inventory_risk` as the public endpoint.
- [ ] Accept and validate all five Inventory Risk query parameters.
- [ ] Extend the shared route/builder signature so `store_id`, `state`, and `sku` are no longer silently dropped — once, for both Retail modules.
- [ ] Split `src/llm/agents/retail/retail/dashboard.py` so each descriptor has its own builder before filling either in.
- [ ] Return `schema_version: 1` and `agent: "retail.inventory_risk"` exactly.
- [ ] Populate all nine KPI measures as raw finite numbers.
- [ ] Resolve `state`, `severity_rank`, and the three `is_*` booleans server-side.
- [ ] Return scope-aware `filter_options`, with categories and stores narrowed to the selected entity.
- [ ] Omit states with no rows from `at_risk_by_state` rather than sending zero bars.
- [ ] Sort every array as documented: severity then value for the register, descending value elsewhere, canonical order for states and expiry buckets.
- [ ] Return all four expiry buckets even when zero, and at most four watchlist rows.
- [ ] Return the complete scoped `risk_register`; the frontend pages it.
- [ ] Return all eight `reference_by_vertical` rows regardless of scope.
- [ ] Verify every equality in section 8, and verify the gross breakdowns are allowed to exceed the headline.
- [ ] Reproduce each vertical's `reference_by_vertical` row exactly when scoped to that vertical.
- [ ] Keep `share` a fraction in `0..1`, not a percentage.
- [ ] Send `dos` at full precision; let the UI round.
- [ ] Send `is_mock: false` and a truthful `note` only when the data is genuinely live.
- [ ] Honour `store_id`, then flip `SUPPORTS_STORE_SCOPE` to `true` in the frontend.
- [ ] Add backend contract tests using `plans/inventory-risk-api-example.json` as a shape reference.
- [ ] Confirm the response passes `normalizeInventoryRiskDashboard(payload)`.
- [ ] Return 400/404/422/503 using the repository JSON `detail` convention.
- [ ] Confirm API errors do not fall back to the fixture.
- [ ] Verify `DATA_SOURCE = "api"` works without any React component change.
- [ ] Keep `dashboard_only=True`; do not enable chat, actions, monitoring, approval, ERP, or LLM behaviour.

## Unresolved backend design decisions

1. **Whether the shared dashboard route is extended positionally or reshaped to
   pass a scope object.** This blocks both Retail modules and must be decided
   once. The recommendation on the frontend side is a single scope object —
   `build_dashboard(scope: dict)` — with each agent reading the keys it
   understands, because both frontends already send an arbitrary key/value
   query and only the backend signature is fixed at three positional slots.
2. Physical source systems and ownership for inventory positions, open POs, and
   supply policy, and whether D365 is queried live or through a mart.
3. Production thresholds and policy for stockout risk, overstock, and slow
   movers. The workbook's `ROP`, `DoS > 15`, and `growth < 1.0 && DoS > 10` are
   demonstration values, not approved policy.
4. Whether the register stays a complete scoped set or gains server-side paging.
   800 rows is comfortable; a real catalogue may not be. Adding
   `detail_offset` / `detail_limit` later mirrors Demand and is a contract
   change, so decide before the first release rather than after.
5. Whether `at_risk_value` remains full position value or is replaced by an
   expected-loss measure. If it changes, the label and the footnote must change
   with it.
6. Whether Inventory Risk adopts a `VITE_INVENTORY_RISK_DATA_SOURCE` env
   variable for parity with Demand, or both modules move to a single shared
   flag.
7. Expiry semantics against real batch data. The workbook models shelf life per
   SKU; a real system tracks it per batch, which may change how
   `shelf_life_days` and `expiry_units` are derived.
