# Agent 5 · Pricing & Markdown — frontend design

**Date:** 2026-08-15
**Status:** Approved for planning
**Scope:** First of five sequential builds (A5 → A6 → A7 → A8 → A9) that bring the
Retail suite's remaining placeholder agents up to the standard already set by
A1–A4. This document covers **only A5, Pricing & Markdown**. A6–A9 each get
their own spec when their turn comes.

## Why this agent, why now

The Retail sidebar carries nine agents from the mockup
(`resources/AI_360_Retail_Suite_v8.2_General_9Agents 20260806.html`) and nine
matching spec docs (`resources/A1..A9_*_Dashboard_Spec.md`). A1–A4 (Demand
Forecasting, Inventory Risk, Replenishment, Promotion Effectiveness) are fully
built: real backend tools plus a frontend that can also run standalone off a
checked-in fixture. A5–A9 are `dashboard_only=True` navigation stubs
(`backend/src/llm/agents/retail/common/placeholder.py`) with nothing behind
them.

This build is **frontend only**, matching the explicit request: build the
board against a JSON fixture now, wire it to a live backend later. No backend
files are touched in this pass.

## Non-goals

- No backend `AgentDescriptor`, no `tools/`, no `config/`, no Postgres/Azure
  SQL query of any kind. `backend/src/llm/agents/retail/pricing_markdown/`
  (currently just `__init__.py` calling `navigation_module(...)`) is untouched.
- No chat, monitoring, or action wiring for `retail.pricing_markdown`.
- A6–A9 are out of scope for this document; they are separate specs after A5
  ships.

## Data source: the workbook extract, not a live database

`resources/dbtemp/schema_with_data.json` is a static extract of the retail
workbook (30 tables, the same source A1–A4's fixture builders already read —
see `scripts/build_inventory_risk_fixture.py`). It already carries everything
A5 needs:

| Table | Rows | Relevant columns |
|---|---:|---|
| `engine` | 800 (1/SKU, chain-net) | `sku_id`, `vertical_id`, `cat_id`, `state`, `position`, `price`, `dos`, `at_risk`, `vendor`, `brand`, `max` |
| `engine_store` | 800×stores | `state`, `position`, `price`, `at_risk_value`, `cluster`, `channel`, `store_id` — the store-level gross basis for the dimension charts |
| `sku_master` | 800 | `expiry_d` (shelf-life days), `comp_idx`, `growth`, `perishable`, `category`, `item` |
| `a5_pricing_markdown` | 8 (1/vertical) | the workbook's own rollup: `markdown_candidates`, `avg_depth_pct`, `at_risk_state_value`, `recoverable`, `write_off`, `comp_idx` — used to **reconcile**, not to source rows |
| `constants` | — | What-If lever ranges (B16–B21) |

The formulas A5 needs already exist in `resources/dbtemp/formula.json` and are
reused verbatim (never re-derived in JS or Python):

- **`f12-at-risk-value`** — `IF(state <> "Healthy", position * price, 0)`
- **`f14-recoverable-at-risk-value`** — branches on state internally (Expiry:
  excess over `ads * shelf_life_days`; Overstock/Slow-mover: excess over `max`,
  or 30% of position if no excess; else 0). This one formula already encodes
  every branch the A5 spec describes — nothing extra to write.

Markdown candidates are exactly the SKUs where
`state ∈ {Expiry, Overstock, Slow-mover}` — the same state column A2 Inventory
Risk already classifies. Write-off is `at_risk − recoverable`, computed once
the two formulas have run.

## Build step: `scripts/build_pricing_markdown_fixture.py`

Sibling to `build_inventory_risk_fixture.py`, `build_promotion_effectiveness_fixture.py`, etc.

1. Read `resources/dbtemp/schema_with_data.json` → `engine`, `engine_store`,
   `sku_master`, `a5_pricing_markdown`, `constants`.
2. Join `engine` rows to `sku_master` on `sku_id` for `expiry_d`/`comp_idx`/`growth`/`perishable`.
3. Run `f12` and `f14` (via the same expression engine the backend Formula
   Manager uses — `src/formulas/expression.py`) over every row to get
   `at_risk_value` and `recoverable_value`; derive `write_off` and per-item
   `state` reason text.
4. Filter to candidates (`state` in the three markdown states) for the
   candidate table and the KPI population; keep the full 800 for the
   inventory-state dimension chart (A5's state chart is broader than the
   candidate set — see spec §11).
5. Roll up by vertical/category/store/cluster/channel/state/legal-entity for
   the chart data blocks.
6. **Reconcile before writing**: recompute the six chain-level KPIs
   (candidates=99, weighted avg depth=28.40%, at-risk=Rp 52.02B,
   recoverable=Rp 31.19B, write-off=Rp 20.84B, recovery rate=59.95%) against
   the spec's documented baseline and against `a5_pricing_markdown`'s own
   per-vertical rollup. Abort the build on mismatch — the same discipline
   `build_inventory_risk_fixture.py` already applies, not a new pattern.
7. Write `frontend/src/agents/retail/pricing_markdown/data/fixture.json`.

## Frontend files (mirrors `promotion_effectiveness/` file-for-file)

```
frontend/src/agents/retail/pricing_markdown/
  index.js                              — registers dashboardComponent (gated, see below)
  PricingMarkdownDashboard.jsx          — top-level assembly, same shape as PromotionEffectivenessDashboard.jsx
  data/
    contract.js                         — schema, normalizePricingMarkdownDashboard(), thresholds, DEFAULT_SCOPE
    fixture.json                        — generated by the script above
    dashboardData.js                    — loadFromFixture / loadFromApi (api branch written, unreached — see Wiring)
    engine.js                           — What-If recompute using f14 for markdown-depth lever moves
    selectors.js                        — buildDashboardFromFixture(rows, scope, options)
    drilldown.js                        — per-KPI row decomposition
  presentation.js                       — formatters (Rp, %, x)
  components/
    PricingMarkdownFilters.jsx          — vertical / category / store / horizon / search / refresh / scope chip
    PricingMarkdownSkeleton.jsx
    PricingAppliedScenarioBanner.jsx
    PricingKpiGrid.jsx                  — 6 cards: candidates, avg depth %, at-risk, recoverable, write-off, comp idx
    PricingKpiDrilldown.jsx
    PricingCharts.jsx                   — main combo chart + by-vertical + by-channel
    MarkdownCandidateTable.jsx          — sortable, click-to-scope
    DimensionCharts.jsx                 — category / store / cluster / channel / inventory-state / legal-entity (6)
    PricingWhatIfSimulator.jsx          — 6 levers, paired index bars, metrics strip
    PricingScenarioComparison.jsx       — multi-line overlay, save/export (max 4 saved)
    SuggestedBestAction.jsx             — 4 tabs: Expiry Markdown / Overstock Clearance / Slow-mover Price Cut / Suppress Reorder
```

Each maps directly to a numbered section of
`resources/A5_Pricing_&_Markdown_Dashboard_Spec.md` (§3 KPIs, §4 main chart,
§5 custom charts+table, §6 dimension charts, §7 best action, §8 filters, §9
What-If). The two workbook caveats from spec §11 — chain-net headline vs.
store-gross chart totals, and Comp idx currently flat at 101 in the vertical
rollup — become explicit footnotes in the UI, the same way A4 prints
`GRAIN_NOTE` and `UPLIFT_NOTE`.

## Wiring: fixture-only until backend exists

`index.js` chooses the component based on `IS_STANDALONE`
(`frontend/src/agents/retail/common/dataSource.js`):

- **Fixture/standalone builds** (`npm run build:standalone`, or
  `VITE_DATA_SOURCE=fixture npm run dev`) → full `PricingMarkdownDashboard`,
  reading the bundled fixture. This is how the board gets built, reviewed and
  demoed in this pass.
- **Default `api` mode** (plain `npm run dev`, and the deployed app today) →
  today's `PlaceholderBoard`, unchanged. The backend still returns the empty
  `dashboard_only` stub, so nothing regresses.

`dashboardData.js` still defines `loadFromApi` (calling
`fetchDashboard("retail.pricing_markdown", ...)`), exactly as A4's does, so
that when a future pass builds the real backend module, flipping the gate (or
removing it) is the only frontend change required — no data-layer rewrite.

## Testing

Mirrors the sibling coverage: `contract.js` normalization defaults,
`selectors.js` rollups against the fixture, `engine.js` formula parity
(`applyLevers` at baseline levers must return the fixture unchanged — the same
invariant `engine.test.js` asserts for A4), and a dashboard render test
(`PricingMarkdownDashboard.test.jsx`) covering loading/error/loaded states,
filters, drilldown open/close, and the What-If → scenario-comparison flow.
Python-side, a small parity test (mirroring
`backend/tests/test_retail_module.py`'s existing placeholder coverage) is out
of scope here since no backend module changes; the fixture-builder's own
reconciliation check (step 6 above) is what guards correctness.

## Open items carried into the plan, not resolved here

- Exact Rp/percentage formatting conventions — reuse `presentation.js` from
  `promotion_effectiveness` rather than reinvent.
- Whether `PricingCharts.jsx` is one file (as sketched, matching
  `PromoCharts.jsx`) or split further — an implementation-plan-level call, not
  a design one.
