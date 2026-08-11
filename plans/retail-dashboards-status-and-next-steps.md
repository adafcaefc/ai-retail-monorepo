# Retail Dashboards — Status, Data Basis, and Next Steps

Status of the three Retail modules as of **11 August 2026**, what data each one
actually stands on, and what has to happen before any of them can serve real
figures. Written for two people working in parallel: one on Demand Forecasting,
one on Inventory Risk.

Companion to [`demand-forecasting-dashboard-frontend.md`](./demand-forecasting-dashboard-frontend.md),
which covers Demand's frontend design rather than the cross-module picture.

---

## 1. Where we are

| Module | UI | Data behind it | Backend builder |
|---|---|---|---|
| `retail.demand_forecasting` | Complete | **Invented in code** | None — shared empty stub |
| `retail.inventory_risk` | Complete | **Workbook, reconciled** | None — shared empty stub |
| `retail.replenishment` | Empty shell | — | None — shared empty stub |

Both finished boards are frontend-only. Neither reads PostgreSQL, and neither
touches D365. Test suites are green: 68 frontend, 348 backend.

Inventory Risk landed in `5003bcd`: six KPIs, at-risk-by-state and category
value panels, dimension charts, expiry timeline, and a paged risk register over
800 SKUs.

### The one asymmetry that matters

Demand and Inventory look equally finished, but they rest on very different
ground:

- **Inventory Risk** reads figures the workbook already computed, and the build
  script *reconciles* them against the workbook's own `A2 Inventory Risk` sheet
  before writing. A mismatch aborts the build.
- **Demand Forecasting** invents every figure — entities, stores, categories,
  item names, and the KPI series are literals in `mockDataset.js` and
  `mockDashboard.js`.

That was a reasonable call when the assumption was that no forecast data
existed. Section 4 shows the assumption was too strong.

---

## 2. Endpoints

### What exists

One generic route serves every agent:

```
GET /api/html/dashboard/{canonical_agent_id}
```

It resolves today for both modules, and returns the same empty payload for
each, because both descriptors point at the same 22-line stub
(`src/llm/agents/retail/retail/dashboard.py`):

```json
{"agent":"retail","default_view":"","kpis":[],"views":{},"side":{},"filters":[],"simulator":null}
```

Note `"agent":"retail"` — not the canonical id. Both frontend contracts reject
a payload whose `agent` does not match, so flipping either board to `api` today
fails at the contract boundary rather than rendering an empty board.

There is **no chat endpoint** for either module: both descriptors set
`chat_agent=""` and `dashboard_only=True`.

### What Inventory Risk needs from it

`loadInventoryRiskDashboard` in `data/dashboardData.js` is the single seam where
the source is chosen — `DATA_SOURCE = "fixture"` today. Both branches return the
same normalized contract, so the cutover touches no component, selector, or test.

`serializeScope` already emits the query the backend would have to honour, with
`ALL` and empty search dropped:

| Key | Supported by the route today |
|---|---|
| `legal_entity_id` | yes |
| `category_group` | yes |
| `store_id` | **no** |
| `state` | **no** |
| `sku` | **no** |

Demand needs `store_id` and `sku` too, plus `grain`, `horizon_weeks`,
`detail_offset`, `detail_limit`.

### The hazard to fix first

`fetchDashboard` serializes *any* key it is given into the query string, but the
route declares exactly three `Query(...)` params and forwards them
**positionally**:

```python
build_dashboard(scoped_entity_id, scoped_period, scoped_category_group)
```

So an unrecognised parameter is **silently dropped** — no error, no warning, a
200 response with unfiltered data. This is the failure mode to design out before
either builder is written.

It is also why this one change cannot be made by two people at once. If Demand
adds `grain`/`horizon_weeks` as positional slots 4 and 5 while Inventory adds
`store_id`/`state` as slots 4 and 5, git merges both cleanly and the same slot
then carries two different meanings. That is a silent wrong-data bug, not a
merge conflict.

**Proposal:** replace the positional signature with a single scope object —
`build_dashboard(scope: dict)` — each agent reading the keys it understands and
ignoring the rest. The frontend already speaks this shape on both sides; only
the backend is the bottleneck. One person takes it, before any builder work.

---

## 3. Dimensions, and what they are based on

### Provenance

```
Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx
  → scripts/extract_workbook_schema.py
  → resources/dbtemp/schema_with_data.json     30 tables, 21,939 rows
  → scripts/build_inventory_risk_fixture.py    (reconciles, then writes)
  → frontend/src/agents/retail/inventory_risk/data/fixture.json
```

### What Inventory Risk uses

| Dimension | Count | Shape | Source table |
|---|---:|---|---|
| Legal entity | 8 | `GRC`, `GMR`, `FSH`, `HNB`, `ELC`, `HNL`, `DGT`, `OMN` | `verticals` |
| Category | 160 | `DGT-C01` + label, scoped to an entity | `categories` |
| Store | 160 | `S001` + label + cluster, scoped to an entity | `stores` |
| State | 6 | Stockout, Low, Expiry, Overstock, Slow-mover, Healthy | derived in the build script |
| SKU rows | 800 | — | `sku_master` × `engine_store` |

The six states are resolved **once, in Python**, along with the KPI predicates
(`DoS > 15`, `growth < 1.0`, `Position < ROP`). No threshold is allowed to exist
in JavaScript: a second copy of a rule is a rule that will silently drift.

### Demand Forecasting's dimensions disagree

| | Demand (invented) | Workbook |
|---|---|---|
| Legal entity | `GRC`, `FSH`, `HBA`, `HME` (4) | 8, listed above |
| Category | `"Fresh Produce"`, `"Beverages"` | `DGT-C01`, `DGT-C02`, … |
| Store | `"Jakarta"`, `"Bandung"` | `S001`, `S002`, … |

Only `GRC` and `FSH` overlap. `HBA` and `HME` do not exist in the dataset, so
they will return empty rather than error once real data lands.

This matters beyond cosmetics. Dimension values are join keys: a future
cross-module feature ("this SKU is trending **and** at stockout risk") is only
possible if the codes are identical on both sides.

**Rule to adopt: mock numbers are fine, mock dimensions are not.** Where the
workbook already has the answer, use it.

### A KPI both modules must agree on

`stockout_risk_skus` appears in **both** `a1_demand_forecasting` and
`a2_inventory_risk`, with identical values across all eight verticals
(46, 31, 39, 42, 35, 32, 40, 37).

Inventory reads it from the fixture; Demand invents it. They are therefore
guaranteed to disagree on screen. Same word, same user, two numbers.

---

## 4. What the workbook can and cannot support

The premise that "forecast data does not exist yet" is too strong. It exists —
just not as a time series.

**It does have** `a1_demand_forecasting`, one row per vertical, whose six
columns map 1:1 onto the six KPIs Demand currently invents:

| Demand KPI | Workbook column | Grocery |
|---|---|---|
| `forecast_next_7d` | `forecast_7d` | 442,050 |
| `forecast_accuracy` | `accuracy_pct` | 92.4 |
| `demand_trend` | `trend_pct` | 5.6 |
| `stockout_risk_skus` | `stockout_risk_skus` | 46 |
| `predicted_to_trend` | `trending_skus` | 47 |
| `seasonality_index` | `seasonality_idx` | 114 |

`engine_store` also carries `ads`, `forecast_7d` and `seas` per SKU × store,
and `sku_master` carries `growth`, `elasticity`, `viral` and `comp_idx`.

**It does not have a usable time axis.** Of all 30 tables, exactly one has a
real one:

```
time_series_24mo — 192 rows = 24 months × 8 verticals, GMV only
```

No SKU, no category, no store. Everything else that looks temporal
(`lead_time_d`, `demand_day`, `weekly_gmv`, `contribution_day`, `peak_month`)
is a per-row scalar, not a series. And `forecast_7d` is a single scalar per
SKU × store, not a curve.

Demand's UI already promises 5 grains × 4 horizons with a confidence band per
SKU. The workbook cannot supply that at any granularity finer than monthly GMV
per vertical.

**Consequences:**

- Demand can stop mocking the six KPIs, the trending list, and all dimensions.
- Demand must keep mocking the forecast series and confidence band.
- Inventory Risk needs nothing further from D365 to reach a real backend — the
  figures are already in `schema_with_data.json`.
- One caveat: `accuracy_pct` is 92.4 for all eight verticals. That is a demo
  constant, not a backtest, so `is_mock: true` stays even for workbook figures.

### The one thing to ask D365 for

Not "forecast data" — that request is too vague to fill. Specifically:

> Historical sales as a time series at **SKU × store × day**, at least 24 months
> back. The workbook only has monthly GMV per vertical (192 points), which is
> not enough to forecast at SKU level.

---

## 5. Next steps

| # | Work | Owner | Blocked by D365? |
|---|---|---|---|
| 1 | Scope-object route (section 2) | one person, alone | No |
| 2 | Align Demand's dimensions to the workbook | Demand | No |
| 3 | Wire Demand's six KPIs to `a1_demand_forecasting` | Demand | No |
| 4 | Inventory Risk backend builder | Inventory | No |
| 5 | Demand backend builder | Demand | **Yes** — needs the series |
| 6 | Replenishment dashboard | unassigned | Partly (`a3_replenishment` exists) |

Items 2–4 can run in parallel once item 1 lands. Item 5 is the only one that
genuinely waits.

### Shared files to coordinate on

Both boards write into the same global files. Prefix conventions are already in
place (`demand-*`, `risk-*`); the discipline is to append in your own section
and not edit the other's blocks.

- `frontend/src/styles.css` — the most frequent conflict source
- `frontend/src/i18n.js`
- `frontend/src/App.test.jsx` — has already conflicted twice
- `backend/src/llm/agents/modules.py`
- `backend/src/llm/agents/retail/retail/dashboard.py` — **one stub currently
  shared by both descriptors.** Split it before either side fills it in.

---

## 6. Invariants worth keeping

1. **One place decides the source.** Components import
   `load<Module>Dashboard` and never touch a fixture, a selector, or `fetch`.
2. **Rules live in one language.** Thresholds and classifications are resolved
   where the data is prepared, not recomputed in JavaScript.
3. **Reconcile before writing.** The fixture build checks itself against the
   workbook and aborts on mismatch. Do not weaken that to a warning.
4. **Label the source honestly.** `is_mock` and a plain-language note, so a
   demo figure is never mistaken for a live ERP position.
5. **Don't grow a third copy of a rule.** When the Inventory Risk backend
   builder is written, the fixture script should call it — not restate its
   thresholds.
