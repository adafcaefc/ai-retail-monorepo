# Retail formula hardcoding audit — what the boards retype instead of read

Audit date: 2026-08-19, updated 2026-08-20. Branch: `fix/promo-season-mix-chart`.

Companion to [RETAIL_FORMULA_SOURCES.md](./RETAIL_FORMULA_SOURCES.md), which
answers "where does this number come from". This file answers a narrower
question: **which business rules does a dashboard compute from a hand-typed
copy rather than from the catalogue?**

Section F, added 2026-08-20, widens that question: some tiles compute from a
hand-typed copy of something that was never in the catalogue at all, when a
derived figure from real data was sitting in the same payload unused. Not the
same bypass as sections A–E, but the same failure for whoever is reading the
tile.

## The contract being audited

`retail.formula` holds 23 expressions and is the single store for the business
rules. A board declares the ids its engine needs, ships the expressions, and
the browser evaluates them — see
[`formulas()`](../backend/src/llm/agents/retail/common/warehouse.py#L91-L109),
which raises rather than skips a missing id, and the module docstring above it
on why the rules live once and are read by both languages.

Every entry below is a place that contract is bypassed. The catalogue is read
at runtime from the `retail.formula` table, which the Formula Manager can edit,
so each of these is a site that keeps computing the old rule after someone
fixes it in the UI.

## Coverage at a glance

| Board | Ships | Evaluates | Dead in payload |
|---|---|---|---|
| A1 Demand Forecasting | 8 | 5 | f06, f07, f20 |
| A2 Inventory Risk | 11 | 11 | — |
| A3 Replenishment | 9 | 9 | — |
| A3.1 Replenishment Detail | 6 | **0** | all six |
| A4 Promotion Effectiveness | 2 | 2 | — |
| A5 Pricing & Markdown | 12 | 12 | — |
| A6 Assortment Optimization | 9 | 8 | f12 |

Catalogue rules never inserted by any board: **f02** and **f15** (both used,
both hardcoded — section A), and **f16–f19** (genuinely unused; A7 Workforce is
still a stub `index.js`).

---

## A. Used but never inserted — hardcoded outright

### f15-contribution-per-day

Catalogue: `ROUND(ads * price * margin_pct)`. Not listed in any board's
`ENGINE_FORMULAS`. The arithmetic is retyped in five places, and only the two
SQL ones round:

| Site | Code |
|---|---|
| [assortment_optimization/dashboard.py:193](../backend/src/llm/agents/retail/assortment_optimization/dashboard.py#L193) | `ads * price * margin_pct` — no ROUND |
| [assortment_optimization/dashboard.py:365](../backend/src/llm/agents/retail/assortment_optimization/dashboard.py#L365) | `sum(round(f.ads * i.price * i.margin_pct, 0))` |
| [assortment_optimization/dashboard.py:379](../backend/src/llm/agents/retail/assortment_optimization/dashboard.py#L379) | same, per store |
| [tools/assortment_data.py:78](../backend/src/llm/agents/retail/assortment_optimization/tools/assortment_data.py#L78), [:237](../backend/src/llm/agents/retail/assortment_optimization/tools/assortment_data.py#L237) | the chat tool's own copy |
| [assortment_optimization/data/engine.js:111](../frontend/src/agents/retail/assortment_optimization/data/engine.js#L111) | `ads * item.price * item.margin_pct` — no ROUND |

Highest-impact entry in this document. Contribution/day is a KPI tile *and* the
input to the tail-quartile and delist/grow cutoffs, so a catalogue edit that
never reaches these five sites changes which SKUs a buyer is told to delist.

### f02-on-hand

Catalogue: `base_ads * on_hand_days * stock_factor * store_health * store_size`.
The string `f02` appears nowhere in `backend/`, `frontend/`, or `scripts/`.

The rule is retyped in
[inventory_risk/data/engine.js:75-81](../frontend/src/agents/retail/inventory_risk/data/engine.js#L75-L81)
(`atStore`, which re-points a chain row at one store). The comment above it
states the workbook "has no formula id for it (it is a data-generation rule,
not a business rule)" — that is incorrect: it is entry 2 in the catalogue. The
same product is restated as prose in
[inventory_risk/dashboard.py:125-129](../backend/src/llm/agents/retail/inventory_risk/dashboard.py#L125-L129)
and in the fixture builders and seeders.

---

## B. Inserted, then re-implemented anyway

### A3.1 Replenishment Detail — ships six, evaluates zero

[`ENGINE_FORMULAS`](../backend/src/llm/agents/retail/replenishment_detail/dashboard.py#L64-L71)
carries f04, f05, f06, f09, f10, f11 "because this board is showing that
chain's working". Nothing evaluates them; the Python retypes them:

| Line | Hardcoded | Catalogue |
|---|---|---|
| [dashboard.py:235](../backend/src/llm/agents/retail/replenishment_detail/dashboard.py#L235) | `position = qty_on_hand + open_po` | f04 `ROUND(on_hand + open_po)` |
| [dashboard.py:281](../backend/src/llm/agents/retail/replenishment_detail/dashboard.py#L281) | `max(0.0, max_qty - position)` | f09 `IF(position < rop, MAX(0, max_inventory - position), 0)` |
| [dashboard.py:194](../backend/src/llm/agents/retail/replenishment_detail/dashboard.py#L194) | `units * line["unit_price_ta"]` | f11 `ROUND(order_buy_units * pack_factor * price)` |

Line 194 is inside `exception_codes`, which raises `FORMULA_TIE_OUT_FAILED`
when the stored amount does not reconcile. The check that exists to catch
formula drift is itself a hand copy of the formula, so it cannot detect drift
in the rule it is checking.

### f21 / f12 in store-level aggregates

The item grain reads the seeded fact columns, but every per-store rollup
retypes `position * price`:

- [inventory_risk/dashboard.py:203-207](../backend/src/llm/agents/retail/inventory_risk/dashboard.py#L203-L207) — f21 and f12 (`CASE WHEN state <> 'Healthy'`) in SQL
- [assortment_optimization/dashboard.py:381](../backend/src/llm/agents/retail/assortment_optimization/dashboard.py#L381), [:395](../backend/src/llm/agents/retail/assortment_optimization/dashboard.py#L395)
- [pricing_markdown/dashboard.py:353-355](../backend/src/llm/agents/retail/pricing_markdown/dashboard.py#L353-L355) — documents the shortcut ("trivial enough not to round-trip through the expression engine"), and drops f21's ROUND with it

### f08 in A1's default scope

[demand_forecasting/dashboard.py:283](../backend/src/llm/agents/retail/demand_forecasting/dashboard.py#L283)
is `_float(row.get("forecast_7d", ads * 7.45))`. The chain-grain query never
selects `forecast_7d`, so the All-Stores board — the default view — always
takes the hardcoded fallback. Only the store-scoped branch reads the stored
f08 column.

### f05 inverted by hand

[demand_forecasting/data/engine.js:60](../frontend/src/agents/retail/demand_forecasting/data/engine.js#L60)
recovers the baseline lead term as `rop / ads - safety`. That inverse is only
valid where f05's `MAX(1, …)` floor did not engage, which is exactly the case
`test_formula_conformance.py` singles out as worth testing.

### f23, both branches — fixed

**Resolved.** A2's `expiry_value` and `overstock_excess_value` tiles used to
retype two different pieces of f23 by hand:
`inventory_risk/data/selectors.js`'s `overstock_excess_value` computed
`(item.position - item.max) * item.price` — f23's Overstock/Slow-mover case,
but missing the `position * 0.3 * price` fallback the catalogue expression
carries for a row that is already Overstock/Slow-mover with `position ≤ max`.
`expiry_value` separately retyped `expiry_units * price` — numerically equal
to f23's Expiry branch, but still a second copy of a rule the catalogue
already states, and not previously listed in this document at all.

Both now sum a `markdown_at_risk_gross` field — f23 evaluated once per item
in [`inventory_risk/dashboard.py`](../backend/src/llm/agents/retail/inventory_risk/dashboard.py)'s
`build_items()` and [`inventory_risk/data/engine.js`](../frontend/src/agents/retail/inventory_risk/data/engine.js)'s
`applyLevers()`, added to A2's `ENGINE_FORMULAS`/`REQUIRED_FORMULAS` — instead
of either branch being retyped. The overstock figure changed as a result: a
row overstocked but not yet above Max now carries its 30% fallback value
instead of contributing zero.

---

## C. Shipped but dead

Payload weight that nothing reads. Each is a rule the board claims to run and
does not:

- **A1 Demand** — f06, f07, f20. `state` arrives as a stored column from A2; f07 appears only in a comment.
- **A6 Assortment** — f12. No `at_risk` reference exists in the A6 frontend.
- **A3.1 Detail** — all six (see section B).

---

## D. Constants typed into code that the catalogue already holds

Catalogue entries carry `parameters[].default`, which never reaches the
browser — the payload ships `{id: expression}` only. So every default is
hardcoded on both sides.

- `f08.week_factor = 7.45`, typed three times:
  [warehouse.py:237](../backend/src/llm/agents/retail/common/warehouse.py#L237)
  (whose docstring claims it comes "from the catalogue's own reference"),
  [demand_forecasting/dashboard.py:326](../backend/src/llm/agents/retail/demand_forecasting/dashboard.py#L326),
  and [demand_data.py:32](../backend/src/llm/agents/retail/demand_forecasting/tools/demand_data.py#L32).
- f14's state-depth table, retyped as `{"Expiry": 0.4, "Overstock": 0.25, "Slow-mover": 0.3}`
  at [pricing_markdown/dashboard.py:372](../backend/src/llm/agents/retail/pricing_markdown/dashboard.py#L372).
  The docstring is candid that these are "the state-based depth table f14's own
  expression states inline".

Clean by contrast: f07's thresholds (0.6, 15, 10) and f13's transcription
constants (1.3, 0.15, 2.2, 0.85, 0.55) appear only in comments and labels, never
re-implemented.

---

## E. The formula text on screen is hand-written English

Every board renders hover text from a frozen object of hand-written strings,
while the catalogue's own `logic` field goes unused:

[A2](../frontend/src/agents/retail/inventory_risk/data/contract.js#L264) ·
[A3](../frontend/src/agents/retail/replenishment/data/contract.js#L164) ·
[A3.1](../frontend/src/agents/retail/replenishment_detail/data/contract.js#L65) ·
[A4](../frontend/src/agents/retail/promotion_effectiveness/data/contract.js#L169) ·
[A5](../frontend/src/agents/retail/pricing_markdown/data/contract.js#L182) ·
[A6](../frontend/src/agents/retail/assortment_optimization/data/contract.js#L201)

They have already drifted from what the board computes:

| Shown | Catalogue | Dropped |
|---|---|---|
| `ROP = ADS × (Lead + Safety)` | f05 | `ROUND`, both `MAX` guards |
| `Σ max(0, Position − ADS × shelf-life)` | f22 | the `perishable = "Y"` gate |
| `Σ Position × unit price` | f21 | `ROUND` |
| `Amount = Order (buy) × pack factor × unit price` | f11 | `ROUND` |
| `SUM(ADS x Price x Margin %)` | f15 | `ROUND` — and f15 is not shipped at all |

A3.1 is the sharpest case: it ships the real expressions in `payload.formulas`,
threads them through
[contract.js:187](../frontend/src/agents/retail/replenishment_detail/data/contract.js#L187)
and [selectors.js:345](../frontend/src/agents/retail/replenishment_detail/data/selectors.js#L345),
and renders `LINE_FORMULAS` / `KPI_FORMULAS` instead.

---

## F. A typed constant shipped where a derived figure was already sitting unused

Sections A–E are all a catalogue bypass: `retail.formula` has a rule, and a
board retypes it anyway. This section is the adjacent failure — no catalogue
entry existed, real data to derive one from was already in the codebase, and
the tile shipped the workbook's typed constant instead.

### A1 Demand — the "Seasonality index" tile

**Fixed 2026-08-20.** `demand_forecasting/data/selectors.js`'s `computeKpis()`
set `seasonality_index` by blending the A1 sheet's typed per-vertical
constant (`seasonality_idx` — 114, 100, 98… on `agent_kpi_reference`), while
`blendSeasonality()` two lines away already derived a real monthly index from
`fact_gmv_monthly` for the chart beside it. Both numbers shipped in the same
payload (`docs/RETAIL_FORMULA_SOURCES.md` already documented both — Grocery:
114 typed against 108.3 derived); the headline tile just read the wrong one.

Now catalogued as `fc01-seasonal-index` (`resources/custom_formulas.json`) —
a new `fc`-prefixed namespace rather than the next `fNN`, because this rule
was never a row on the workbook's `Formulas` sheet; it is this project's own
method for filling a gap the workbook left typed. `warehouse.seasonal_indices()`
evaluates it; the tile now reads `blendSeasonality(...)`'s curve at the
current month instead of the typed blend.

### What else to watch for

Any tile whose `derivation` label reads `typed-constant` is a candidate:
check whether the data it would need to derive from for real already exists
elsewhere in the payload before assuming none does. A1's `forecast_accuracy`
and `demand_trend` are typed for a different reason — no data exists to
derive them from at all (`docs/RETAIL_FORMULA_SOURCES.md`'s "Still missing"
table) — so they are not the same case; `seasonality_index` was, because
`fact_gmv_monthly` already existed and was already being read for the chart.

---

## Why no test catches any of this

[test_formula_conformance.py](../backend/tests/test_formula_conformance.py)
checks the **catalogue against the workbook** at 16,000 rows, and does it well
— including a sabotage suite. What no test checks is the copies in sections
A–D **against the catalogue**.

Two consequences:

1. The conformance test reads `resources/dbtemp/formula.json` (the seed). The
   boards read the `retail.formula` table. An edit made through the Formula
   Manager moves every board that evaluates, leaves every hardcoded site on the
   old rule, and fails no test.
2. The drift is silent in the worst way — each copy still returns a plausible
   number, and the tie-out check meant to notice it (A3.1) shares the same copy.

## Suggested order of work

1. **f15 in A6** — five sites, feeds a classification cutoff. Add
   `f15-contribution-per-day` to A6's `ENGINE_FORMULAS`, evaluate it in
   `dashboard.py` and `engine.js`, and settle the ROUND question one way.
2. **A3.1's tie-out check** — evaluate f11 and f04 rather than retyping them,
   so `FORMULA_TIE_OUT_FAILED` can actually detect a rule change.
3. **f08's `ads * 7.45` fallback** in A1's default scope, and the three copies
   of 7.45 — read the value from `f08.parameters[week_factor].default`.
4. **f02** — add it to A2's `ENGINE_FORMULAS`, evaluate it in `atStore`, and
   correct the comment that says it has no id.
5. **The store-rollup SQL** (f21/f12) — lower priority; the shortcut is
   deliberate and documented, but it belongs on a checklist so a catalogue edit
   has one place to look.
6. **Hover text** — derive from the catalogue's `logic`/`expression` instead of
   `KPI_FORMULAS`, or add a test asserting the two agree.

Already fixed as of 2026-08-20: `RETAIL_FORMULA_SOURCES.md`'s expression
count (was still 22, now 23 plus a note on the separate `fc`-prefixed custom
namespace), and section B's "f23's overstock branch" entry (see section F's
sibling fix above it in A2, and the new §2 entry for its previously-undocumented
Expiry-branch twin).

**A citation-drift note.** File:line references throughout this document are
a snapshot from the audit date, not a live index — several have already moved
by a few lines as of this update (e.g. section B's f23 citation was
`selectors.js:127`, confirmed at `:131` before this session's fix changed the
file again). Treat every `file:line` here as "was here as of 2026-08-19",
and re-locate by the quoted code if a line number no longer matches.
