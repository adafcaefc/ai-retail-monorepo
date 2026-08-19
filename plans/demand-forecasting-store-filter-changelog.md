# Demand Forecasting Store Filter Changelog

Date: 2026-08-14

## Resolution

The Demand Forecasting Store filter now uses the existing canonical contract:

```text
Frontend query.store_id
  → GET /api/html/dashboard/retail.demand_forecasting?store_id=S001
  → DashboardScope.store_id == "S001"
  → retail.dim_store.store_id = fact_inventory_daily.store_key
  → Store-scoped Store × SKU inputs
  → frontend aggregation and rendering
```

The primary bug was that `DashboardScope` received `store_id`, but Demand
Forecasting declared it unsupported. Its SQL then returned unscoped chain rows,
and the route reported `ignored_filters: ["store_id"]`. The fix adds Store
support to the Demand Forecasting descriptor and applies the Store predicate at
the data-query level.

## Files changed

- `backend/src/llm/agents/retail/common/warehouse.py` — allows `_scope_clause`
  callers to provide a real Store dimension column and bind `store_id`.
- `backend/src/llm/agents/retail/demand_forecasting/dashboard.py` — declares
  Store support, selects Store-grain rows for a Store request, returns the
  normalized scope, and reports non-Store-grain limitations.
- `backend/tests/test_dashboard_scope.py` — parser and SQL-scope assertions.
- `backend/tests/test_retail_module.py` — Demand-specific supported-filter
  contract assertion.
- `backend/tests/test_demand_forecasting_store_scope.py` — builder, SQL
  listener, and HTTP integration regressions for All/S001/S002.
- `frontend/src/agents/retail/demand_forecasting/data/contract.js` — preserves
  `scope_limitations` at the feature boundary.
- `frontend/src/agents/retail/demand_forecasting/data/selectors.js` — carries
  backend scope limitations through the row-to-dashboard transformation.
- `frontend/src/agents/retail/demand_forecasting/DemandForecastingDashboard.jsx`
  and `frontend/src/styles.css` — display explicit Store-scope limitations.
- `frontend/src/agents/retail/demand_forecasting/data/dashboardData.test.js` —
  verifies the existing `store_id` HTTP parameter is sent unchanged.
- `plans/demand-forecasting-backend-handoff.md` — preserves the investigation
  and adds its implementation/resolution record.

## Store-grain headline KPI source

All Stores continues to use `retail.fact_inventory_chain_daily` because its
800-row chain-net forecast is the existing headline KPI definition and sums to
`1,656,178.21602674`. The seed semantics explicitly warn that summing Store
rows does not reproduce chain facts because Store rows are rounded and chain
state is calculated independently.

For a selected Store, the chosen source is
`retail.fact_inventory_daily.forecast_7d`, the ENGINE_STORE f08 forecast at
Store × SKU grain. It preserves the meaning of the existing seven-day forecast
while making the Store scope real; it is not a new metric inferred from the
chain total. The query also uses the same rows' ADS, inventory, open PO,
position, ROP, and state fields, so downstream calculations share the same
Store scope.

## Query behavior

Before:

```sql
-- Chain item query: no Store key exists in this source.
FROM retail.fact_inventory_chain_daily c
WHERE c.cal_date = %(day)s

-- Store dimension query: Store join existed, but no Store predicate.
FROM retail.fact_inventory_daily f
JOIN retail.dim_store s ON s.store_id = f.store_key
WHERE f.cal_date = %(day)s
```

After a Store selection:

```sql
FROM retail.fact_inventory_daily f
JOIN retail.dim_store s ON s.store_id = f.store_key
JOIN retail.dim_item i ON i.item_id = f.item_key
JOIN retail.dim_vertical vt ON vt.vertical_id = i.vertical_id
WHERE f.cal_date = %(day)s
  AND s.store_id = %(store_id)s
```

The live SQL capture bound `store_id=S001` and `store_id=S002` respectively.
All Stores retains the chain query and does not receive a fake Store predicate.

## Behavior before vs. after

| Case | Before | After |
| --- | --- | --- |
| All Stores | 800 chain items, 160 Store rows, forecast `1,656,178.21602674` | Same chain-scoped result |
| S001 | `ignored_filters=["store_id"]`, 800 chain items, 160 Store rows, chain KPI | 100 S001 rows, one S001 dimension, forecast `25,948.94103250092` |
| S002 | `ignored_filters=["store_id"]`, 800 chain items, 160 Store rows, chain KPI | 100 S002 rows, one S002 dimension, forecast `30,756.578276753906` |

S001 and S002 now produce different results at the source-row and aggregate
levels.

## Intentionally non-Store-scoped fields

- Actual demand/history remains unavailable because the loaded sales-history
  table has no rows; forecast points keep `actual: null`.
- Accuracy/MAPE and demand trend remain vertical-level workbook constants; no
  Store-grain backtest source exists.
- Seasonality remains vertical-level because `fact_gmv_monthly` has no Store
  key.

The backend returns these limitations as `scope_limitations`, and the frontend
shows them in the Store-scoped view.

**Resolved**: the predicted-to-trend count used to be listed here too — it
stayed a vertical-level reference value while the ranked items were
Store-scoped, so a Store's row count below that reference value meant every
row in the Store got marked trending. `is_trending` is now a per-row formula
(`viral OR growth > 1.25`) that needs no vertical-wide count, so it is
correctly computable at Store/category grain and is no longer a limitation.

## Tests and validation

Commands/results:

- `PYTHONPATH=. ../.venv/bin/pytest -q tests/test_dashboard_scope.py tests/test_retail_module.py tests/test_retail_dashboard_builders.py tests/test_dashboard_route_scope.py tests/test_demand_forecasting_store_scope.py` — **58 passed** in the seeded environment.
- `PYTHONPATH=. ../.venv/bin/pytest -q tests/test_demand_forecasting_store_scope.py` — **4 passed**, including the actual SQL predicate/bound-parameter listener.
- `npm test -- src/agents/retail/demand_forecasting` — **30 passed**.
- `python3 -m py_compile backend/src/llm/agents/retail/common/warehouse.py backend/src/llm/agents/retail/demand_forecasting/dashboard.py` — passed.

Live HTTP capture against the seeded Postgres snapshot (`2026-07-01`):

| HTTP request | Scope / ignored filters | Returned dimensions | Forecast KPI |
| --- | --- | --- | ---: |
| `/api/html/dashboard/retail.demand_forecasting` | `{}` / none | 160 Store IDs | 1,656,178.21602674 |
| `...?store_id=S001` | `{"store_id":"S001"}` / none | S001 only; 100 item rows | 25,948.94103250092 |
| `...?store_id=S002` | `{"store_id":"S002"}` / none | S002 only; 100 item rows | 30,756.578276753906 |
