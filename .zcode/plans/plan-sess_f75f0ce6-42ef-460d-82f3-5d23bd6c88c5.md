## Agent 4 — Promotion Effectiveness (full agent: backend + chat + monitoring + frontend)

### Confirmed understanding
- **Agent 4 = Promotion Effectiveness** (`resources/A4_Promotion_Effectiveness_Dashboard_Spec.md`), the next retail agent after A1 (demand), A2 (inventory_risk), A3 (replenishment). Canonical id: `retail.promotion_effectiveness`.
- The promo source data **exists in the workbook JSON export** (`resources/dbtemp/schema_with_data.json`) as two tables: `a4_promotion` (8 rows, per-vertical KPIs) and `promotion_discount_detail` (48 campaign rows). It is also loaded generically into the **`newdata`** schema by `import_new_dataset.py` (this is the "I added all the json as table" you remembered) — **but the retail agents (A1/A2/A3) do not read `newdata`; they read the curated `retail` schema.** The promo tables are not currently seeded into `retail`.
- The promo incremental-margin formula `f13-incremental-promotion-margin` already exists in `retail.formula`. `fact_inventory_chain_daily` carries `margin_rp`/`funding_rp`; `dim_item` carries `is_promo_eligible`, `cannibalisation_pct`, `margin_pct`, `price`, `base_ads`.

**Decision:** Seed the two promo tables into the `retail` schema (consistent with A1/A2/A3) so A4 reads the same curated schema as its siblings — no cross-schema dependency on the generic `newdata` load.

---

### Phase 1 — Data layer (seed promo tables into the `retail` schema)

**1a. `scripts/create_retail_schema.py`** — add two `CREATE TABLE IF NOT EXISTS` statements:
- `retail.promotion_detail` (PK `promo_id`) with columns matching `promotion_discount_detail`: `promo_id, promo_name, discount_type, scope, vertical_label, target_category, season, peak_month, mechanism, discount_pct, value_rule, min_qty_threshold, supplier_funding_pct, expected_uplift_pct, pre_buy_uplift_units, valid_from, valid_to, d365_construct`.
- `retail.promotion_vertical_kpi` (the `a4_promotion` sheet, one row per vertical): `vertical_label, active_promo_skus, uplift_pct, incremental_margin, roi_x, cannib_pct, funding_pct`.

**1b. `scripts/seed_retail_facts_from_json.py`** — add:
- `build_promotion_detail(tables)` reading `tables["promotion_discount_detail"]`.
- `build_promotion_vertical_kpi(tables)` reading `tables["a4_promotion"]`.
- A 4th entry in `build_agent_kpi_reference`'s `sheets` dict: `"retail.promotion_effectiveness": ("a4_promotion", ("active_promo_skus","uplift_pct","incremental_margin","roi_x","cannib_pct","funding_pct"))` — so `agent_reference(connection, AGENT_ID)` returns the A4 reconciliation anchors exactly as A1/A2/A3 do.
- Wire both builders into the seed `main()` (upsert into the two new tables).

> These scripts are idempotent (`CREATE TABLE IF NOT EXISTS` + upsert). Running them populates the new tables; existing tables are untouched.

---

### Phase 2 — Backend agent folder (`backend/src/llm/agents/retail/promotion_effectiveness/`)

Mirror the A2/A3 structure exactly.

**2a. `tools/promotion_data.py` + `tools/__init__.py`** — the snapshot tool:
- `get_promotion_effectiveness_snapshot(legal_entity_id, category_group)` returning the standard envelope via `retail.common.snapshot.envelope(...)` plus: `totals` (chain rollups), `by_vertical` (the 6 A4 KPIs per vertical joined from `retail.promotion_vertical_kpi` + `fact_inventory_chain_daily`), `campaigns` (bounded top-N from `retail.promotion_detail`), `largest_margin_skus` (top-N promo-eligible SKUs by `f13`-style margin from `fact_inventory_chain_daily` JOIN `dim_item`), `by_channel`/`by_cluster`/`by_category` rollups, `funding_gaps` and `pre_buy_required` classified groups (per the spec's `promoClassify` logic), and `reference_by_vertical`.
- `TOOLS = {"get_promotion_effectiveness_snapshot": get_promotion_effectiveness_snapshot}`.

**2b. `dashboard.py`** — `build(scope)` + `ENGINE_FORMULAS` + `SUPPORTED_FILTERS`. Returns the payload the React board aggregates (rows + reference + formulas + filter_options), following the A2/A3 `build()` pattern (`warehouse`/`snapshot` helpers, `_scope_clause`). `ENGINE_FORMULAS` includes `f01-ads-per-store` and `f13-incremental-promotion-margin`.

**2c. `__init__.py`** — `DESCRIPTOR = AgentDescriptor(...)` with `db_domain="retail_promotion"`, `chat_agent="retail.promotion_effectiveness.chat"`, 3 `MonitoringPass`es (ROI/value, funding-gap, pre-buy/cannibalization), `import_agent_name="retail_dataset"`, `allowed_tables=PROMOTION_ALLOWED_TABLES`.

**2d. `config/retail_promotion_effectiveness_chat.json`** — the **chat agent** (`retail.promotion_effectiveness.chat`, `MessagesInput`→`FinanceAgentOutput`). Tools: snapshot, `query_retail_promotion`, formula tools, alert/action tools. System prompt modeled on the replenishment chat prompt: promo economics (uplift vs margin quality, ROI, cannibalization, supplier funding), the two-uplift-meanings caveat, the dataset single-day/empty-tables caveats, units, dashboard layout resolution, and the `{{constants.*}}` footers.

**2e. `config/retail_promotion_effectiveness_monitoring.json`** — the **monitoring agents** (3 passes: `monitoring.margin_quality`, `monitoring.funding`, `monitoring.prebuy_cannib`) + `retail.promotion_effectiveness.simulation` + `retail.promotion_effectiveness.action`, all referencing `{{constants.RETAIL_MONITORING_OUTPUT_PROMPT}}` and the sim/execute shared prompts, mirroring the replenishment monitoring config.

---

### Phase 3 — Wire into shared registries

**3a. `backend/src/llm/agents/common/tools/freeform_query.py`**:
- Add `PROMOTION_ALLOWED_TABLES = (*RETAIL_SHARED_TABLES, "retail.promotion_detail", "retail.promotion_vertical_kpi", "retail.fact_inventory_chain_daily", "retail.dim_item")`.
- Add `"retail_promotion": PROMOTION_ALLOWED_TABLES` to `DOMAIN_ALLOWED_TABLES`.
- Add `query_retail_promotion` + `describe_retail_promotion_tables` (same shape as the other retail query/describe fns) and register them in `LOCAL_FREEFORM_QUERY_TOOLS` + `__all__`.

**3b. `backend/src/llm/agents/common/config/subagents.json`** — add `"retail_promotion"` to the `agent` literal `choices` in `ActionSpec`, `SimulationInput`, `ExecuteActionInput`.

**3c. `backend/src/llm/agents/modules.py`** — add `"retail.promotion_effectiveness"` to `ENABLED_MODULES` (after replenishment).

---

### Phase 4 — React frontend board (`frontend/src/agents/retail/promotion_effectiveness/`)

Mirror `inventory_risk/` structure (the closest sibling):
- `index.js` (`{ id, chatLabel: "Promotion", dashboardComponent }`).
- `PromotionEffectivenessDashboard.jsx` + `.test.jsx` (KPI grid, main combo chart, two margin charts, promo calendar table, dimension charts, what-if simulator, scenario comparison, suggested-best-action tabs).
- `components/` — `PromoKpiGrid`, `PromoKpiDrilldown`, `PromoCalendarTable`, `MarginByVerticalChart`, `MarginByChannelChart`, `DimensionCharts`, `PromoWhatIfSimulator`, `PromoScenarioComparison`, `SuggestedBestAction` (High ROI / Funding Gap / Pre-buy tabs), `PromotionEffectivenessFilters`, `PromotionEffectivenessSkeleton`.
- `data/` — `contract.js`, `dashboardData.js`, `selectors.js` (+ test), `engine.js` (+ test), `drilldown.js`, `fixture.json` (generated from the backend payload via a `build_promotion_effectiveness_fixture.py` script mirroring the A1/A2/A3 fixture builders, so `test_retail_dashboard_builders.py` parity holds).

---

### Phase 5 — Tests / verification
- Extend `backend/tests/test_retail_fact_seed.py` with promo-table row-count/column assertions.
- Add `test_retail_dashboard_builders.py` coverage for the A4 payload vs fixture (byte-parity), matching how A1/A2/A3 are locked.
- Add `selectors.test.js` / `engine.test.js` for the new frontend data layer.

---

### Notes / honesty caveats baked into the prompts (from the spec's "Catatan kritis")
- ROI is a stored KPI; no separate promo-investment column is exposed (derive `investment = incremental_margin / roi` only when asked, label it derived).
- "Uplift" has two meanings: modeled net uplift (~25.6%, chain KPI) vs campaign planned uplift (~46.8%, per-campaign). UI labels distinguish them.
- Incremental margin is store/chain-level gross; inventory-state chart uses inventory value, not incremental margin — does not tie to the headline.
- `fact_promotion`/`fact_sales_daily`/`fact_price_daily` remain empty by design — report unavailable rather than substituting.

### Out of scope (not requested, available as follow-ups)
- D365 Commerce discount activation / `submitERP('promo')` — the action agent is approval-only like A3.
- Compare-Scenarios CSV export beyond the shared simulator.

I'll implement in the phase order above (data layer → backend → registries → frontend → tests), running the existing retail tests as I go to keep parity.