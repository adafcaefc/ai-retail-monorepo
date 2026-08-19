# Retail formula sources — what is measured, modelled, or typed

Every number on the three Retail boards, and where it comes from. Written so a
reader can challenge any figure on screen and be answered with a cell address
rather than an opinion.

Three labels are used throughout, and they are not interchangeable:

| Label | Means |
|---|---|
| **measured** | A formula in the workbook computes it. Reproduced here and checked against the workbook's own answer. |
| **modelled** | No workbook formula. A stated method fills the gap, using workbook inputs. The method is named below and in the code. |
| **typed** | Somebody keyed a constant into a cell. Carried through unchanged, never presented as a calculation. |

---

## 1. The formula catalogue

`resources/dbtemp/formula.json` holds 22 expressions. Nineteen transcribe the
workbook's `Formulas` sheet; f20–f22 are ENGINE columns I, L and N — real
workbook formulas that sheet simply does not list.

**The catalogue is a hand transcription, not an extraction.** It arrived in
commit `791aa14`, converting nineteen rows of prose like

```
State | Stockout<0.6ROP; Low<ROP; Expiry(perishable,DoS>shelf);
        Overstock(non-perish,DoS>15); Slow(growth<1,DoS>10)
```

into executable expressions, and introducing constants the prose never mentions
(1.3, 0.15, 2.2, 0.85, 0.55). So it is **tested rather than trusted**, by
`backend/tests/test_formula_conformance.py`:

| Check | Scope | Result |
|---|---|---|
| f01–f16, f20, f21 vs `ENGINE_STORE` | 18 columns × 16,000 rows | 0 mismatches |
| f17–f19 vs `Workforce` | 159 stores | 0 mismatches |
| Lever path vs `What-If · Per Agent` | demand +20%, promo 15, 8 verticals | ≤ 1.5 units |
| Reorder floors under a negative lever | 75 SKUs crossing `MAX(1, …)` | holds |
| Monotonicity per lever | 4 levers × 120 SKUs | holds |

The lever check matters more than its size suggests. Every other comparison
sits at `Constants` B16–B21, which are all zero, so a sign error in
`(1 + demand_lever / 100)` would pass all 16,000 rows. `What-If · Per Agent` is
the only non-zero reference the workbook contains.

**Verified by deliberate sabotage.** Eight mutations were applied to
`formula.json` one at a time — flipped lever signs, `DoS > 15` → `> 16`,
`MAX(1, …)` → `MAX(2, …)`, `/100` → `×100`. All eight were caught.

---

## 2. Agent 1 · Demand Forecasting

### What the workbook computes

**One thing.** The `A1 Demand Forecasting` sheet has six columns and five of
them are literals:

```
Forecast 7d      =SUMIFS(ENGINE_STORE!U, vertical)   <- measured
Accuracy %       92.4                                <- typed
Trend %          5.6, 8.7, 6.9, …                    <- typed
Stockout-risk    46, 31, 39, …                       <- typed
Trending SKUs    47, 39, 44, …                       <- typed
Seasonality idx  114, 100, 98, …                     <- typed
```

### KPI ledger

| KPI | Label | Source |
|---|---|---|
| Forecast next 7 days | measured | f01 → f08, reconciled to 1,656,178.216 |
| Stockout-risk SKUs | measured | `Position < ROP` via f03/f04/f05. A1 types 46; this computes 46 |
| Predicted to trend | measured formula | `viral OR growth > 1.25`, per SKU. Reconciles exactly to the sheet's typed count |
| Forecast accuracy | typed | 92.4 for **all eight** verticals — a demo constant, not a backtest |
| Demand trend | typed | Per vertical, and unsupported by the series (see below) |
| Seasonality index | typed | 114 typed against 108.3 derived — both kept, both labelled |

### `time_series_24mo` is not history

Its second year is **byte-identical** to its first in all eight verticals, so
year-on-year growth is exactly zero by construction. It is one seasonal profile
written twice.

Consequences:

- **No actuals line is drawn.** The A1 spec calls the main chart "actual vs
  AI"; there are no actuals, so the series starts at today rather than
  back-casting a line that would read as measurement.
- **It is an excellent seasonal index**, which is how it is used: month GMV ÷
  series mean gives twelve classical indices per vertical.
- The typed `Trend %` has nothing behind it. It is still applied to the
  forecast curve, because it is the workbook's stated trend, and labelled.

### Modelled methods, and why each one

| Quantity | Method | Anchored to |
|---|---|---|
| Forecast curve | `ADS × DOW(d) × seasonal(month) × (1+trend)^(d/365)` — classical multiplicative decomposition | f01 for level, `Constants` B7 for the week |
| Day-of-week profile | `[0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25]`, Monday first | Sums to **exactly 7.45**, which is `Constants` B7 and what f08 multiplies by. A modelled allocation of a measured total |
| Prediction interval | `ŷ ± z · (1 − accuracy/100) · √h`, z = 1.645 | At h=1 with 92.4% accuracy this is ±12.5% — which is where the A1 spec's flat "±12%" comes from. Stated this way it widens with horizon, as an interval must |
| Seasonal curve | month GMV ÷ series mean, per vertical | `time_series_24mo` |
| Current month | July | `Constants` B6 = 6 |
| Trending membership | `viral OR growth > 1.25`, per SKU — a formula, not a rank+quota allocation, so it composes correctly under category/store scoping | Reconciles per vertical exactly |

### What-If

Four of six levers reach something, because four are parameters in the
catalogue: `demand` and `promo` through f01, `inbound` through f03, `lead` and
`safety` through f05. **`markdown` reaches nothing** — the workbook has no
markdown term anywhere.

Accuracy and Trending do not move either: they are typed constants. The payload
names them in `simulation.unmodelled` so the panel can say so rather than
leaving a reader to wonder why a slider did nothing.

**Sliders open at zero**, not at the mockup's `promo: 15, markdown: 25`. Those
are the values of the published *scenario*, not of the baseline — opening there
would show a simulation while claiming to show the workbook.

---

## 3. Agent 2 · Inventory Risk

The opposite case: everything the A2 spec asks for is computed in the workbook,
and `build_inventory_risk_fixture.py` reconciles 48 KPI values across 8
verticals before writing.

### Two definitions that had drifted

The A2 spec gives two different rules for the same KPI in adjacent columns, and
presents them as one:

| KPI | Spec "Formula" column | Spec "Data di workbook" column | Count |
|---|---|---|---|
| Overstock SKUs | `count(DoS > 15)` | `COUNTIFS(ENGINE!J, "Overstock")` | 40 / 40 |
| Slow-moving SKUs | `count(growth<1 AND DoS>10)` | `ENGINE!J = "Slow-mover"` | **62 / 51** |

Overstock agreed by luck of this dataset — no perishable SKU sits above 15 days
without being Expiry first. Slow-mover never agreed: 11 SKUs satisfy the raw
predicate but were already claimed by a more urgent state, so the card read 62
while the state chart directly beneath it read 51.

**Both now follow the workbook.** The card reads 51.

### The What-If engine

`frontend/src/formulas/expression.js` is a port of the Python evaluator. What
is duplicated is the **interpreter**, not what it interprets: there is no
threshold, state name or lever name in that file. The rules stay in
`formula.json`, one copy, read by both languages.

| Guard | Scope |
|---|---|
| JS vs Python evaluator | 22 formulas × 110 worked examples |
| Engine at zero levers vs fixture | 800 chain-net rows, exact |
| Engine vs published +20% scenario | 8 verticals |
| Reorder floors at minimum lever | 75 SKUs |

Delete `expression.js` when the backend can answer scoped What-If queries. Two
evaluators are defensible while one of them is the only way to get an answer.

### Honest limits on the board

- **Projection has no history.** One on-hand reading per SKU exists; the chart
  starts at today and says why.
- **Store and cluster charts stay on the baseline** under a scenario — they
  arrive pre-aggregated, so there are no rows left to re-run.
- **Gross vs chain-net.** Store breakdowns sum local pockets and exceed the
  chain-net headline by design (A2 spec §10 note 1).

---

## 4. Agent 3 · Replenishment

The least blocked of the three: five of six KPIs are computed in the workbook,
and nothing waits on D365.

### Two order values, both kept

The workbook states order value twice, and they differ by about a fifth:

```
A3 Replenishment / ENGINE!P    order units × SELLING price   (retail)
Replenishment Detail!amount    buy units × TRADE price       (cost)
```

Grocery: Rp 4.46 bn against Rp 3.60 bn. A buyer approving a PO needs the cost;
a merchandiser sizing the commitment needs the retail value. Reporting one as
"order value" and hiding the other is how a board gets used to argue for the
wrong decision, so both ship, both named.

### Routes come from lead time

A3 spec §2 classifies `fresh → Direct`, `catId ∈ {BEV, HOU} → Flow-Through`,
else `Cross-Dock`. **`BEV` and `HOU` do not exist in this dataset** — the
mockup carried its own category codes.

`SKU_Master.lead_d` takes exactly three values, and they line up with the
spec's own lead-time story one for one:

| Lead | SKUs | Route | Spec's added lead |
|---:|---:|---|---|
| 2d | 75, all perishable | Direct Store Delivery | +2d |
| 4d | 625 | Flow-Through | +4d |
| 7d | 100 | Cross-Docking | +5d and up |

`perishable == "Y"` and `lead_d == 2` select the same 75 rows with no
exceptions, so the fresh rule and the lead-time rule agree where they overlap.

### Pack rounding is real money

`Buy = CEILING(Order ÷ pack)` always rounds up, so a PO brings in slightly more
than the shortfall. That is why f11 (`buy × pack × price`) and `ENGINE!P`
(`round(need × price)`) differ — GRC-001 by exactly two units at Rp 18,900.
Both are right; the board labels the gap rather than reconciling it away.

### The one number that proposes something

`saving_vs_designated` — **Rp 4.45 bn** chain-wide — is what the same purchase
order would cost at each line's cheapest quoted vendor instead of its
designated one. Shown per vendor as well as in total: a saving nobody can
attribute is a saving nobody can act on.

---

## 5. What all three now agree on

`frontend/src/agents/retail/crossModule.test.js` holds them to it:

- the same 800 SKUs under the same codes, in the same categories and entities;
- the same 8 legal entities — `HBA` and `HME`, which Demand used to invent, do
  not exist and are gone;
- the same 160 stores and 160 categories;
- **`stockout_risk_skus` SKU for SKU**, per vertical and in total (302);
- the same day-of-week constant, and the same catalogue expressions.

Before this, Demand invented its dimensions from a hash of the row index, so
`GRC-001` meant a different product on each board. Dimension values are join
keys: a cross-agent feature ("this SKU is trending **and** at stockout risk")
is only possible while the codes mean the same thing on both sides.

---

## 6. Still missing, and what it would take

| Gap | Blocks | Needs |
|---|---|---|
| Sales history at SKU × store × day | Demand's actuals line, real accuracy, real trend | D365. 24 months minimum |
| Backtest accuracy | Replacing the typed 92.4 | The above, plus stored forecast runs |
| Markdown elasticity | A1/A2's sixth lever | A price-response model; nothing in the workbook |
| Stochastic safety stock | Replacing `safety_days` with `z · σ_LT` | Demand variability per SKU, which needs the history |
| Inbox / agent hand-off | Every board's `next_agent` routing | A mechanism that does not exist anywhere in this app yet |

**Only the first row genuinely waits on D365, and only for Agent 1.** Agents 2
and 3 are complete against the workbook today.
