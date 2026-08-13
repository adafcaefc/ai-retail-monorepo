# Demand Forecasting Dashboard Frontend Plan

This plan covers the populated dashboard for the existing canonical module
`retail.demand_forecasting`. It does not cover chat, agent actions, monitoring,
Inventory Risk, Replenishment, or changes to the Retail navigation architecture.
The visual and synthetic-data reference is
`AI_360_Retail_Suite_v8.2_General_9Agents 20260806.html`, specifically Agent 1
(`a1`) and the shared sales-view/filter functions it uses.

## 1. Current Repository Architecture

- `backend/src/llm/agents/modules.py` is the navigation source of truth. Its
  enabled IDs are returned by `GET /api/html/agents`; the frontend does not own
  another module list.
- `AgentsProvider` prepends the three frontend-only Main pages, shapes the
  backend agent list, and exposes agents keyed by canonical ID.
- `App.jsx` holds `activeAgent`. A sidebar click stores the selected canonical
  ID, and the selected agent's `dashboardComponent` is rendered. This is
  state-based module routing; the application does not use React Router URLs.
- `frontend/src/agents/registry.js` eagerly discovers
  `frontend/src/agents/*/*/index.js` and merges each override into the matching
  API item by exact canonical ID.
- All three Retail overrides currently reference the same empty
  `RetailDashboard`. Their IDs, active states, chat state, and metadata remain
  separate even though the component is shared.
- Demand Forecasting should be populated by changing only its override to a
  Demand-specific component. Inventory Risk and Replenishment should continue
  to reference the empty shared component.
- `dashboard_only=True` disables chat submission, monitoring, alerts/actions,
  generic Workboard data traffic, and simulations. It does **not** stop a
  custom dashboard component from loading its own dashboard data. Demand
  Forecasting can therefore remain dashboard-only while its custom component
  loads mock data now and JSON later.
- `App.jsx` passes `chatLabel` to `AlertsPanel`. Demand's override supplies
  `chatLabel: "Demand"`, so the top-right UI remains `Ask Demand`; the textarea
  and Send button remain disabled because the module is dashboard-only.
- The Retail topbar convention is already handled by `App.jsx`: small grey
  kicker `Retail`, then the selected module's larger white name. A custom
  dashboard does not need to render another page header.
- The generic dashboard data convention is
  `GET /api/html/dashboard/{canonical_agent_id}`. The existing frontend
  `fetchDashboard(agent, filters)` function serializes any non-empty filter
  object into that request.
- The shared `Workboard` understands the Finance dashboard payload and a fixed
  KPI/main-chart/side-chart/simulator layout. The Demand mockup has a different
  layout, six KPIs, a confidence band, a period selector, a horizontal ranking,
  and a detail table. A Demand-specific dashboard is cleaner than expanding
  `Workboard` with Retail branches.
- The frontend is JavaScript/JSX, not TypeScript. It does not use PropTypes or
  runtime schema libraries. Data contracts should use JSDoc typedefs plus a
  small normalizer/validator and targeted tests.
- Recharts is already installed. No chart dependency is needed. The generic
  `ChartRenderer` supports ordinary line/area/bar charts but not the exact
  actual/forecast transition plus low/high confidence envelope or the
  mockup's horizontal trending ranking. Demand-specific Recharts components
  should be used for those two visualizations without changing the generic
  renderer.
- Global styles live in one `frontend/src/styles.css`; there are no component
  CSS imports or CSS modules. New rules should be namespaced under a Demand
  dashboard root and reuse the existing design tokens, container queries,
  cards, focus styles, and reduced-motion rules.
- Existing loading patterns use shape-matched skeletons; errors use
  `role="alert"` and often a Retry action; empty states use muted status copy.
  Existing effects guard against stale responses with a `cancelled` flag.

## 2. Existing Files Relevant to This Work

| File | Current role / extension point |
|---|---|
| `frontend/src/App.jsx` | Owns `activeAgent`, resolves `dashboardComponent`, renders the Retail header convention, passes `chatLabel`, and enforces dashboard-only chat behavior. No dashboard implementation change should be needed here. |
| `frontend/src/App.test.jsx` | End-to-end shell tests for Retail grouping, independent active states, empty dashboards, header text, and disabled chat. It will need to distinguish populated Demand from blank Inventory/Replenishment. |
| `frontend/src/agents/AgentsProvider.jsx` | Fetches module metadata and exposes agent maps/groups. No change planned. |
| `frontend/src/agents/registry.js` | Auto-discovers overrides and merges them by canonical ID. No change planned. |
| `frontend/src/agents/retail/demand_forecasting/index.js` | Current Demand override. It will switch from `RetailDashboard` to `DemandForecastingDashboard` and retain `id`/`chatLabel`. |
| `frontend/src/agents/retail/inventory_risk/index.js` | Must continue pointing at the empty shared dashboard. |
| `frontend/src/agents/retail/replenishment/index.js` | Must continue pointing at the empty shared dashboard. |
| `frontend/src/agents/retail/retail/RetailDashboard.jsx` | Intentionally empty shared Retail canvas. Keep for Inventory Risk, Replenishment, and legacy reuse. |
| `frontend/src/components/Workboard.jsx` | Existing generic Finance dashboard loader/layout. Useful as a reference for async state, filters, accessibility, and formatting, but not the right renderer for the Demand layout. |
| `frontend/src/components/ChartRenderer.jsx` | Shared Recharts renderer for standard backend chart contracts. Reuse its formatting/color conventions where practical; do not add Demand-only band behavior to it. |
| `frontend/src/components/Skeleton.jsx` | Reusable `Skeleton` primitives and generic dashboard skeleton. Demand should use the primitives to build a shape-matched skeleton. |
| `frontend/src/api/dashboard.js` | Existing dashboard client and canonical endpoint path. `fetchDashboard()` already serializes arbitrary non-`ALL` query fields. |
| `frontend/src/format.js` | Application-wide numeric formatting keyed to the EN/ID language choice. Demand should use these helpers rather than mockup `toLocaleString` calls. |
| `frontend/src/LanguageProvider.jsx` / `frontend/src/i18n.js` | Current language state and exact-string translation pattern. Demand-authored labels should be added to the existing dictionaries, not get a parallel locale system. |
| `frontend/src/styles.css` | EY tokens, workboard/card/filter/table conventions, container-based responsiveness, focus states, skeletons, and all component styling. |
| `frontend/src/pages/main/data_source/DataSource.jsx` | Best local example of independent loading/error/retry state and retaining content during refetch. |
| `frontend/src/pages/main/formula_manager/FormulaManager.test.jsx` | Best local example of direct component tests with hoisted API mocks and Testing Library. |
| `backend/src/llm/agents/modules.py` | Keeps the approved three Retail canonical IDs aligned with the sidebar. No change planned. |
| `backend/src/llm/agents/retail/demand_forecasting/__init__.py` | Demand descriptor; currently dashboard-only and points to the legacy empty dashboard builder. A later backend phase will point it to its own builder while keeping the ID and capability flag. |
| `backend/src/llm/agents/retail/retail/dashboard.py` | Shared structural empty response used by all three current Retail scaffolds. Keep for the two blank modules. |
| `backend/src/api/finance_agents_html.py` | Serves module metadata and `GET /api/html/dashboard/{agent}`. Later backend work must decide how Demand-specific query fields are passed to its builder. |
| `backend/src/llm/agents/descriptor.py` | Defines the current three-argument dashboard-builder contract. This is the one backend constraint that does not yet carry store/search/grain/horizon inputs. |
| `backend/src/llm/agents/common/dashboard_blocks.py` | Existing dashboard payload/filter helpers and server-filter naming conventions. Useful reference, but the Demand response should not be forced into the Finance `views/side/simulator` shape. |
| `backend/tests/test_retail_module.py` | Locks the Retail IDs, dashboard-only status, disabled chat metadata, and current empty dashboard. Later it must assert only Inventory/Replenishment remain empty. |

## 3. Mockup Features to Port

### Port in the first Demand dashboard

1. **Demand filter bar**
   - Legal entity / retail vertical.
   - Category.
   - Store.
   - Forecast horizon: 4, 8, 12, or 16 weeks.
   - SKU search.
   - Refresh/retry affordance.
   - Active-scope summary and clear action.

2. **Six Demand KPIs**
   - Forecast (next 7d), units.
   - Forecast accuracy, `100 - MAPE` from an eight-week backtest.
   - Demand trend, next seven days versus previous seven days.
   - Stockout-risk SKUs, forecast demand versus supply/ROP.
   - Predicted to trend, based on viral/seasonal/growth signals.
   - Seasonality index, where 100 is an average month.

3. **Period-aware demand overview**
   - Daily, weekly, monthly, quarterly, and yearly selector.
   - Actual history and AI forecast split.
   - Forecast horizon controlled by the filter bar.
   - Summary metrics under the chart: next 7d, accuracy, trend, and peak
     day/period.

4. **Forecast confidence view**
   - Twelve weeks of actual history.
   - Forecast curve through the selected horizon.
   - Explicit low/high confidence band around forecast points.
   - Visual marker at the actual-to-forecast boundary.
   - Tooltip values for actual/forecast/range.

5. **Predicted-to-trend ranking**
   - Top items ranked by predicted uplift.
   - Signal badges such as viral, growth, seasonal, or promo.
   - ADS context in the tooltip/detail copy.

6. **Forecast detail table**
   - SKU/item, category, ADS, selected-period forecast, trend, signals, and
     supply state.
   - Sorted by forecast descending by default.
   - Row selection updates the SKU scope/search rather than navigating to
     another agent.
   - Empty result message when the filters match no rows.

### Demand formulas found in the mockup

- Seven-day forecast: sum of `ADS * day_of_week_factor` over seven days. The
  mockup's day factors are `[0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25]`.
- Forecast accuracy: `100% - MAPE`; the mock horizon reduces illustrative
  accuracy by about `0.22` points per week beyond eight weeks.
- Trend: `(average forecast next 7d / average actual last 7d) - 1`.
- Stockout risk: count where `position < ROP`; mock ROP is
  `ADS * (lead_days + safety_days)`.
- Predicted-to-trend count: viral items or growth index above `1.25`.
- Predicted uplift ranking: growth uplift plus an illustrative 18-point viral
  adjustment.
- Seasonality index: current month seasonality factor times 100.
- Forecast detail by period: ADS multiplied by days in the selected grain,
  with the mockup's small forecast adjustment.
- Mock confidence band: the reference renders approximately +/-12% around
  the future curve. The normalized contract should carry explicit low/high
  numbers instead of asking the UI to derive the band.

### Simplify or defer

- Do not port the mockup's 800-SKU, 160-store, eight-vertical monolithic data
  engine wholesale. Preserve representative labels, deterministic behavior,
  formulas, and interactions in a Demand-only fixture/calculation layer.
- Do not port Agent 1 chat, challenge responses, inbox handoffs, Replenishment
  routing, agentic suggestions, approvals, ERP write-back, scenario adoption,
  or cross-agent flows.
- The mockup automatically appends category/store/cluster/legal-entity
  breakdowns and a cross-agent what-if simulator to every agent page. They are
  not among the requested first-dashboard building blocks and should be a
  follow-up scope decision rather than silently expanding this implementation.
  The normalized response can be extended later without changing module
  routing.
- The mockup renders two closely related actual-vs-forecast cards: a shared
  period-aware sales view and a Demand-specific weekly confidence view. The
  first implementation should retain both because the former owns the period
  selector/summary and the latter makes the confidence range explicit. If
  product design prefers one consolidated chart, approve that before coding.

## 4. Proposed Component Architecture

Use the existing Demand override folder as the feature boundary:

```text
frontend/src/agents/retail/demand_forecasting/
├── index.js                              # existing override; swap component only
├── DemandForecastingDashboard.jsx       # async state, filter state, page composition
├── DemandForecastingDashboard.test.jsx  # component/integration behavior
├── components/
│   ├── DemandForecastFilters.jsx        # dependent selectors, horizon, search, clear/refresh
│   ├── DemandKpiGrid.jsx                # six read-only KPI cards/sparklines
│   ├── ForecastOverviewPanel.jsx        # period selector + period-aware chart + four summaries
│   ├── ForecastConfidencePanel.jsx      # weekly actual/forecast/band panel
│   ├── ForecastLineChart.jsx            # pure Recharts actual/forecast/range renderer
│   ├── PredictedTrendPanel.jsx          # horizontal Recharts uplift ranking
│   ├── ForecastDetailTable.jsx          # accessible sortable/detail table
│   └── DemandForecastingSkeleton.jsx    # shape-matched loading state using Skeleton
└── data/
    ├── contract.js                      # constants, JSDoc typedefs, normalization/guards
    ├── dashboardData.js                 # one mock/API gateway used by the dashboard
    ├── mockDataset.js                   # deterministic representative master/series seeds
    ├── mockCalculations.js              # pure Demand formulas and scope aggregation
    ├── mockCalculations.test.js          # formula/filter determinism tests
    └── mockDashboard.js                 # mock provider returning the normalized contract
```

Architecture decisions:

- `DemandForecastingDashboard` owns filters and request lifecycle because the
  filters describe one dashboard request. Child components remain
  presentation-only.
- Keep mock data, calculations, normalization, and React presentation in
  separate files. Do not embed copied mockup generators inside JSX.
- Use one pure `ForecastLineChart` core for the period overview and confidence
  panel, parameterized by points/labels rather than duplicating chart math.
- Use Recharts directly for the confidence envelope and horizontal ranking.
  Reuse shared number-format helpers and semantic colors, but do not modify
  `ChartRenderer` for a single module's needs.
- Do not extract internal components from `Workboard`; that would refactor
  unrelated Finance behavior. Match its accessible/status conventions with
  Demand-owned presentational components instead.
- No change is needed in `App.jsx`, `AgentsProvider`, the agent registry,
  `AlertsPanel`, Inventory Risk, Replenishment, or `RetailDashboard`.

## 5. Data Flow

### Mock mode

```text
activeAgent = retail.demand_forecasting
  -> demand override selects DemandForecastingDashboard
  -> local filters create a DemandDashboardQuery
  -> dashboardData.loadDemandForecastingDashboard(query)
  -> mockDashboard.getMockDemandForecastingDashboard(query)
  -> mockDataset + pure mockCalculations
  -> normalizeDemandForecastingDashboard(payload)
  -> KPI/chart/table presentation components
```

### Future API mode

```text
activeAgent = retail.demand_forecasting
  -> same DemandForecastingDashboard and filters
  -> same dashboardData.loadDemandForecastingDashboard(query)
  -> fetchDashboard("retail.demand_forecasting", serializedQuery)
  -> GET /api/html/dashboard/retail.demand_forecasting?...filters
  -> normalizeDemandForecastingDashboard(payload)
  -> same KPI/chart/table presentation components
```

`dashboardData.js` is the only provider-selection point. It should default to
mock mode and read a narrowly scoped, build-time Vite flag such as
`VITE_DEMAND_FORECASTING_DATA_SOURCE=mock|api`. This is the repository's first
frontend environment flag, so add it only for provider selection and document
that Vite bakes it into the build; it is not a runtime server toggle.

## 6. Mock Data Strategy

- Reuse the reference's Demand concepts and formulas, not its monolithic DOM,
  inline CSS, global state object, or cross-agent inventory engine.
- Keep a deterministic representative fixture with enough legal entities,
  categories, stores, and SKUs to exercise every filter and state. It should
  include viral, growth, seasonal, promo, healthy, low, and stockout examples.
- Use stable seeded generation or fixed source rows. The same query must
  return identical results across renders and tests; no `Math.random()` or
  clock-based values.
- `mockCalculations.js` should be pure and independently testable:
  scope rows, aggregate ADS, build period series, compute forecast/accuracy/
  trend/risk/trending/seasonality, calculate confidence bounds, rank trending
  items, and shape detail rows.
- `mockDashboard.js` should expose the same async function and normalized
  response shape as API mode. Do not add artificial latency in production
  mock mode; loading behavior can be tested with controlled promises.
- Keep raw numbers in the data contract. Components format them using
  `format.js` and the active language. Do not store formatted strings as the
  source of truth.
- Treat every mock figure and formula as illustrative. Put an `is_mock: true`
  and a concise data note in the payload so the UI can label the synthetic
  source without presenting it as live ERP data.
- Dependent filter options should be generated from the same scoped dataset:
  changing legal entity resets invalid category/store values before reloading.
- Keep confidence bounds in the output (`confidence_low` /
  `confidence_high`), even in mock mode. The API later owns uncertainty; the
  React chart should only render it.

## 7. Future Backend Contract

### Recommended endpoint

Use the existing canonical dashboard route rather than adding a second Retail
route:

```http
GET /api/html/dashboard/retail.demand_forecasting
```

This preserves the module-ID/endpoint alignment already used by every agent.
The suggested `/api/retail/demand-forecasting/dashboard` would create a second
route naming system and a new router solely for one module.

### Query parameters

| Parameter | Type / default | Purpose |
|---|---|---|
| `legal_entity_id` | string / `ALL` | Retail vertical/legal entity. Reuses the existing server-filter name. |
| `category_group` | string / `ALL` | Category scope. Reuses the current generic dashboard name even if the UI label is “Category.” |
| `store_id` | string / `ALL` | Store scope within the selected legal entity. |
| `sku` | string / omitted | Case-insensitive SKU ID/name search. |
| `grain` | enum / `weekly` | `daily`, `weekly`, `monthly`, `quarterly`, or `yearly`. Kept separate from the existing Finance `period` date parameter. |
| `horizon_weeks` | integer / `8` | Allowed initially: `4`, `8`, `12`, `16`. |
| `detail_offset` | integer / `0` | Detail-table paging boundary for the future real dataset. |
| `detail_limit` | integer / `100` | Detail rows returned; backend should enforce a cap. |

Unknown option IDs should return `422`, an unknown/disabled agent remains
`404`, and source failures follow the existing dashboard route's `503`.

### Expected normalized response

```json
{
  "schema_version": 1,
  "agent": "retail.demand_forecasting",
  "as_of": "2026-08-06T03:00:00Z",
  "is_mock": true,
  "note": "Synthetic AI Retail 360 demonstration data.",
  "scope": {
    "legal_entity_id": "ALL",
    "category_group": "ALL",
    "store_id": "ALL",
    "sku": "",
    "grain": "weekly",
    "horizon_weeks": 8
  },
  "filter_options": {
    "legal_entities": [{ "value": "GRC", "label": "GRC · Grocery Retail" }],
    "categories": [{ "value": "GRC-C01", "label": "Fruit" }],
    "stores": [{ "value": "S001", "label": "Grocery 01 · Jakarta" }],
    "grains": ["daily", "weekly", "monthly", "quarterly", "yearly"],
    "horizons_weeks": [4, 8, 12, 16]
  },
  "kpis": [
    {
      "id": "forecast_next_7d",
      "label": "Forecast (next 7d)",
      "value": 12480,
      "unit": "units",
      "comparison_label": "all triggers on",
      "comparison_value": null,
      "direction": "flat",
      "status": "neutral",
      "sparkline": [10800, 11200, 11050, 11900]
    }
  ],
  "forecast": {
    "grain": "weekly",
    "history_count": 12,
    "horizon_weeks": 8,
    "points": [
      {
        "key": "W-1",
        "label": "W-1",
        "actual": 11320,
        "forecast": null,
        "confidence_low": null,
        "confidence_high": null
      },
      {
        "key": "W+1",
        "label": "W+1",
        "actual": null,
        "forecast": 12480,
        "confidence_low": 10982,
        "confidence_high": 13978
      }
    ],
    "summary": [
      { "id": "next_7d", "label": "Next 7d", "value": 12480, "unit": "units" },
      { "id": "accuracy", "label": "Accuracy", "value": 92.4, "unit": "%" },
      { "id": "trend", "label": "Trend", "value": 4.8, "unit": "%" },
      { "id": "peak", "label": "Peak", "value": "Saturday ×1.35", "unit": null }
    ]
  },
  "trending_items": [
    {
      "sku_id": "GRC-001",
      "sku_name": "Fruit 1",
      "predicted_uplift_pct": 31.5,
      "signals": ["viral", "growth"],
      "ads_units_per_day": 42.3
    }
  ],
  "details": {
    "total": 1,
    "offset": 0,
    "limit": 100,
    "rows": [
      {
        "sku_id": "GRC-001",
        "sku_name": "Fruit 1",
        "category_id": "GRC-C01",
        "category_label": "Fruit",
        "ads_units_per_day": 42.3,
        "forecast_units": 298,
        "trend_pct": 13.4,
        "signals": ["viral", "promo"],
        "supply_state": "Low"
      }
    ]
  }
}
```

Contract rules:

- Numeric chart/table/KPI fields are JSON numbers, never formatted strings.
- Actual-only points use null forecast/bounds; forecast-only points use null
  actual. The last actual may be repeated as an anchor only if documented.
- Confidence low must be `<= forecast <= confidence_high`.
- IDs are stable machine keys; labels are display strings.
- `scope` must echo the applied query after validation/resetting invalid
  dependent options.
- The mock provider and backend response both pass through the same frontend
  normalizer. Missing optional arrays become empty; missing required identity,
  scope, or forecast data produces a visible contract error rather than
  silently invented values.

### Backend route constraint

The current generic endpoint passes only `legal_entity_id`, calendar
`period`, and `category_group` positionally into every descriptor builder.
Store, SKU, grain, horizon, and paging are not represented. Before backend
implementation, choose one backward-compatible route-to-builder mechanism:

1. preferred: introduce a dashboard query/context object accepted by module
   builders while adapting existing builders at the route boundary; or
2. add an optional demand-specific query handler to `AgentDescriptor` while
   preserving existing builders untouched.

Do not overload Finance's calendar `period` parameter with Demand's grain.
Do not hard-code a `retail.demand_forecasting` branch in the route if a small
generic extension can support later Retail dashboards too.

### Loading, error, and empty behavior

- Initial request: shape-matched Demand skeleton with `role="status"`.
- Filter/period refetch: keep the last valid dashboard visible, set
  `aria-busy="true"`, and visually de-emphasize it to prevent layout jumps.
- Request failure: retain no stale data on initial failure; show an inline
  `role="alert"` with Retry. On refetch failure, retain the previous data and
  show a non-blocking inline error/retry message.
- Valid zero-row response: show KPIs/series only when they are meaningful and
  a clear “No SKUs match the current scope” table/board empty state.
- Ignore stale responses after filters change or the component unmounts,
  following the repository's existing cancelled-effect pattern.

## 8. Mock-to-API Migration Strategy

1. Build the UI against `loadDemandForecastingDashboard(query)`, never import
   mock data directly from a React component.
2. Keep mock and API outputs identical after normalization.
3. Default `VITE_DEMAND_FORECASTING_DATA_SOURCE` to `mock`; configure `api` in
   the backend integration environment when the endpoint is ready.
4. The backend engineer implements the route query plumbing and
   `backend/src/llm/agents/retail/demand_forecasting/dashboard.py` to return
   the documented response.
5. The descriptor changes its `build_dashboard` import from the shared empty
   Retail builder to the Demand builder. It remains
   `id="retail.demand_forecasting"` and `dashboard_only=True`.
6. Contract tests compare backend responses to required fields/invariants.
7. Switch the build-time source flag to `api`; no React presentation source
   changes should be required.

Files that should **not** change for the mock-to-API switch:

- `DemandForecastingDashboard.jsx`.
- Every Demand presentation component.
- `mockDataset.js`, `mockCalculations.js`, and `mockDashboard.js`.
- `frontend/src/agents/retail/demand_forecasting/index.js`.
- `frontend/src/App.jsx`, `AlertsPanel.jsx`, agent registry/provider, sidebar,
  Inventory Risk, and Replenishment.
- Demand CSS and component behavior tests, except adding an API-mode contract
  case if desired.

## 9. UI Implementation Plan

### Filters

- Render a namespaced toolbar inside the Demand dashboard, not in the global
  app header.
- Initialize legal entity/category/store/SKU/grain/horizon from contract
  defaults.
- Reset category/store when a parent selection makes them invalid.
- Apply select/horizon changes immediately; submit SKU search on Enter or a
  Search action to avoid a request per keystroke.
- Clear restores `ALL`, blank search, weekly grain, and eight-week horizon.
- Refresh reruns the active provider; it does not enable Agent Action or chat.

### KPI cards

- Render the six cards in an auto-fit grid using EY tokens and accessible text.
- They are read-only and must not show Workboard's AI “Insight” affordance.
- Use compact SVG/Recharts sparklines only when a real numeric series exists.
- Format units and percentages through `format.js`.

### Main forecast chart

- Use a responsive Recharts composed chart with Actual and AI Forecast lines,
  a low/high range area, a vertical actual/forecast boundary, grid, legend,
  accessible title/description, and numeric tooltips.
- Do not hard-code colors in JSX. Add Demand semantic CSS variables derived
  from the existing blue/purple/neutral token vocabulary.
- Disable or reduce animation under `prefers-reduced-motion`.

### Period selector

- Keep Daily/Weekly/Monthly/Quarterly/Yearly as a segmented control in the
  forecast panel header.
- Use buttons with `aria-pressed`; changing grain reloads the normalized
  response while retaining prior content until completion.
- Grain and horizon are independent: grain changes aggregation, horizon weeks
  controls the future range.

### Summary metrics

- Render Next 7d, Accuracy, Trend, and Peak immediately under the overview
  chart, matching the mockup's four-metric strip.
- Treat Peak as text and the other metrics as raw number + unit.

### Predicted-to-trend section

- Use a horizontal Recharts bar chart ranked by uplift descending.
- Provide an accessible fallback/list so item names, uplift, and signals are
  not available only through color or hover.
- Selecting an item sets the SKU scope and refreshes the whole Demand view.

### Forecast confidence section

- Render the fixed historical-to-future confidence panel separately from the
  period overview for initial mockup parity.
- Use backend/mock-provided bounds; no confidence math lives in the chart.
- Label the forecast horizon and actual/forecast boundary explicitly.

### Forecast detail section

- Use a semantic table with sticky header, numeric alignment, signal/status
  badges, total count, and selected grain in the forecast column title.
- Default sort is forecast descending; optional client-side sort may cover
  visible rows, but backend paging/sort semantics must be explicit before a
  real large dataset.
- Row activation updates SKU scope. Keyboard activation must match click.
- Show an empty state rather than an empty `<tbody>`.

## 10. Styling Strategy

- Adapt layout/content from the mockup, not its CSS. Do not copy `.card`,
  `.grid`, `.seg`, `.tb`, inline hex values, emojis, dark-theme rules, or the
  monolithic global selectors.
- Append one clearly labelled, namespaced Demand section to
  `frontend/src/styles.css`, for example all rules under
  `.demand-forecasting-dashboard`.
- Reuse existing variables for surfaces, borders, typography, spacing,
  radii, shadows, EY chrome, status colors, and focus outlines.
- Keep the root as `className="workboard demand-forecasting-dashboard"` so it
  occupies the existing shell canvas and inherits scrolling/min-size behavior.
  Override the generic four-row grid with a Demand-owned vertical layout only
  inside that namespace.
- Use container queries against the board's actual width, as `Workboard`
  already does, so the layout responds correctly when sidebar/chat widths
  change. Planned breakpoints: six-to-three/two KPI columns, two charts to one
  column, then horizontally scrollable detail table.
- Reuse `.workboard-status` semantics for errors/empty copy and `Skeleton`
  primitives for loading, but create layout-specific wrappers.
- Preserve the existing topbar and sidebar styling. The Demand component must
  not render another `Retail / Demand Forecasting` header.

## 11. Testing Plan

### Direct dashboard/component tests

- Default mock load renders six KPI labels, both forecast panels, summary
  metrics, predicted ranking, and detail rows.
- Initial pending state renders the Demand skeleton.
- Initial rejected load renders an alert and Retry; Retry reloads.
- Refetch keeps existing content with `aria-busy` and ignores stale responses.
- Valid empty data renders a clear empty state.
- Period buttons update `grain` and selected styling/`aria-pressed`.
- Legal entity change resets incompatible category/store selections.
- SKU search and clear produce the expected provider query.
- Trending-item/detail-row activation scopes the selected SKU.
- Chart inputs keep actual/forecast/bounds as numbers or null.

### Mock calculation/provider tests

- Same query returns deterministic output.
- Forecast, trend, accuracy, risk, trending, seasonality, uplift, and confidence
  invariants match the documented mock formulas.
- Filtering reduces rows and all KPI/chart/table aggregates reconcile to the
  same filtered scope.
- Horizon changes point count and illustrative accuracy in the expected
  direction.
- Every forecast bound brackets its forecast value.
- Mock and API payload fixtures normalize to the same shape.
- Invalid provider mode fails clearly rather than silently calling an
  unintended endpoint.

### Shell/module isolation tests

- Update `App.test.jsx` so Demand renders its populated custom dashboard.
- Inventory Risk and Replenishment still render the empty shared dashboard.
- Retail count remains three and canonical IDs/active-card behavior are
  unchanged.
- Header remains small grey `Retail` plus large white `Demand Forecasting`.
- Ask Demand label remains and textarea/Send remain disabled.
- No alerts/actions/monitoring/chat API calls are made for any Retail module.
- Formula Manager, What If Simulator, and Data Source assertions continue to
  pass.

### Verification

- `npm test`.
- `npm run build`.
- Backend contract tests when the future endpoint is implemented.
- Manual responsive check with sidebar open/closed and disabled chat panel
  open/closed, including keyboard focus and reduced motion.

## 12. Files Expected to Be Created

### Frontend implementation

- `frontend/.env.example` — documents the build-time mock/API source flag.
- `frontend/src/agents/retail/demand_forecasting/DemandForecastingDashboard.jsx`.
- `frontend/src/agents/retail/demand_forecasting/DemandForecastingDashboard.test.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/DemandForecastFilters.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/DemandKpiGrid.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/ForecastOverviewPanel.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/ForecastConfidencePanel.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/ForecastLineChart.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/PredictedTrendPanel.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/ForecastDetailTable.jsx`.
- `frontend/src/agents/retail/demand_forecasting/components/DemandForecastingSkeleton.jsx`.
- `frontend/src/agents/retail/demand_forecasting/data/contract.js`.
- `frontend/src/agents/retail/demand_forecasting/data/dashboardData.js`.
- `frontend/src/agents/retail/demand_forecasting/data/mockDataset.js`.
- `frontend/src/agents/retail/demand_forecasting/data/mockCalculations.js`.
- `frontend/src/agents/retail/demand_forecasting/data/mockCalculations.test.js`.
- `frontend/src/agents/retail/demand_forecasting/data/mockDashboard.js`.

### Later backend integration

- `backend/src/llm/agents/retail/demand_forecasting/dashboard.py` — real
  dashboard builder returning the normalized contract.
- `backend/tests/test_demand_forecasting_dashboard.py` — query, contract,
  reconciliation, empty, and error tests.

## 13. Files Expected to Be Modified

### Frontend implementation

- `frontend/src/agents/retail/demand_forecasting/index.js` — import the new
  Demand component; keep `id` and `chatLabel` unchanged.
- `frontend/src/styles.css` — add namespaced Demand dashboard rules using
  existing tokens and container patterns.
- `frontend/src/i18n.js` — add Demand labels to the existing EN/ID dictionary.
- `frontend/src/App.test.jsx` — replace the “Demand is empty” assertion with
  populated Demand assertions while retaining blank Inventory/Replenishment
  and disabled-chat checks.

No change is expected in `App.jsx`, `AlertsPanel.jsx`, `AgentsProvider`, the
registry, Inventory Risk, Replenishment, shared `RetailDashboard`, or
`frontend/src/api/dashboard.js`.

### Later backend integration

- `backend/src/llm/agents/retail/demand_forecasting/__init__.py` — point
  `build_dashboard` at the Demand builder; preserve canonical metadata and
  `dashboard_only=True`.
- `backend/src/api/finance_agents_html.py` and possibly
  `backend/src/llm/agents/descriptor.py` — add a generic, backward-compatible
  way to pass Demand query context to the builder.
- `backend/tests/test_retail_module.py` — Demand is no longer expected to
  return the structural empty payload; Inventory/Replenishment still are.

`backend/src/llm/agents/modules.py` must not change.

## 14. Risks / Open Questions

1. **Two similar forecast charts:** the mockup renders both a period-aware
   overview and a separate weekly confidence chart. The plan preserves both
   for parity, but product design should confirm whether consolidation is
   preferred before implementation.
2. **Extent of Agent 1 parity:** category/store/cluster/legal-entity
   breakdowns and the what-if/compare sections are appended by the mockup's
   shared shell. They are deliberately deferred here. Confirm if they are
   required in the first Demand release.
3. **Backend builder query contract:** the current descriptor builder accepts
   only three positional filters. Approve a generic query/context extension
   before the backend engineer implements store/SKU/grain/horizon support.
4. **First frontend environment flag:** a Vite build-time source flag gives a
   zero-code mock/API switch, but this repo has no frontend env convention.
   If deployment prefers no build flags, replace it with one explicit provider
   export in `dashboardData.js`; only that file would change at cutover.
5. **Synthetic fidelity versus bundle size:** copying the entire mock engine
   would be large and hard to validate. Approve a smaller deterministic
   representative dataset that preserves Demand formulas and interactions,
   not every generated SKU/store from the standalone demo.
6. **Detail paging/sorting:** the mockup renders all scoped rows client-side;
   real data should page server-side. Confirm expected maximum row count and
   whether v1 needs paging controls or only a capped top-100 table.
7. **Localization scope:** the app already offers EN/ID. The plan includes
   Demand labels in `i18n.js`; backend-provided category/store/SKU names should
   remain data and should not be translated by the frontend.
8. **Confidence semantics:** +/-12% is illustrative mock behavior, not a
   statistical model. The backend must later supply calibrated bounds and
   confidence metadata; the UI must not present the mock range as measured
   uncertainty.

## 15. Implementation Sequence

1. Approve the open decisions: two charts versus consolidation, dimension/
   what-if scope, env flag versus fixed provider, and table paging depth.
2. Add JSDoc contract constants/normalizer and write contract invariants.
3. Add the deterministic Demand mock dataset and pure calculation functions;
   test formulas, filters, reconciliation, and confidence bounds.
4. Add the async data gateway with mock default and API branch through the
   existing `fetchDashboard` client.
5. Build the dashboard shell and shape-matched loading/error/empty states.
6. Implement filters and request lifecycle, including dependent resets,
   stale-response guards, refresh, and clear.
7. Implement the six KPI grid using shared formatting and language state.
8. Implement the shared Recharts forecast core, then the period-aware overview
   and summary metrics.
9. Implement the confidence panel, actual/forecast boundary, tooltip, and
   range legend.
10. Implement predicted-to-trend ranking and scope interaction.
11. Implement the detail table, sorting/empty behavior, and SKU scope action.
12. Add namespaced responsive/accessibility styling to `styles.css`.
13. Update only the Demand override to use the new component; verify Inventory
    Risk and Replenishment remain blank.
14. Update App isolation tests and run the complete frontend test/build suite.
15. In the later backend phase, implement the agreed query plumbing and Demand
    builder, run backend contract tests, then switch the environment to API
    mode without changing presentation components.
