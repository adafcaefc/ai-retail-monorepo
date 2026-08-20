# Agent 1 · Demand Forecasting — KPI card ↔ Formula Manager pairing

The six KPI cards at the top of the Demand Forecasting board, and the
`retail.formula` entry behind every figure on each one.

Companion to [A2_KPI_FORMULA_PAIRING.md](./A2_KPI_FORMULA_PAIRING.md), written
to the same contract and for the same reason: so a reader can point at any tile
and be answered with a formula id rather than an opinion, and so anyone editing
a rule in the Formula Manager can see, before they save, which cards will move.

**Four of the six are evaluated from the catalogue. Two are not, and cannot be
yet** — see cards 2 and 3. That split is deliberate and is what
`fixture.derivation` has always reported to the tiles; this document says which
rule sits behind the ones that have one.

---

## The two paths, and why they agree

| Path | Runs in | Code | When |
|---|---|---|---|
| **Baseline** | Python, server-side | [`demand_forecasting/dashboard.py`](../backend/src/llm/agents/retail/demand_forecasting/dashboard.py) → `build_item` | Every page load |
| **What-If** | JavaScript, in the browser | [`demand_forecasting/data/engine.js`](../frontend/src/agents/retail/demand_forecasting/data/engine.js) → `applyLevers` | A lever moves off zero |

Both read the **same catalogue** — `retail.formula`, which is also what the
Formula Manager writes — and both run it through the same expression evaluator,
ported once per language. Neither reads a stored answer.

Aggregation is a third, separate thing: the sums, counts and volume-weighted
blends live in [`selectors.js`](../frontend/src/agents/retail/demand_forecasting/data/selectors.js)'s
`computeKpis`. **It resolves no rule.** The expression engine is scalar-only
(`MAX, MIN, ROUND, CEILING, IF, AND, OR, NOT`) and has no `SUM` or `COUNT`, so
there is nowhere to put an aggregate even if one belonged there — and it does
not: a catalogue entry for "average" would describe a chart rather than the
business.

> **Why the baseline path stopped reading stored columns.**
> `build()` used to read `ads`, `position_qty`, `rop_qty` and `state` straight
> off the fact table, compute `forecast_7d` as the literal `ads * 7.45` (f08's
> arithmetic retyped — and on the chain branch the stored column does not even
> exist, so the default All-Stores board *always* took that fallback), and test
> `position < rop` and `viral or growth > 1.25` in Python.
>
> `retail.formula` is read live and uncached precisely so a Formula Manager
> save takes effect at once, and that promise held only for the What-If path.
> The result was not merely that an edit was ignored — it was that the board
> became **internally inconsistent**. Doubling f08 left the tile at 1,809,147
> at rest and jumped it to 3,980,124 the moment the demand lever moved off
> zero, because baseline and scenario were computing from two different rules.
> That is the bug this ends.
>
> **No number moved.** The stored columns are the workbook's own and they agree
> with the catalogue exactly — the fixture builder's `verify_engine_chain()`
> proves it over all 800 rows at zero levers. Before and after: forecast
> 1,809,147.223, stockout-risk 345, trending 355.

---

## Card 1 · Forecast next 7 days

| Layer | Source |
|---|---|
| **Value** | `Σ f08-forecast-7-days`, aggregation only |
| **Rule** | `f08-forecast-7-days` |
| **Feeds it** | `f01-ads-per-store` |
| **Sparkline** | The scope's blended seasonal curve — `fc01-seasonal-index` |

```
f01  base_ads × seasonality × arch_horizon_factor × store_size
     × (1 + demand_lever / 100)
     × IF(AND(promo_eligible = "Y", promo_lever > 0),
           1 + (promo_lever / 100) × 1.3 × (1 - promo_depth), 1)

f08  ads × week_factor
```

`week_factor` is `Constants` B7 — `DOW_SUM` in
[`warehouse.py`](../backend/src/llm/agents/retail/common/warehouse.py), 7.45 —
passed as f08's parameter rather than written into the multiplication. The
board no longer carries its own copy of the number.

---

## Card 2 · Forecast accuracy — typed, not catalogued

| Layer | Source |
|---|---|
| **Value** | Volume-weighted blend of `accuracy_pct` across the scope's verticals |
| **Rule** | none — see below |
| **Sparkline** | Prediction band width, `forecast × z × (1 − accuracy/100) × √h` |

`accuracy_pct` is **92.4 for all eight verticals**, typed into the A1 sheet. It
is not a backtest and no rule produces it.

`fc02-forecast-accuracy-pct` is already in the catalogue and editable —
`100 - (vol_base * 26.6 + shape_err * 0.4 + store_vol + hz_pen)` — but nothing
feeds its four parameters. Its source sheet `A1 Accuracy live` has no
`SheetSpec`, no table and no seed mapping; see
[v8.5-new-agent-formulas.md](./v8.5-new-agent-formulas.md). Wiring this tile
means building that extraction path first.

The prediction band is a **presentation model, not a business rule**: `z` is
`INTERVAL_Z` (1.645, the 90% two-sided normal quantile) and the `√h` widening
is a property of accumulating forecast error. It belongs in the board, not in
the Formula Manager.

---

## Card 3 · Demand trend — typed, not catalogued

| Layer | Source |
|---|---|
| **Value** | Volume-weighted blend of `trend_pct` across the scope's verticals |
| **Rule** | none, and none is proposed |
| **Sparkline** | The forecast curve the trend compounds into |

Per-vertical constants (5.6, 8.7, 6.9, …) typed into the A1 sheet, and
**unsupported by the workbook's own series** — `time_series_24mo`'s second year
is byte-identical to its first, so measured year-on-year growth is exactly zero.

Not among the ten v8.5 formulas, and there is no derivation anywhere to encode.
Cataloguing it would put a rule in the Formula Manager that restates a typed
constant — worse than leaving it, because the tile currently labels itself
"Workbook constant" honestly.

---

## Card 4 · Stockout-risk SKUs

| Layer | Source |
|---|---|
| **Count** | `count(is_stockout_risk)` where `is_stockout_risk = state ∈ {Stockout, Low}` |
| **Rule** | `f07-inventory-state` |
| **Feeds it** | `f01` → `f03` → `f04` → `f05` → `f20` → `f07` |
| **Sparkline** | Days-of-cover histogram, `position / ads` — the `f20` shape |

```
f03  open_po_total × (store_size / total_store_size) × (1 + inbound_lever / 100)
f04  ROUND(on_hand + open_po)
f05  ROUND(ads × (MAX(1, lead_time_days + lead_time_adjust)
                + MAX(0, safety_days + safety_adjust)))
f20  IF(ads > 0, position / ads, 0)
f07  IF(position < rop × 0.6, "Stockout",
     IF(position < rop,       "Low", …))
```

**Why the flag reads the state and not `position < rop`.** f07 assigns
`Stockout` below `0.6 × ROP` and `Low` below ROP, so those two states *are* the
rows below the reorder point, by construction. Reading them off the state
cannot drift from f07; a separate comparison can. This is also the definition
[A2 card 1](./A2_KPI_FORMULA_PAIRING.md) uses, and the two boards must agree —
both display this tile, and a reader with both tabs open has no way to tell
which is wrong if they differ.

Verified equivalent over the live warehouse at both grains: **345 of 800**
chain-net rows and **7,090 of 16,000** store rows, with no row disagreeing
either way.

> **This equivalence is a property of f07's branch order, not a law.** The note
> on `REPLENISH_STATES` in `warehouse.py` describes an f07 that tested `Expiry`
> before `Low`, which would put perishable stock that is both below ROP and
> past shelf life outside this set. The catalogue does not currently do that —
> Stockout and Low are tested first — which is why the counts agree exactly.
> That comment is stale as written and its 199-row figure does not reproduce.

---

## Card 5 · Predicted to trend

| Layer | Source |
|---|---|
| **Count** | `count(fc10-trending-sku = 1)` |
| **Rule** | `fc10-trending-sku` |
| **Sparkline** | Growth-index histogram over the trending rows |

```
fc10  IF(OR(is_viral = "Y", growth_index > 1.25), 1, 0)
```

**New in this pass.** The A1 spec states this test but the catalogue had no
entry for it, so the 1.25 threshold was typed in `dashboard.py`, in
`build_demand_forecasting_fixture.py`, and implicitly in the fixture it wrote.
It is now one editable rule; a Formula Manager save moves the tile (dropping
the threshold to 1.05 takes the count from 355 to 600).

Returns 1/0 rather than a label so the board counts rows without parsing a
string. `chain_sku` grain: `is_viral` and `growth_index` are SKU-master
attributes, chain-wide, with no per-store variation.

**A per-row predicate, not a quota.** It never depends on how many other rows
are in the result set, so it composes correctly under any scope filter — while
still reconciling exactly to the sheet's typed vertical-wide `Trending SKUs`
count, which the fixture builder's `reconcile()` asserts across all eight
verticals.

`engine.js` deliberately does **not** re-run fc10 when a lever moves: no lever
touches `is_viral` or `growth_index`, so the baseline's catalogue-evaluated
answer carries through unchanged rather than a rule being run that cannot move.

---

## Card 6 · Seasonality index

| Layer | Source |
|---|---|
| **Value** | The scope's blended seasonal curve at the current month |
| **Rule** | `fc01-seasonal-index` |
| **Evaluated in** | Python, `warehouse.seasonal_indices()` — server-side, not in the browser |

```
fc01  ROUND(month_gmv / series_mean × 100, 4)
```

Already catalogue-driven before this pass. Reads real `fact_gmv_monthly` data
rather than the A1 sheet's typed 114/100/98/…, which is still carried in
`reference_by_vertical` for comparison. `vertical` grain — there is no
per-store GMV key, so a Store scope shows its owning vertical's curve, which
`scope_limitations` states on the board.

---

## Which cards move when you edit a rule

| Edit this | These cards move |
|---|---|
| `f01-ads-per-store` | Forecast next 7 days, Stockout-risk SKUs |
| `f03`, `f04`, `f05`, `f20`, `f07` | Stockout-risk SKUs |
| `f08-forecast-7-days` | Forecast next 7 days |
| `fc10-trending-sku` | Predicted to trend |
| `fc01-seasonal-index` | Seasonality index, and card 1's sparkline |
| `f06-maximum-inventory` | **nothing** — shipped in the payload, evaluated by no A1 code |

Forecast accuracy and Demand trend move for no formula edit. They are typed
constants, and the tiles say so.
