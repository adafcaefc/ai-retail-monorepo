# Demand Forecasting Backend Handoff

This document is the implementation handoff for the completed frontend module
`retail.demand_forecasting`. It is derived from the current frontend contract,
provider gateway, mock provider, calculation layer, and every React consumer in
`frontend/src/agents/retail/demand_forecasting/`.

Contract terminology used below:

- **R** — required by the current API-mode validator or by the normalizer to
  render at all.
- **P** — required for a complete populated dashboard, although the normalizer
  currently supplies an empty/default value when it is absent.
- **O** — optional metadata or intentionally unused in the current phase.
- JSON numbers must be finite JSON numbers. Do not send `NaN`, `Infinity`, or
  formatted number strings.
- “Nullable” describes a valid explicit JSON `null`, not an omitted field.

The response has 16 top-level fields. Six roots are validator-critical:
`schema_version`, `agent`, `forecast`, `dimensions`, `simulation`, and
`suggested_actions`. A production-quality populated response must also supply
the filter options, six KPIs, confidence panel, trending items, and detail
section documented below.

## 1. Endpoint

```http
GET /api/html/dashboard/retail.demand_forecasting
```

The frontend switches to this endpoint when:

```dotenv
VITE_DEMAND_FORECASTING_DATA_SOURCE=api
```

When the variable is missing or has any value other than `api`, the frontend
uses mock mode. API errors are surfaced to the user and never fall back to the
mock provider.

### Query parameters

| Parameter | Type | Allowed values / validation | Default | Required | Frontend source |
|---|---|---|---|---|---|
| `legal_entity_id` | string | `ALL` or a `filter_options.legal_entities[].value` ID | `ALL` | No | Legal Entity / Retail Vertical select |
| `category_group` | string | `ALL` or a `filter_options.categories[].value` ID | `ALL` | No | Category select or Category chart drilldown |
| `store_id` | string | `ALL` or a `filter_options.stores[].value` ID | `ALL` | No | Store select or Store chart drilldown |
| `sku` | string | SKU ID or case-insensitive item search text; trimmed, maximum 120 characters | empty string | No | SKU search, trend selection, or Detail-row selection |
| `grain` | string enum | `daily`, `weekly`, `monthly`, `quarterly`, `yearly` | `weekly` | No | Forecast overview period selector |
| `horizon_weeks` | integer enum | `4`, `8`, `12`, `16` | `8` | No | Horizon segmented control |
| `detail_offset` | integer | `0..1,000,000` | `0` | No | Normalized query contract; no visible pager yet |
| `detail_limit` | integer | `1..100` | `100` | No | Normalized query contract; frontend caps rows at 100 |

`fetchDashboard()` omits falsey values and the literal `ALL` from the URL.
Consequently the normal default request includes `grain=weekly`,
`horizon_weeks=8`, and `detail_limit=100`, but omits the three `ALL` filters,
empty `sku`, and zero `detail_offset`.

### Existing backend route gap

The current generic FastAPI route in `backend/src/api/finance_agents_html.py`
declares only `legal_entity_id`, `period`, and `category_group`, and calls the
legacy three-argument dashboard builder. FastAPI ignores the extra Demand
query parameters today. The Demand descriptor also still delegates to the
legacy generic Retail builder. Backend integration therefore must extend the
existing route/builder path to accept the eight Demand parameters and return
this schema-v2 payload. The public endpoint above does not need to change.

## 2. Exact Response Contract

### 2.1 Top-level metadata and scope

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `schema_version` | integer | R | No | `2` | `validateDemandDashboardV2` | Must be `2` or newer in API mode. |
| `agent` | string const | R | No | `retail.demand_forecasting` | `normalizeDemandDashboard` | Must exactly match the canonical module ID. |
| `as_of` | ISO-8601 string | O | No | `2026-08-06T03:00:00Z` | Normalized only | Data/model snapshot time. |
| `is_mock` | boolean | O | No | `false` | `DemandForecastingDashboard` | Controls “Synthetic data” vs “Live data”. Production should send `false`. |
| `note` | string | O | No | `Forecast run 2026-08-06 03:00 UTC` | `DemandForecastingDashboard` | Short provenance or caveat displayed beside scope. |
| `scope` | object | P | No | `{...}` | Normalizer; local scenario context | Echo of the effective normalized request. |
| `scope.legal_entity_id` | string | P | No | `GRC` | Scenario context | Effective entity or `ALL`. |
| `scope.category_group` | string | P | No | `GRC-C01` | Scenario context | Effective category or `ALL`. |
| `scope.store_id` | string | P | No | `GRC-S1` | Scenario context | Effective store or `ALL`. |
| `scope.sku` | string | P | No | `GRC-001` | Scenario context | Effective SKU/search text. |
| `scope.grain` | grain enum | P | No | `weekly` | Overview and scenario context | Effective presentation grain. |
| `scope.horizon_weeks` | integer | P | No | `4` | Scenario context | Effective horizon. |
| `scope.detail_offset` | integer | P | No | `0` | Normalized Detail metadata | Effective result offset. |
| `scope.detail_limit` | integer | P | No | `100` | Normalized Detail metadata | Effective row limit, maximum 100. |

### 2.2 Filter options

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `filter_options` | object | P | No | `{...}` | Dashboard | Options appropriate to the current scope. |
| `filter_options.legal_entities` | array | P | No | `[{"value":"GRC","label":"GRC · Grocery Retail"}]` | `DemandForecastFilters` | All selectable Legal Entities / Retail Verticals. |
| `filter_options.legal_entities[].value` | string | P | No | `GRC` | Legal Entity select | Stable query ID. |
| `filter_options.legal_entities[].label` | string | P | No | `GRC · Grocery Retail` | Legal Entity select/scope chip | Display label. |
| `filter_options.categories` | array | P | No | `[{"value":"GRC-C01","label":"Fresh Produce"}]` | `DemandForecastFilters` | Categories valid for the selected entity. |
| `filter_options.categories[].value` | string | P | No | `GRC-C01` | Category select | Stable category query ID. |
| `filter_options.categories[].label` | string | P | No | `Fresh Produce` | Category select/scope chip | Display label. |
| `filter_options.stores` | array | P | No | `[{"value":"GRC-S1","label":"GRC Jakarta 1"}]` | `DemandForecastFilters` | Stores valid for the selected entity. |
| `filter_options.stores[].value` | string | P | No | `GRC-S1` | Store select | Stable store query ID. |
| `filter_options.stores[].label` | string | P | No | `GRC Jakarta 1` | Store select/scope chip | Display label. |
| `filter_options.grains` | grain-enum array | P | No | `["daily","weekly","monthly","quarterly","yearly"]` | `ForecastOverviewPanel` | Enabled period buttons. Omission defaults to all five. |
| `filter_options.horizons_weeks` | integer array | P | No | `[4,8,12,16]` | `DemandForecastFilters` | Enabled horizon buttons. Omission defaults to all four. |

### 2.3 KPI array

`kpis` should contain exactly the six IDs in section 5. The validator currently
defaults a missing array to empty, but a populated production dashboard must
provide all six.

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `kpis` | array | P | No | six objects | `DemandKpiGrid` | Ordered KPI cards. |
| `kpis[].id` | string enum | P | No | `forecast_next_7d` | KPI formatting | Stable semantic ID. |
| `kpis[].label` | string | P | No | `Forecast (next 7d)` | `DemandKpiGrid` | Visible title. |
| `kpis[].value` | number | P | No | `3995` | `DemandKpiGrid` | Raw numeric value. |
| `kpis[].unit` | string | P | Yes | `units`, `%`, `SKUs`, `index` | `DemandKpiGrid` | Formatting suffix/label; `null` means no unit. |
| `kpis[].comparison_label` | string | P | No | `AI demand signal` | `DemandKpiGrid` | Small explanatory caption. |
| `kpis[].direction` | enum | P | No | `up` | Normalizer | `up`, `down`, or `flat`; invalid values become `flat`. |
| `kpis[].status` | enum | P | No | `good` | KPI accent | `good`, `warn`, `bad`, or `neutral`. |
| `kpis[].sparkline` | number array | P | No | `[3635,3755,3715,3875,3995]` | KPI sparkline | Ordered raw trend points; two or more points render a sparkline. |

### 2.4 Forecast-series schema

The following reusable series shape occurs at these exact prefixes:

- `forecast` — overview chart and four summary metrics; `points` is R and must
  be non-empty.
- `confidence` — separate confidence panel; if omitted, the normalizer reuses
  `forecast`, but production should send it explicitly.
- `simulation.baseline_forecast` — R with non-empty points; current baseline
  for Compare Scenarios.
- `scenarios[].baseline_forecast` and `scenarios[].forecast` — optional and
  normalized, but server scenarios are not consumed in this phase.

For every prefix `<series>` above:

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `<series>.grain` | grain enum | P | No | `weekly` | Overview / context | Period represented by each point. |
| `<series>.history_count` | integer | P | No | `12` | Series metadata | Count of historical points. |
| `<series>.horizon_weeks` | integer | P | No | `4` | Confidence badge/context | Forecast horizon represented. |
| `<series>.horizon_label` | string | P | No | `4-week AI forecast` | Panel header | Human-readable series description. |
| `<series>.points` | array | R for `forecast` and simulation baseline | No | `[...]` | `ForecastLineChart`, comparison | Ordered history, transition, and forecast. |
| `<series>.points[].key` | string | P | No | `W+1` | Forecast-boundary lookup | Unique stable point key. |
| `<series>.points[].label` | string | P | No | `W+1` | X axis/tooltip | User-visible period label. |
| `<series>.points[].actual` | number | P | Yes | `4055` | Actual line/tooltip | Historical observation. `null` on forecast-only points. |
| `<series>.points[].forecast` | number | P | Yes | `4075` | Forecast line/comparison | Future prediction. `null` on historical-only points. |
| `<series>.points[].confidence_low` | number | P | Yes | `3586` | Confidence area/tooltip | Lower bound. `null` where no forecast interval exists. |
| `<series>.points[].confidence_high` | number | P | Yes | `4564` | Confidence area/tooltip | Upper bound. `null` where no forecast interval exists. |
| `<series>.summary` | array | O/P | No | `[...]` | Overview only | Summary strip; normally empty for other series. |
| `<series>.summary[].id` | string | P for overview | No | `next_7d` | Overview formatting | Stable summary ID. |
| `<series>.summary[].label` | string | P for overview | No | `NEXT 7D` | Overview summary | Display label. |
| `<series>.summary[].value` | number or string | P for overview | Yes | `3995` or `Saturday ×1.35` | Overview summary | Raw value; strings support nonnumeric Peak text. |
| `<series>.summary[].unit` | string | P for overview | Yes | `units` | Overview summary | Display unit; `null` for Peak text. |

`forecast.summary` is expected to contain `next_7d`, `accuracy`, `trend`, and
`peak` in that order.

### 2.5 Dimensions

All five dimension arrays and `chain_total` are mandatory in API mode. Empty
dimension arrays are allowed for a no-match scope, but `seasonality` must still
contain exactly 12 points and identify a current month.

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `dimensions` | object | R | No | `{...}` | `DemandDimensionPanels` | Seven-day dimension package. |
| `dimensions.categories` | array | R | No | `[...]` | Category chart/buttons | Category seven-day totals. |
| `dimensions.categories[].id` | string | P | No | `GRC-C01` | Category drilldown | Query-compatible category ID. |
| `dimensions.categories[].label` | string | P | No | `Fresh Produce` | Axis/tooltip/button | Category name. |
| `dimensions.categories[].forecast_units` | number | P | No | `3995` | Category bar | Seven-day forecast units. |
| `dimensions.categories[].share_pct` | number | P | No | `100` | Tooltip | Share of current `chain_total`. |
| `dimensions.stores` | array | R | No | `[...]` | Store ranking/buttons | Store seven-day totals, highest first. |
| `dimensions.stores[].id` | string | P | No | `GRC-S1` | Store drilldown | Query-compatible store ID. |
| `dimensions.stores[].label` | string | P | No | `GRC Jakarta 1` | Axis/tooltip/button | Store name. |
| `dimensions.stores[].forecast_units` | number | P | No | `3995` | Store bar | Seven-day forecast units. |
| `dimensions.stores[].share_pct` | number | P | No | `100` | Tooltip | Share of current total. |
| `dimensions.stores[].legal_entity_id` | string | P | No | `GRC` | Normalized metadata | Store owner Legal Entity. |
| `dimensions.stores[].cluster` | string | P | No | `Flagship` | Store tooltip | Store cluster. |
| `dimensions.clusters` | array | R | No | four objects | Cluster chart | Cluster seven-day totals. Prefer all four known clusters, including zero rows. |
| `dimensions.clusters[].id` | string | P | No | `Flagship` | Bar identity | Stable cluster ID. |
| `dimensions.clusters[].label` | string | P | No | `Flagship` | Axis/tooltip | Cluster label. |
| `dimensions.clusters[].forecast_units` | number | P | No | `3995` | Cluster bar | Sum of underlying store forecast. |
| `dimensions.clusters[].share_pct` | number | P | No | `100` | Tooltip | Share of current total. |
| `dimensions.clusters[].store_count` | integer | P | No | `1` | Tooltip | Distinct stores contributing. |
| `dimensions.legal_entities` | array | R | No | `[...]` | Legal Entity chart/summary | Store-to-entity rollup. |
| `dimensions.legal_entities[].id` | string | P | No | `GRC` | Entity drilldown/summary | Query-compatible Legal Entity ID. |
| `dimensions.legal_entities[].label` | string | P | No | `GRC · Grocery Retail` | Axis/tooltip | Legal Entity / vertical name. |
| `dimensions.legal_entities[].forecast_units` | number | P | No | `3995` | Entity bar/summary | Sum of entity stores on seven-day basis. |
| `dimensions.legal_entities[].share_pct` | number | P | No | `100` | Summary/tooltip | Share of Chain Total. |
| `dimensions.legal_entities[].store_count` | integer | P | No | `1` | Summary/tooltip | Distinct contributing stores. |
| `dimensions.seasonality` | array of exactly 12 | R | No | `[...]` | Seasonality chart | January through December curve. |
| `dimensions.seasonality[].month` | string | P | No | `Jul` | Axis/tooltip | Month label. |
| `dimensions.seasonality[].index` | number | R | No | `114` | Bar/KPI source | Seasonal index, where 100 is average. |
| `dimensions.seasonality[].current` | boolean | R collectively | No | `true` | Bar highlight | Exactly one point should identify the current/reference month. |
| `dimensions.chain_total` | number | R | No | `3995` | Chain summary/reconciliation | Scoped seven-day forecast total. |

### 2.6 Predicted-to-trend items

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `trending_items` | array | P | No | `[...]` | `PredictedTrendPanel` | Ranked representative trending items; may be empty legitimately. |
| `trending_items[].sku_id` | string | P | No | `GRC-001` | Selection/key | SKU query ID. |
| `trending_items[].sku_name` | string | P | No | `Everyday Essential 001` | Axis/list/tooltip | Item name. |
| `trending_items[].predicted_uplift_pct` | number | P | No | `47.5` | Bar/list/tooltip | Expected demand uplift percentage. |
| `trending_items[].signals` | string array | P | No | `["viral","growth"]` | Tooltip/list | Signal context such as viral, growth, seasonal, or promo. |
| `trending_items[].ads_units_per_day` | number | P | No | `536.3` | Tooltip | Average daily sales/demand units. |

### 2.7 Forecast Detail

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `details` | object | P | No | `{...}` | `ForecastDetailTable` | Selected-period result window. |
| `details.total` | integer | P | No | `1` | Detail header | Total matching rows before limit/offset. |
| `details.offset` | integer | P | No | `0` | Normalized metadata | Returned window start. |
| `details.limit` | integer `1..100` | P | No | `100` | Normalized metadata | Requested/returned maximum. |
| `details.forecast_total_units` | number | P | No | `3995` | Reconciliation/tests | Full scoped selected-period total, not merely displayed rows. |
| `details.rows` | array, max 100 consumed | P | No | `[...]` | `ForecastDetailTable` | Rows sorted by `forecast_units` descending. |
| `details.rows[].sku_id` | string | P | No | `GRC-001` | Row key/drilldown | SKU ID. |
| `details.rows[].sku_name` | string | P | No | `Everyday Essential 001` | Row label | Item name. |
| `details.rows[].category_id` | string | P | No | `GRC-C01` | Normalized identity | Category query ID. |
| `details.rows[].category_label` | string | P | No | `Fresh Produce` | Detail table | Category name. |
| `details.rows[].ads_units_per_day` | number | P | No | `536.3` | Detail table | Average daily sales/demand. |
| `details.rows[].forecast_7d_units` | number | P | No | `3995` | Normalized seven-day measure | Explicit seven-day SKU forecast, independent of selected Detail grain. |
| `details.rows[].forecast_units` | number | P | No | `3995` | Detail table | Forecast for `scope.grain`: one day/week/month/quarter/year. |
| `details.rows[].trend_pct` | number | P | No | `29.5` | Detail table | SKU trend/uplift percentage. |
| `details.rows[].signals` | string array | P | No | `["viral"]` | Detail table | Demand signal tags. |
| `details.rows[].supply_state` | string | P | No | `Low` | Detail badge | Current supply classification; current CSS expects `Healthy`, `Low`, or `Stockout`. |

### 2.8 Simulation metadata

The dashboard response must include simulation metadata even though execution
is currently mock-only. This renders the levers and Baseline vs Scenario card.

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `simulation` | object | R | No | `{...}` | `DemandWhatIfSimulator` | Current baseline/scenario metadata. |
| `simulation.applied` | boolean | O | No | `false` | Normalized only | Whether returned metrics are scenario-adjusted. |
| `simulation.levers` | array containing six IDs | R | No | `[...]` | Simulator sliders/banner | Lever definitions. |
| `simulation.levers[].id` | lever-ID enum | R collectively | No | `demand` | Slider/state | One of `demand`, `promo`, `markdown`, `inbound`, `lead`, `safety`; all six required. |
| `simulation.levers[].label` | string | P | No | `Demand shift` | Slider/banner | Display label. |
| `simulation.levers[].unit` | string | P | No | `%` or `d` | Slider/banner | Display unit. |
| `simulation.levers[].min` | number | P | No | `-30` | Slider | Minimum. |
| `simulation.levers[].max` | number | P | No | `40` | Slider | Maximum. |
| `simulation.levers[].step` | number | P | No | `1` | Slider | Step. |
| `simulation.levers[].effect` | string | P | No | `Moves the whole forecast curve` | Slider helper | Human explanation. |
| `simulation.scenario_levers` | object | R | No | `{...}` | Scenario run/load state | Current six numeric lever values. |
| `simulation.scenario_levers.demand` | number | R | No | `0` | Scenario state | Demand shift percentage. |
| `simulation.scenario_levers.promo` | number | R | No | `15` | Scenario state | Promo intensity percentage. |
| `simulation.scenario_levers.markdown` | number | R | No | `25` | Scenario state | Markdown depth percentage. |
| `simulation.scenario_levers.inbound` | number | R | No | `0` | Scenario state | Extra inbound percentage. |
| `simulation.scenario_levers.lead` | number | R | No | `0` | Scenario state | Vendor lead-time delta in days. |
| `simulation.scenario_levers.safety` | number | R | No | `0` | Scenario state | Safety-stock delta in days. |
| `simulation.baseline` | object | R | No | `{...}` | Simulator metrics/chart | Baseline metrics for current scope. |
| `simulation.scenario` | object | R | No | `{...}` | Simulator metrics/chart | Scenario metrics; equals baseline when unapplied. |
| `simulation.baseline.forecast_next_7d` / `simulation.scenario.forecast_next_7d` | number | R | No | `3995` | Simulator | Seven-day units. |
| `simulation.baseline.stockout_risk_skus` / scenario equivalent | number | R | No | `1` | Simulator | Stockout-risk count. |
| `simulation.baseline.forecast_accuracy_pct` / scenario equivalent | number | R | No | `94.7` | Simulator | Accuracy percentage. |
| `simulation.baseline.predicted_to_trend` / scenario equivalent | number | R | No | `1` | Simulator | Trending count. |
| `simulation.baseline_forecast` | series object | R | No | `{...}` | `DemandScenarioComparison` | Current-context baseline; uses the series schema in 2.4. |

### 2.9 Server scenarios

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `scenarios` | array | O | No | `[]` | Normalizer only | Reserved for forward compatibility. Send `[]`. Server scenarios are not loaded into the UI. |
| `scenarios[].id` | string | O | No | `scenario-1` | Not consumed | Scenario identity. |
| `scenarios[].name` | string | O | No | `S1` | Not consumed | Display name. |
| `scenarios[].levers` | six-number object | O | No | `{...}` | Not consumed | Saved levers. |
| `scenarios[].context` | object | O | No | `{...}` | Not consumed | Six compatibility fields: entity, category, store, SKU, grain, horizon. |
| `scenarios[].context.legal_entity_id` | string | O | No | `GRC` | Not consumed | Saved entity. |
| `scenarios[].context.category_group` | string | O | No | `GRC-C01` | Not consumed | Saved category. |
| `scenarios[].context.store_id` | string | O | No | `GRC-S1` | Not consumed | Saved store. |
| `scenarios[].context.sku` | string | O | No | `GRC-001` | Not consumed | Saved SKU search. |
| `scenarios[].context.grain` | grain enum | O | No | `weekly` | Not consumed | Saved grain. |
| `scenarios[].context.horizon_weeks` | integer | O | No | `4` | Not consumed | Saved horizon. |
| `scenarios[].baseline_forecast` | series object | O | No | `{...}` | Not consumed | Saved-context baseline. |
| `scenarios[].forecast` | series object | O | No | `{...}` | Not consumed | Saved scenario series. |
| `scenarios[].saved_at` | string | O | No | `2026-08-06T03:05:00Z` | Not consumed | Save time. |

Compare Scenarios is session-local React state. Local saved objects also carry
their scenario metrics and both series, but this is not a server contract.

### 2.10 Suggested actions

| JSON path | Type | Req. | Nullable | Example | Consumer | Meaning |
|---|---|---:|---:|---|---|---|
| `suggested_actions` | object | R | No | `{...}` | `DemandSuggestedActions` | Presentational recommendations only. |
| `suggested_actions.primary` | object | R | No | `{...}` | Primary card | Seven-day forecast-basket recommendation. |
| `suggested_actions.primary.title` | string | R | No | `Send 7-day forecast basket to Replenishment` | Primary card | Recommendation title. |
| `suggested_actions.primary.description` | string | R | No | `3,995 units across 1 SKU...` | Primary card | Current-scope numeric explanation. |
| `suggested_actions.primary.action_label` | string | R | No | `Send to Replenishment` | Disabled button | Visible transactional label; control remains disabled. |
| `suggested_actions.secondary` | object | R | No | `{...}` | Secondary card | Stockout-risk recommendation. |
| `suggested_actions.secondary.title` | string | R | No | `Raise safety stock on 1 stockout-risk SKU` | Secondary card | Current risk count. |
| `suggested_actions.secondary.description` | string | R | No | `Forecast exceeds supply...` | Secondary card | Explanation. |
| `suggested_actions.secondary.action_label` | string | R | No | `Flag to Inventory Risk` | Disabled button | Visible transactional label; control remains disabled. |
| `suggested_actions.plan_preview` | object | R | No | `{...}` | Read-only preview | Forecast basket preview. |
| `suggested_actions.plan_preview.title` | string | R | No | `Generate forecast basket` | Preview header | Plan concept. |
| `suggested_actions.plan_preview.description` | string | R | No | `Read-only preview...` | Preview header | Backend-pending caveat. |
| `suggested_actions.plan_preview.rows` | array | R | No | `[...]` | Preview table | Recommended top basket rows, currently up to 12 normalized. |
| `suggested_actions.plan_preview.rows[].sku_id` | string | P | No | `GRC-001` | Row key | SKU ID. |
| `suggested_actions.plan_preview.rows[].sku_name` | string | P | No | `Everyday Essential 001` | Preview table | Item name. |
| `suggested_actions.plan_preview.rows[].forecast_7d_units` | number | R | No | `3995` | Preview table | True seven-day forecast regardless of overview/Detail grain. |
| `suggested_actions.plan_preview.rows[].signal` | string | P | No | `viral` | Preview table | Main demand signal. |
| `suggested_actions.plan_preview.rows[].route` | string | P | No | `Priority review` | Preview table | Presentational route/status text only. |

## 3. Full Example Response

A complete representative response is stored at:

`plans/demand-forecasting-api-example.json`

It represents a weekly, four-week-horizon request scoped to GRC, Fresh
Produce, store GRC-S1, and SKU GRC-001. It has been passed through:

```js
normalizeDemandDashboard(payload, { requirePhase2: true })
```

The example is deliberately scoped to one SKU to keep the handoff readable;
it still includes every required top-level section, all six KPIs, both series,
all four cluster rows, all 12 seasonality points, simulation metadata, Detail,
trending data, and Suggested Best Action data.

## 4. Backend Source Data Requirements

The backend may source these semantics from normalized tables, a feature
store, a forecast service, or precomputed marts. The frontend does not require
the mock dataset’s physical structure.

| Semantic field/domain | Business meaning | Suggested type | Grain | Source vs derived | UI dependencies | Precomputed measure acceptable? |
|---|---|---|---|---|---|---|
| Legal Entity / Retail Vertical | Owning company/vertical and stable ID/name | string IDs + dimension row | entity | Source master | Filter, entity chart, seasonality weighting | Yes |
| Category | Product category ID/name under an entity | string IDs + dimension row | SKU/category | Source master | Filter, Detail, category chart | Yes |
| Store | Store ID/name and owning entity | string IDs + dimension row | store | Source master | Filter, store chart, rollups | Yes |
| Cluster | Flagship, Mall, Community, or Express classification | enum/string | store | Source attribute | Cluster chart | Yes |
| SKU/item | Stable SKU ID and item name | strings | SKU | Source master | Search, trend, Detail, basket | No substitute for stable IDs |
| Historical actual demand | Observed units, not scenario-adjusted | decimal units | SKU/store/day, aggregatable | Source fact | Both Actual lines, backtest, ADS/trend | Yes, at requested grains if traceable |
| Forecast demand | Model point forecast | decimal units | SKU/store/forecast date | Model output | KPI, future lines, Detail, dimensions, basket | Yes; preferred |
| Confidence bounds | Calibrated forecast interval | low/high decimals | Same as forecast point | Model output/derived | Confidence band and tooltip | Yes; preferred |
| Average daily sales (ADS) | Recent normalized daily unit velocity | decimal units/day | SKU/store/as-of date | Derived from demand/sales | Detail and trending tooltip; forecast inputs | Yes |
| Inventory on hand | Physical available inventory at as-of time | decimal units | SKU/store | Source snapshot | Risk and supply state | Yes |
| Open purchase orders / inbound | Confirmed inbound units and expected receipt timing | decimal units + date/status | SKU/store or SKU/DC/PO line | Source transactional | Risk, supply coverage, What-If semantics | Yes |
| Vendor lead time | Expected supplier-to-location days | decimal/integer days | SKU/vendor/location | Source policy/performance | ROP and risk | Yes |
| Safety stock | Policy buffer in units or days | decimal | SKU/store | Source policy | ROP and risk | Yes |
| Reorder point | Threshold covering lead time plus safety | decimal units | SKU/store/as-of date | Derived or source policy | Stockout-risk and supply state | Yes; otherwise send inputs |
| Growth/trend signal | Forward vs prior demand change and/or model growth score | decimal percent/score | SKU/scope/as-of date | Derived/model output | Demand trend, trending ranking, Detail | Yes |
| Viral signal | External/social/loyalty indication of unusual demand | boolean + optional score | SKU/time window | Source feature/model output | Trending count, signals, uplift context | Yes |
| Promotional signal | Active/planned promotion and intensity | boolean + optional percent/type | SKU/store/date | Source promotion calendar | Forecast, signals, What-If promo lever | Yes |
| Seasonality | Monthly index curve, 100 = average | 12 numeric indices | entity/month; weighted to scope | Source configuration/model output | Seasonality KPI/chart, forecast | Yes |
| Forecast/backtest error | Out-of-sample actual-vs-forecast error | decimal percent | model/scope/backtest window | Derived from actual and archived forecast | Accuracy KPI | Yes; preferred |
| Supply state | Healthy, Low, or Stockout for displayed row | enum | SKU/store/as-of date | Derived | Detail badge, basket priority route | Yes |
| Calendar/day-of-week effects | Trading-day and peak-day multipliers | decimal factor | date/entity/category | Source configuration/derived | Forecast and Peak summary | Yes |
| As-of/model-run metadata | Data cutoff and model version/provenance | timestamp + strings | dashboard run | Source metadata | `as_of`, `note`, auditability | Yes |

At minimum this normally implies eleven logical source domains: organization
master, product/category master, store/cluster master, actual-demand facts,
forecast outputs, inventory snapshots, inbound/open-PO facts, vendor and supply
policy, promotion/calendar data, demand-signal features, and
seasonality/backtest artifacts.

## 5. KPI Calculation Requirements

The frontend needs the derived values, not a mandated production algorithm.
The mock formulas are deterministic UI fixtures and must not be treated as the
production forecasting specification.

| KPI | Source inputs | Required derived backend output | Production semantic requirement |
|---|---|---|---|
| Forecast next 7d | Scoped future point forecasts or SKU/store daily forecasts | `kpis[forecast_next_7d].value`, `forecast.summary[next_7d]`, dimension `chain_total` | Sum expected units for the next seven calendar/trading days under the same scope. |
| Forecast accuracy | Archived forecasts and matching actuals; defined backtest window | Percentage `0..100` | A documented out-of-sample accuracy measure. `100 - MAPE` is acceptable but not required; methodology/window must be stable and label/note truthful. |
| Demand trend | Next-seven-day forecast and comparable prior-seven-day actual/baseline | Signed percentage | Percent change of next 7d vs prior/comparable 7d. Do not substitute a monthly change when the overview grain changes. |
| Stockout-risk SKUs | Forecast through supply lead window, on hand, eligible inbound, lead time, safety stock/ROP | Distinct scoped SKU count | Count SKUs whose available/expected position cannot cover forecast demand within the applicable lead/safety window. Exact policy must be documented. |
| Predicted to trend | Growth/model score, viral/promo/seasonal signals | Distinct scoped SKU count and ranked `trending_items` | Count items crossing a production-approved trending threshold. Mock rank limits are not a production requirement. |
| Seasonality index | Scoped 12-month curve and current/reference month | Numeric index | Must equal the highlighted current point in `dimensions.seasonality`; see section 8. |

Backend output must keep duplicated representations consistent: KPI cards,
overview summaries, simulation baseline metrics, dimensions, Detail totals,
and Suggested Best Action prose must use the same underlying measures.

## 6. Forecast-Series Requirements

### Historical Actual

- Represents observed demand for periods preceding the forecast boundary.
- Must be based on stable source actuals.
- Must not change when a What-If scenario is applied.
- Historical points normally have `actual = number`, `forecast = null`, and
  null bounds.

### Future Forecast and confidence

- Represents model forecast for the selected scope, grain, and horizon.
- Future points normally have `forecast`, `confidence_low`, and
  `confidence_high`; `actual` is null.
- Bounds must satisfy `confidence_low <= forecast <= confidence_high` and must
  correspond to the same model, scope, period, and interval definition.
- Scenario levers may change future forecast and bounds, never historical
  Actual values.

### Transition

`ForecastLineChart` finds the first point whose `forecast` is non-null and
draws the forecast boundary at that point’s `key`. The current contract may
repeat the last Actual as `actual` on that first forecast point to visually
anchor the transition. Keys must be unique and points chronologically ordered.

### Grain and horizon

- Supported overview grains: Daily, Weekly, Monthly, Quarterly, Yearly.
- `horizon_weeks` is always one of 4/8/12/16, even when the overview is
  expressed in another grain.
- The backend chooses an appropriate number of future points covering that
  horizon and reports it truthfully in `horizon_label`.
- The separate `confidence` panel currently expects a weekly series regardless
  of overview grain.
- The frontend does not mandate the mock’s exact history count, but
  `history_count` must match the supplied history and the series must contain
  useful history plus at least one future point.

## 7. Dimension Reconciliation Rules

For a given scope and seven-day forecast basis:

```text
Forecast next 7d KPI
  = sum(dimensions.categories[].forecast_units)
  = sum(dimensions.stores[].forecast_units)
  = sum(dimensions.clusters[].forecast_units)
  = sum(dimensions.legal_entities[].forecast_units)
  = dimensions.chain_total
```

Each hierarchy must derive from the same underlying scoped forecast rows.
Legal Entity totals are sums of stores; Cluster totals are sums of stores;
category totals are a regrouping of the same SKU/store forecast. Use a
deterministic rounding/apportionment method so displayed integers reconcile
exactly.

Detail has different period semantics:

| Detail grain | Meaning of `details.rows[].forecast_units` | Direct equality to next-7d KPI? |
|---|---|---|
| Daily | One selected/next day | No |
| Weekly | Seven-day period | Yes; `details.forecast_total_units = chain_total` |
| Monthly | One month | No |
| Quarterly | One quarter | No |
| Yearly | One year | No |

`details.forecast_total_units` is the full scoped total for the selected
period, including rows not returned because of the 100-row limit.
`details.rows[].forecast_7d_units` always remains seven-day demand and is
separate from selected-period `forecast_units`.

## 8. Seasonality Requirements

- Return exactly 12 chronologically ordered points, January through December.
- Index `100` means an average month.
- Exactly one current/reference month should have `current: true`.
- The `seasonality_index` KPI must equal that point’s `index` exactly.
- A single Legal Entity uses that entity’s curve.
- `ALL` or another mixed-entity scope requires a deterministic weighted curve.
- The current mock weights entity curves by scoped baseline seven-day demand;
  production may use another defensible stable weight, but it must be
  documented and used consistently for both chart and KPI.
- Category, Store, and SKU filters must scope the curve through the same
  deterministic model rather than selecting an unrelated default curve.

## 9. Forecast Detail Contract

Every row field is listed in section 2.7. Key backend rules are:

- Sort returned rows by selected-period `forecast_units` descending.
- Return at most `detail_limit`, capped at 100.
- `total` counts the full matching set.
- `forecast_total_units` totals the full matching set, not just returned rows.
- `forecast_units` follows `scope.grain`.
- `forecast_7d_units` is a separate invariant seven-day value used for the
  forecast basket and must not be derived from Monthly/Quarterly/Yearly Detail.
- ADS is a numeric units/day value; formatting remains frontend-owned.
- `category_id`, `sku_id`, and selection IDs must round-trip into query filters.

## 10. Suggested Best Action Requirements

The frontend renders backend-provided text, but the text must reconcile with:

- current seven-day forecast basket total;
- full scoped SKU count (`details.total`, not the displayed-row count);
- forecast accuracy percentage;
- predicted-to-trend count;
- stockout-risk count; and
- true seven-day per-SKU preview rows.

Recommended backend construction:

- Primary description: `Forecast next 7d`, scoped SKU count, accuracy, and
  predicted-to-trend count.
- Secondary title/description: stockout-risk count and forecast-vs-supply
  interpretation.
- Preview rows: highest-priority/top seven-day SKU forecasts with signal and a
  nontransactional route/status label.

All Send, Flag, Generate, approval, ERP, agent-handoff, and AI behavior remains
out of scope. Buttons stay disabled regardless of response content.

## 11. What-If / Simulation

Current lever contract:

| ID | Label | Unit | Min | Max | Step | Baseline |
|---|---|---:|---:|---:|---:|---:|
| `demand` | Demand shift | `%` | -30 | 40 | 1 | 0 |
| `promo` | Promo intensity | `%` | 0 | 50 | 1 | 15 |
| `markdown` | Markdown depth | `%` | 0 | 60 | 1 | 25 |
| `inbound` | Extra inbound | `%` | -40 | 60 | 1 | 0 |
| `lead` | Vendor lead time | `d` | -2 | 6 | 1 | 0 |
| `safety` | Safety stock | `d` | -2 | 5 | 1 | 0 |

The current simulator is frontend mock/local only. In API mode, pressing Run
returns a visible “backend integration pending” error without making a
scenario request. No production simulation URL exists and this handoff does
not invent one.

### Future simulation endpoint — backend design decision

Minimum eventual request semantics:

- canonical agent ID;
- all eight normalized dashboard query fields;
- the six numeric lever values;
- optional model/data as-of token to prevent simulating against a different
  baseline than the displayed page.

Minimum eventual response semantics:

- the same complete schema-v2 dashboard shape;
- `simulation.applied = true`;
- baseline and scenario metrics;
- baseline and scenario forecast series;
- scenario-adjusted KPIs, future forecast/bounds, trending, Detail,
  dimensions, and Suggested Best Action;
- historical Actual points byte-for-byte/numerically unchanged from baseline;
- all seven-day dimension reconciliation rules preserved.

The backend team must decide route, method, persistence/idempotency,
authorization, model-run versioning, and whether scenario execution is
stateless. No action, approval, ERP, chat, or LLM endpoint is implied.

## 12. Error Contract

The shared frontend client reads JSON error fields in this order:
`detail`, then `error`; otherwise it displays `Dashboard request failed
(<status>)`.

| Condition | Expected HTTP/result | Repository convention and frontend behavior |
|---|---|---|
| Invalid type/range | `422` with `{"detail":"..."}` when FastAPI query validation handles it | Visible dashboard error; no mock fallback. |
| Unknown filter/domain value or inconsistent hierarchy | `400` with `{"detail":"..."}` | Current dashboard route maps builder `ValueError` to 400. Examples: store not in selected entity, unsupported category. |
| Unknown agent | `404` with `{"detail":"..."}` | Current route maps registry lookup failure to 404. |
| Source/model unavailable | `503` with `{"detail":"Dashboard data unavailable: ..."}` | Current dashboard route convention. Do not return fabricated zeros as live data. |
| Malformed schema-v2 response | Prefer prevent with backend contract tests; if HTTP 200 reaches frontend, `normalizeDemandDashboard` throws a visible contract/data error | No fallback to mock. Missing required Phase 2 fields, wrong agent, no forecast points, invalid seasonality, or missing simulation/action fields fail. |
| No matching data | `200` with a valid empty-state schema-v2 payload | Empty KPI values and Detail/trending/dimension rows are acceptable, but `forecast.points` must remain non-empty, seasonality must still have 12 numeric points with a current month, simulation metadata/actions must exist, and Chain Total should be zero. |

The backend must avoid exposing confidential source exception content in 503
details while preserving a useful operator-facing log.

## 13. Calculation Ownership

| Concern | Backend | Frontend |
|---|---|---|
| Data retrieval | Owns | None |
| Source authorization and scoping | Owns | Sends query only |
| Forecast calculations/model invocation | Owns | None in API mode |
| Historical Actual aggregation | Owns | Renders supplied values |
| Confidence bounds | Owns | Renders band |
| KPI calculations | Owns | Formats values |
| Category/Store/Cluster/Entity aggregation | Owns | Renders and drills down |
| Dimension reconciliation/rounding | Owns | Assumes exact totals |
| Seasonality weighting and current index | Owns | Highlights supplied current point |
| Trending ranking/signals | Owns | Displays/selects items |
| Detail period conversion and sorting | Owns | Displays maximum 100 rows |
| Supply state/risk policy | Owns | Displays badge |
| Suggested-action numeric text and basket rows | Owns | Presents read-only/disabled controls |
| Raw numeric response | Owns | Must receive finite numbers |
| Number/localization formatting | None | Owns |
| Chart rendering/tooltips | None | Owns |
| Responsive layout | None | Owns |
| Filter control state | Returns options/effective scope | Owns interaction |
| Loading/error/retry UI | Returns HTTP status/detail | Owns |
| Scenario local storage | None in current phase | Owns session-local saved scenarios |
| Transactional actions/chat/ERP | Out of scope | Disabled |

## 14. Backend Implementation Checklist

- [ ] Keep `GET /api/html/dashboard/retail.demand_forecasting` as the public endpoint.
- [ ] Accept and validate all eight Demand query parameters.
- [ ] Extend the generic route/builder signature so Store, SKU, grain, horizon, offset, and limit are not ignored.
- [ ] Map real organization, product, store, actual-demand, forecast, inventory, inbound, policy, promotion, signal, seasonality, and backtest data.
- [ ] Populate the six KPI objects with raw numeric values.
- [ ] Populate period-aware overview Actual/Forecast points.
- [ ] Populate the separate weekly confidence series and valid low/high bounds.
- [ ] Keep historical Actual values invariant under any future scenario.
- [ ] Populate and rank `trending_items`.
- [ ] Populate full-result Detail metadata and at most 100 rows.
- [ ] Provide both selected-period `forecast_units` and true `forecast_7d_units`.
- [ ] Populate Category, Store, Cluster, and Legal Entity seven-day totals.
- [ ] Reconcile every dimension sum exactly to `dimensions.chain_total` and Forecast next 7d.
- [ ] Return exactly 12 seasonality points with one current month.
- [ ] Make the Seasonality KPI equal the highlighted curve point.
- [ ] Populate six lever definitions, scenario values, baseline/scenario metrics, and baseline series.
- [ ] Populate Suggested Best Action strings and seven-day basket preview rows.
- [ ] Return `scenarios: []`; do not attempt server scenario persistence in this phase.
- [ ] Add backend contract tests using `plans/demand-forecasting-api-example.json` as a shape reference.
- [ ] Confirm the response passes `normalizeDemandDashboard(payload, { requirePhase2: true })`.
- [ ] Return 400/404/422/503 errors using the repository JSON `detail` convention.
- [ ] Confirm API errors do not fall back to mock.
- [ ] Verify `VITE_DEMAND_FORECASTING_DATA_SOURCE=api` works without React component changes.
- [ ] Keep `dashboard_only=True`; do not enable chat, action, monitoring, approval, ERP, or LLM behavior.

## Unresolved backend design decisions

1. Physical source systems/tables and ownership for actuals, forecasts,
   inventory, inbound, signal features, and seasonality.
2. Production forecast model, interval level, model version, and run cadence.
3. Production definition and backtest window for Forecast accuracy.
4. Production thresholds/policy for stockout-risk and predicted-to-trend.
5. Mixed-entity seasonality weighting method, provided it is deterministic and
   keeps the KPI/chart identical.
6. Whether the generic dashboard route is extended directly or delegates the
   eight parameters through a Demand-specific builder abstraction.
7. Future simulation route/method, statelessness, versioning, authorization,
   and persistence. No decision is required to deliver the read-only dashboard
   endpoint.

---

## Store Filter Error Analysis

Investigation date: 2026-08-14

### 1. Executive Summary

The Store dropdown is holding and sending the correct canonical individual
Store ID. For example, `S001` means `S001 · Grocery 01 · Jakarta Pusat`; it is
not a Store name, cluster, or region.

The primary root cause is at the backend scope/query boundary. The endpoint
parses `store_id=S001` into `DashboardScope.store_id == "S001"`, but the Demand
Forecasting descriptor declares `store_id` unsupported and its SQL scope helper
does not generate a Store predicate. The builder therefore returns the same
chain-level `fact_inventory_chain_daily` rows and the complete 160-store
dimension for `S001`, `S002`, and All Stores.

There is a second, reinforcing frontend defect: the API response is treated as
already scoped, but `scopeItems()` and `scopeStores()` do not apply
`query.store_id`. The frontend then rebuilds the dashboard from the unscoped
rows and drops the backend's `ignored_filters` warning. This is a data-contract
and query-scope failure, not a stale-cache problem.

Impact is high for a Store-specific view: the forecast, inventory-risk,
SKU/detail, dimension, suggested-action, and simulation outputs remain
chain-wide or entity-wide while the scope chip says the selected Store. The
selected Store can therefore display `1,656,178.22` chain forecast units even
though the database has `25,948.94` units for S001 and `30,756.58` for S002.

### 2. Expected Behavior

When the user selects `S001 · Grocery 01 · Jakarta Pusat`, the expected flow is:

```text
option.value "S001"
  -> query.store_id "S001"
  -> GET /api/html/dashboard/retail.demand_forecasting?store_id=S001
  -> DashboardScope.store_id "S001"
  -> Store-scoped source rows and aggregations
  -> response scope/store dimension identifies S001
  -> frontend renders only S001's forecast and risk values
```

The same flow for `S002` must produce S002-specific results. All Stores must
omit the query parameter (or normalize it to null) and use the documented
chain-wide scope.

### 3. Actual Behavior

The frontend correctly changes its state and makes a new request, but the
backend treats the non-empty Store filter as an unsupported filter for this
agent. It still executes the chain query without a Store predicate and the
per-Store query without `s.store_id = :store_id`.

The live route returns HTTP 200 and explicitly reports
`"ignored_filters": ["store_id"]`, but the frontend's API gateway uses the
response as raw rows, calls `buildDashboardFromFixture(rows, query)`, and does
not propagate `ignored_filters` to the rendered dashboard. Its local selectors
also ignore `query.store_id`, so the resulting dashboard is still chain-wide.

Observed live route behavior:

| Request | HTTP | `ignored_filters` | chain items | Store rows | first Store IDs |
| --- | ---: | --- | ---: | ---: | --- |
| `/api/html/dashboard/retail.demand_forecasting` | 200 | absent | 800 | 160 | S001, S002, S003 |
| `...?store_id=S001` | 200 | `["store_id"]` | 800 | 160 | S001, S002, S003 |
| `...?store_id=S002` | 200 | `["store_id"]` | 800 | 160 | S001, S002, S003 |

### 4. End-to-End Value Trace

Concrete trace for `S001`:

| Stage | Store value / meaning |
| --- | --- |
| Dropdown label | `S001 · Grocery 01 · Jakarta Pusat` |
| Dropdown option value | `S001` |
| Frontend filter state | `query.store_id = "S001"` |
| Frontend effect/request trigger | `query.store_id` is a dependency of the dashboard-loading `useEffect`; changing it starts a new load |
| HTTP parameter | `store_id=S001` |
| Backend received value | FastAPI `store_id: str | None` receives `"S001"` |
| Backend normalized value | `DashboardScope(store_id="S001")`; `"ALL"`/empty would normalize to `None` |
| Descriptor/service argument | No separate service/repository exists; the route calls `descriptor.build_dashboard(scope)`, which is `demand_forecasting.dashboard.build(scope)` |
| SQL scope helper result | `("", {})` for `DashboardScope(store_id="S001")`; no Store clause or bound Store parameter is produced |
| Chain SQL column/predicate | No Store column exists in `fact_inventory_chain_daily`; query is filtered only by `c.cal_date = :day` (plus optional entity/category predicates) |
| Per-Store SQL column/predicate | Joins `f.store_key = s.store_id`, but filters only `f.cal_date = :day`; there is no `s.store_id = :store_id` predicate |
| SQL bound values | `day = "2026-07-01"`; no `store_id` bind value |
| Backend returned rows | 800 chain-net item rows and all 160 Store rows; the Store rows include S001 and S002 rather than only S001 |
| Backend warning | `ignored_filters: ["store_id"]` |
| Frontend response processing | Rebuilds a dashboard from `items` and `stores`; `scopeItems` filters only legal entity, category, and SKU search; `scopeStores` filters only legal entity |
| Frontend displayed scope | The locally reconstructed scope says `store_id = "S001"`, so the scope chip looks correct |
| Frontend displayed data | KPI `forecast_next_7d = 1,656,178.21602674`, Detail total `800`, and Store dimension count `160` — chain/all-store values |

The same trace with `S002` has the same backend SQL and the same frontend
result. Only the HTTP request value and the ignored-filter warning's presence
change from the All Stores request.

### 5. Reproduction

1. Open the Demand Forecasting page (`retail.demand_forecasting`) with the API
   data source enabled.
2. Leave Legal Entity and Category at All.
3. Select `S001 · Grocery 01 · Jakarta Pusat` in the Store dropdown.
4. Observe the browser request:

   ```http
   GET /api/html/dashboard/retail.demand_forecasting?store_id=S001
   ```

5. Observe the 200 response metadata:

   ```json
   {
     "ignored_filters": ["store_id"],
     "items": ["800 chain-level item rows"],
     "stores": ["160 Store rows"]
   }
   ```

6. The live database has this Store-level evidence for the same snapshot:

   | Store | SKU rows | Store forecast 7d | `position < rop` risk SKUs |
   | --- | ---: | ---: | ---: |
   | S001 | 100 | 25,948.941032500927 | 46 |
   | S002 | 100 | 30,756.578276753906 | 53 |

7. Select S002. The request changes to
   `...?store_id=S002`, but the response still contains 800 chain items and
   160 Store rows, and the frontend still renders the same chain-wide KPI.

The frontend selector was also executed directly with the checked-in response
shape for All, S001, and S002. It produced, in every case, 800 items,
`1,656,178.21602674` forecast units, 160 Store dimension rows, and the same
first Detail SKU (`GRC-025`). With `legal_entity_id=GRC`, S001 and S002 both
produced the GRC total `442,050.26262828155` and 100 items, rather than a
Store-specific result.

### 6. Evidence

Frontend:

- `frontend/src/agents/retail/demand_forecasting/components/DemandForecastFilters.jsx:61-67`
  renders the Store `<select>` with `value={query.store_id}` and sends the
  selected DOM value to `onPatch({ store_id: value })`.
- `frontend/src/agents/retail/demand_forecasting/data/contract.js:84-97`
  normalizes Store state as a string and defaults it to `"ALL"`.
- `frontend/src/agents/retail/demand_forecasting/data/contract.js:111-124`
  serializes the selected value as the `store_id` request field and omits only
  `ALL`.
- `frontend/src/api/dashboard.js:20-40` serializes that field with
  `URLSearchParams` and calls the canonical dashboard route.
- `frontend/src/agents/retail/demand_forecasting/DemandForecastingDashboard.jsx:53-91`
  includes `query.store_id` in the load effect dependencies, so changing Store
  does trigger a new request. There is no React Query, SWR, Redux, or other
  response cache in this path.
- `frontend/src/agents/retail/demand_forecasting/data/dashboardData.js:48-57`
  confirms that API mode receives rows, then rebuilds the dashboard locally.
- `frontend/src/agents/retail/demand_forecasting/data/selectors.js:86-101`
  proves that local scoping checks only legal entity, category, and SKU search;
  Store is not checked in either `scopeItems` or `scopeStores`.
- `frontend/src/agents/retail/demand_forecasting/data/selectors.js:448-471`
  builds KPIs from `baselineItems` and dimensions from `stores`, so an
  unscoped backend payload remains unscoped on screen.

Backend:

- `backend/src/api/agents_html.py:551-553` declares the expected public
  parameter as `store_id` and `:600-626` parses the scope, calls the builder,
  and attaches `ignored_filters`.
- `backend/src/llm/agents/common/dashboard_scope.py:44-50` defines
  `store_id` as a Store join key; `:68-80` normalizes it; `:82-96` marks it as
  applied when non-empty.
- `backend/src/llm/agents/retail/demand_forecasting/__init__.py:62-63`
  passes the builder's `SUPPORTED_FILTERS` to the descriptor.
- `backend/src/llm/agents/retail/common/warehouse.py:53-57` declares only
  `legal_entity_id` and `category_group` as supported, and
  `:106-116` shows `_scope_clause()` can emit only those two predicates.
- `backend/src/llm/agents/retail/demand_forecasting/dashboard.py:150-193`
  contains the actual chain and Store SQL. The chain query reads
  `fact_inventory_chain_daily` (one row per item, no Store key); the Store
  query reads `fact_inventory_daily` joined to `dim_store`, but applies only
  the snapshot date and optional legal-entity predicate.
- `backend/src/llm/agents/retail/demand_forecasting/dashboard.py:219-251`
  converts chain rows into `items` without a `store_id`; `:261-289` returns
  the per-Store rows as a separate dimension block, not as the selected item
  scope.

Live evidence captured during this investigation:

- Real FastAPI TestClient requests for All, S001, and S002 all returned 200;
  selected requests returned `ignored_filters: ["store_id"]`, 800 items, and
  160 stores.
- Read-only database counts were 800 rows in
  `retail.fact_inventory_chain_daily` and 16,000 rows in
  `retail.fact_inventory_daily` for `2026-07-01`.
- The chain forecast sum was `1,656,178.2160267404`; the Store sums above were
  different and were not used to scope the returned chain items.

### 7. Root Cause

The frontend Store contract is internally consistent: `option.value` is the
canonical Store ID, the state is `query.store_id`, and the HTTP field is
`store_id`. No frontend-to-backend naming or label/value mismatch was found.

The primary root cause is that the Demand Forecasting backend does not apply
the Store ID it accepts. `DashboardScope` preserves `S001`, but
`SUPPORTED_FILTERS` excludes `store_id`; `_scope_clause()` therefore emits no
Store predicate; and both Demand SQL statements run at chain/all-store scope.
The route correctly exposes this as `ignored_filters`, but still returns 200.

The frontend has a matching assumption that is invalid for this filter:
`scopeItems()` and `scopeStores()` assume the backend has already narrowed rows,
but neither applies `query.store_id`. Because chain item rows carry no Store ID,
the frontend cannot repair this by filtering the current payload. It displays a
locally echoed Store scope over chain-wide data.

The first semantic divergence is therefore:

```text
Backend normalized scope: store_id = S001
        !=
SQL scope: no Store predicate; chain/all-store rows
```

The second divergence is:

```text
Frontend displayed scope: store_id = S001
        !=
Frontend displayed rows: rows returned without Store scope
```

### 8. Contributing Factors

- `ignored_filters` is an intentional backend warning, but
  `dashboardData.js` reconstructs a new payload and drops that field before
  `normalizeDemandDashboard()`/the React components can show it.
- The endpoint's public description says Store filtering is supported, while
  the Demand descriptor's `SUPPORTED_FILTERS` says it is not.
- The backend response has no effective `scope` echo. The frontend creates its
  own scope from the request, so the UI can claim S001 without server
  confirmation.
- The row contract mixes chain-net item rows and gross per-Store rows. A
  chain-net table cannot represent an individual Store filter because it has no
  Store dimension. The per-Store table does, through `store_key` joined to
  `dim_store.store_id`.
- Existing frontend tests assert that a Store click changes `store_id` in the
  load call, but do not assert that the returned KPI, Detail rows, or dimension
  scope changes. Existing backend tests intentionally assert that Store is an
  ignored filter for Retail builders, which protects the current behavior
  rather than the UI contract.
- No evidence supports a stale-cache explanation: `query.store_id` is a load
  dependency, `fetchDashboard()` performs a new fetch, and no client cache
  library is used in this path.

### 9. Scope of Impact

| Demand Forecasting output | Impact for a selected Store | Evidence / reason |
| --- | --- | --- |
| Store dropdown and scope chip | Misleading only | The selected ID/label is correct, but it is not reflected in the rows |
| API request | Not affected | `store_id=S001`/`S002` is sent correctly |
| Forecast next 7d KPI | Affected | Chain `1,656,178.22` is shown instead of selected Store scope |
| Forecast horizon/overview series | Affected | Series is generated from the unscoped chain item ADS sum |
| Confidence series | Affected semantically; value may coincide | It is generated from the same unscoped items; accuracy is also a uniform typed constant `92.4` |
| Forecast accuracy / MAPE | Scope affected, numeric difference not provable | This dataset has no backtest; the displayed 92.4% is typed at vertical level |
| Demand trend | Affected semantically and generally numerically | It is blended from all returned chain items; S001's GRC value is 5.6, while All Stores is 6.303178995... |
| Stockout-risk SKU KPI | Affected | Chain value is 302; Store-level source counts are 46 for S001 and 53 for S002 |
| Inventory position / inbound / supply state | Affected | Detail rows come from chain-level position, open PO, ROP, and state |
| Category/product breakdowns | Affected | Categories and Detail are grouped from unscoped chain item rows |
| Detail table | Affected | Selected S001/S002 still shows 800 chain items when no legal entity is selected |
| Forecast by Store chart | Affected for selected scope | It still shows all 160 Store rows; the selected Store is not isolated |
| Cluster chart | Affected | It is grouped from all returned Store rows |
| Legal Entity chart | Affected | With no entity selected it remains a chain-wide rollup, not the selected Store's entity scope |
| Seasonality | Scope affected; no Store-level source is available | It is built from vertical GMV, not a Store-specific dataset |
| Suggested actions/worklist | Affected | It is derived from unscoped chain items and risk/trend membership |
| What-If simulation | Affected | Scenario calculations start from the same unscoped `items` array |
| Actual demand/history | Not currently measurable | `fact_sales_daily` is empty and the forecast-only series renders `actual: null`; Store correctness cannot be validated for history until actuals exist |

### 10. Recommended Fix

Establish one canonical Store identifier at the request boundary and make
Store scope a real backend capability:

```text
frontend option.value / query.store_id: "S001"
        -> API store_id=S001
        -> DashboardScope.store_id="S001"
        -> retail.dim_store.store_id = fact_inventory_daily.store_key
        -> Store-scoped rows and aggregations
        -> effective response scope.store_id="S001"
```

The smallest correct architectural change is to decide and document the
measure grain, then make the backend builder honor it. For a selected Store,
the builder should use the per-Store source (`fact_inventory_daily` joined to
`dim_store`, plus the needed item/category/reference joins) or a Store-aware
view, shape those rows into the frontend row contract, and return only the
selected Store in the Store dimension. For All Stores, it may continue using
the chain-net source if chain-net is the intended headline measure. The UI must
not silently compare a chain-net total with a Store gross total; the response
must identify its effective grain.

At the same time, either make the backend response fully scoped and keep the
frontend's row-selector assumption explicit, or add a real `store_id` check to
the frontend selectors for a payload that contains Store-keyed item rows. The
current payload has no Store ID on `items`, so a frontend-only filter cannot be
the fix.

The backend should also return an effective `scope` and an explicit `grain`,
and the frontend should preserve/display `ignored_filters` as an error or
unsupported-filter state. Do not merely add `store_id` to
`SUPPORTED_FILTERS` without adding the corresponding SQL/data scope.

### 11. Regression Tests Required

Frontend:

- Assert the Store option `S001 · Grocery 01 · Jakarta Pusat` has value
  `S001` and the All Stores option has value `ALL`.
- Assert selecting S001 produces exactly `store_id=S001` in the request URL;
  selecting S002 produces `store_id=S002`; All Stores omits the field.
- Assert changing Store causes a new load and cannot reuse the previous
  response/cache entry. There is no cache today, but this should remain an
  explicit request contract.
- With a Store-scoped fixture, assert S001 and S002 produce different KPI,
  Detail, risk, and Store-dimension results.
- Assert the frontend does not render a selected Store scope over rows whose
  effective response scope is chain-wide or whose `ignored_filters` includes
  `store_id`.

Backend:

- Assert `DashboardScope.from_query(store_id="S001")` preserves S001 and
  `DashboardScope.from_query(store_id="ALL")` yields no applied Store filter.
- Assert the Demand descriptor declares `store_id` supported only after the
  builder actually implements it.
- Assert the generated chain/per-Store query for S001 contains the intended
  Store predicate and a bound Store ID, or intentionally selects a documented
  Store-aware source.
- Assert `build(DashboardScope(store_id="S001"))` returns only S001-scoped
  rows and `build(DashboardScope(store_id="S002"))` returns only S002-scoped
  rows; neither may include `ignored_filters`.
- Assert All Stores has the documented omitted/null representation and
  preserves chain-wide totals.

Integration:

- Send All, S001, and S002 through the real HTTP route.
- Assert the effective response scope and returned Store IDs match the
  request.
- Assert S001 and S002 return distinct expected forecast and risk values.
- Assert every Demand output (KPI, forecast series, confidence, category,
  Store/cluster/entity dimensions, Detail, suggested actions, and simulation
  baseline) is derived from the same effective Store scope.
- Add a negative test for a mismatched or unknown Store ID and a test for a
  Store outside a selected Legal Entity.

### API Contract Recommendation

| Contract field | Recommended value |
| --- | --- |
| Frontend field | `query.store_id`; dropdown `option.value` |
| API parameter | `store_id` |
| Type | string |
| Example | `"S001"` |
| Backend field | `DashboardScope.store_id` |
| Database column | `retail.dim_store.store_id`, joined to `retail.fact_inventory_daily.store_key` for Store-grain facts |
| Meaning | Canonical individual Store identifier; not Store name, cluster, region, or legal entity |
| All-Stores representation | Frontend state `"ALL"`; omit from HTTP; backend normalize omitted/`"ALL"` to `null` |

The response should echo the effective scope, including `scope.store_id`, and
declare the measure grain. A selected Store must never return an unlabelled
chain-net total under a Store-specific scope. The contract must also define
whether Store-specific forecast totals are gross sums from
`fact_inventory_daily` or another Store-grain forecast source; that decision
cannot be inferred from the current UI and should be made before coding.

### Implementation / Resolution

Implementation date: 2026-08-14

The recommended fix is implemented. The public contract remains unchanged:

```text
GET /api/html/dashboard/retail.demand_forecasting?store_id=S001
```

The route still normalizes the request to `DashboardScope(store_id="S001")`.
Demand Forecasting now declares `store_id` in its own `SUPPORTED_FILTERS`, and
the shared SQL scope helper accepts a real Store column only when a caller
provides one. The chain query deliberately does not receive a fabricated Store
predicate because `fact_inventory_chain_daily` has no Store key.

For a selected Store, the builder now queries the actual Store-grain source:

```sql
FROM retail.fact_inventory_daily f
JOIN retail.dim_store s ON s.store_id = f.store_key
JOIN retail.dim_item i ON i.item_id = f.item_key
JOIN retail.dim_vertical vt ON vt.vertical_id = i.vertical_id
WHERE f.cal_date = %(day)s
  AND s.store_id = %(store_id)s
```

The same `s.store_id = %(store_id)s` predicate is applied to the Store
dimension query. `f.forecast_7d`, ADS, inventory position, open PO, ROP, state,
item metadata, and the individual Store `size_index` are therefore selected
before the frontend's existing calculations run. Returned Store-grain item
rows carry `store_id`, and the returned Store dimension contains only the
selected Store. `ignored_filters` no longer contains `store_id` after the
builder successfully applies it. The response also echoes the normalized
scope and carries explicit Store-scope limitations through the frontend, where
they are displayed rather than hidden.

#### Store-total source decision

All Stores intentionally remains on `retail.fact_inventory_chain_daily`, one
row per SKU. Its forecast sum is `1,656,178.21602674`, which is the existing
chain KPI and the source that preserves the current KPI's chain-net meaning.
The seed documentation explicitly says the 800-row chain fact is not safely
reconstructed by summing the 16,000 Store rows: Store rows are rounded before
aggregation and chain state/position is evaluated from chain inputs.

For a selected Store, the semantically equivalent Store-grain source is
`retail.fact_inventory_daily.forecast_7d` (ENGINE_STORE's f08 value), not a
newly defined metric and not a numerically convenient split of the chain KPI.
It is the same workbook seven-day forecast measure at Store × SKU grain and is
the only loaded source that supplies that measure together with Store-scoped
inventory and inbound inputs. This yields `25,948.94103250092` for S001 and
`30,756.578276753906` for S002.

#### Output scope after the fix

Store-scoped inputs now feed the forecast KPI, forecast time series, forecast
confidence levels/intervals, inventory and inbound quantities, supply-risk
classification, category/product rankings, detail rows, Store/cluster/legal
entity dimensions, suggested actions, and What-If baseline/simulation rows.
The following remain explicitly limited because the schema/data does not
provide a genuine Store-grain source:

- historical actual demand: the loaded sales-history source has no rows, so
  actuals remain null;
- accuracy/MAPE and demand trend: the existing values are vertical-level
  workbook constants, not Store-grain backtests;
- seasonality: `fact_gmv_monthly` is vertical-level and has no Store key.

These limitations are returned as `scope_limitations` and displayed in the
Store-scoped dashboard. They are not represented as if they were Store facts.

**Resolved**: predicted-to-trend was previously listed here too — the count
was a vertical-level reference value while the ranked items were Store-scoped,
so 100% of a Store's SKUs could get marked trending once the requested count
exceeded the Store's row count. `is_trending` is now a per-row formula
(`viral OR growth > 1.25`, see `dashboard.py`'s `is_trending()`) that needs no
vertical-wide count and is correctly computable at Store/category grain, so
this is no longer a limitation.

#### Before/after live evidence

The post-implementation TestClient capture used the seeded snapshot
`2026-07-01`:

| Request | Normalized scope | Ignored filters | Item rows | Returned Store IDs | Forecast KPI |
| --- | --- | --- | ---: | --- | ---: |
| `GET .../retail.demand_forecasting` | `{}` | none | 800 chain rows | S001–S160 (160) | 1,656,178.21602674 |
| `GET ...?store_id=S001` | `{"store_id":"S001"}` | none | 100 Store × SKU rows | S001 only | 25,948.94103250092 |
| `GET ...?store_id=S002` | `{"store_id":"S002"}` | none | 100 Store × SKU rows | S002 only | 30,756.578276753906 |

The executed SQL capture showed bound parameters
`{"day":"2026-07-01","store_id":"S001"}` and the predicate
`AND s.store_id = %(store_id)s`; the S002 request had the corresponding S002
bound value. S001 and S002 are therefore distinct at the query/input level,
not merely relabelled response totals.

#### Validation

- Backend scope/parser, descriptor, Retail builder/route, and Store integration
  suites: **58 passed**.
- Store-specific live builder/API/SQL-listener tests: **4 passed** against the
  seeded Postgres database.
- Frontend Demand Forecasting suite: **30 passed**; the existing behavior
  remains green and the new request-contract assertion verifies
  `store_id=S001`.
- Python syntax validation passed for the changed backend modules.
