# Demand Forecasting frontend data contract

The production dashboard handoff remains:

```http
GET /api/html/dashboard/retail.demand_forecasting
```

Supported query fields are `legal_entity_id`, `category_group`, `store_id`,
`sku`, `grain`, `horizon_weeks`, `detail_offset`, and `detail_limit`.

Schema version 2 extends the Phase 1 normalized response with:

- `dimensions.categories`, `dimensions.stores`, `dimensions.clusters`,
  `dimensions.legal_entities`, `dimensions.seasonality`, and
  `dimensions.chain_total`;
- `simulation.levers`, `simulation.baseline`, `simulation.scenario`,
  `simulation.scenario_levers`, and `simulation.baseline_forecast`;
- `scenarios`, shaped as local scenario metadata and forecast series; and
- `suggested_actions.primary`, `suggested_actions.secondary`, and the
  read-only `suggested_actions.plan_preview`.

All dimension `forecast_units` values are raw seven-day numbers. Category,
store, cluster, and legal-entity rows must each sum to
`dimensions.chain_total`, which must equal the scoped `forecast_next_7d` KPI.

Forecast Detail uses the selected grain. Weekly Detail is a seven-day period,
so its full-result `forecast_total_units` reconciles directly to the next-7d
KPI even though only the first 100 rows are returned. Daily, Monthly,
Quarterly, and Yearly Detail represent their own selected periods and must not
be forced to equal the seven-day KPI. Each Detail row also carries an explicit
`forecast_7d_units` value for consumers such as the seven-day forecast basket;
that field does not change when the display grain changes.

## Future simulation backend TODO

Phase 2 simulation is intentionally mock-only. No backend route is defined by
this frontend work. A future backend design should accept the normalized
dashboard query plus the six lever values (`demand`, `promo`, `markdown`,
`inbound`, `lead`, `safety`) and return the same schema-version-2 dashboard
contract, including baseline/scenario metrics and series. Until that contract
is approved, API mode reports simulation integration as pending and never
falls back to an action, chat, or generic simulator endpoint.

Saved scenarios remain browser-session React state in this phase; persistence
and cross-user sharing are not implied by the response schema. Every local
scenario stores its six-field dashboard context (Legal Entity, Category,
Store, SKU, grain, and horizon) plus its baseline and scenario series. Only
context-compatible scenarios are compared. Although schema version 2
normalizes a `payload.scenarios` field for forward compatibility, server
scenarios are not hydrated into Compare Scenarios in this phase.

API mode validates the Phase 2 dimensions, simulation metadata, and suggested
actions before normalization. Missing required fields are contract errors,
not successful empty panels. Locally saved scenarios are deliberately not a
required server field.
