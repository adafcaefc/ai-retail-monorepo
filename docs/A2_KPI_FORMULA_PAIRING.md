# Agent 2 · Inventory Risk — KPI card ↔ Formula Manager pairing

The six KPI cards at the top of the Inventory Risk board, and the
`retail.formula` entry behind every figure on each one.

Written so a reader can point at any tile and be answered with a formula id
rather than an opinion — and so anyone editing a rule in the Formula Manager
can see, before they save, which cards will move.

**Every derived figure below is evaluated from the catalogue.** Nothing on
these tiles is a threshold typed into Python or JavaScript. The board supplies
parameters and decides evaluation order; `retail.formula` decides the answer.

---

## The two paths, and why they agree

A figure on these cards is produced twice, by two engines, from the same rows:

| Path | Runs in | Code | When |
|---|---|---|---|
| **Baseline** | Python, server-side | [`inventory_risk/dashboard.py`](../backend/src/llm/agents/retail/inventory_risk/dashboard.py) → `build_items` | Every page load |
| **What-If** | JavaScript, in the browser | [`inventory_risk/data/engine.js`](../frontend/src/agents/retail/inventory_risk/data/engine.js) → `applyLevers` | A lever moves off zero |

Both read the **same catalogue** — `retail.formula`, which is also what the
Formula Manager writes — and both run it through the same expression
evaluator, ported once per language. Neither reads a stored answer.

Aggregation is a third, separate thing and lives only in the browser, in
[`selectors.js`](../frontend/src/agents/retail/inventory_risk/data/selectors.js)'s
`computeKpis`. It counts flags and sums columns. **It resolves no rule**, which
is why no threshold appears in that file.

> **Why the baseline path stopped reading stored columns.**
> `fact_inventory_chain_daily` carries `position_qty`, `rop_qty`, `max_qty`,
> `days_cover`, `state`, `inventory_value`, `at_risk_value` and `expiry_units`
> as precomputed answers, and `build_items` used to read all eight, plus a
> retyped `position < rop` for the stockout flag. Those columns are the
> workbook's own and they still agree with the catalogue exactly — the switch
> moved no number on screen. What it changed is what happens after someone
> edits a rule: `retail.formula` is read live and uncached precisely so a
> correction takes effect at once, and that promise previously held only for
> the What-If path. Fixing f20 and watching the baseline board keep last
> week's days-of-supply was the bug this ends.

---

## Card 1 · Stockout-risk SKUs

| Layer | Source |
|---|---|
| **Count** | `count(is_stockout_risk)` where `is_stockout_risk = state ∈ {Stockout, Low}` |
| **Rule** | `f07-inventory-state` |
| **Feeds it** | `f04-position` → `f05-rop` → `f20-days-of-supply` → `f07` |
| **Caption** | Static label, "Position below reorder point" |

```
f04  ROUND(on_hand + open_po)
f05  ROUND(ads × (MAX(1, lead_time_days + lead_time_adjust)
                + MAX(0, safety_days + safety_adjust)))
f07  IF(position < rop × 0.6, "Stockout",
     IF(position < rop,       "Low", …))
```

**Why the flag reads the state and not `position < rop`.** f07 assigns
`Stockout` below `0.6 × ROP` and `Low` below ROP, so those two states *are* the
rows below the reorder point, by construction. Reading them off the state costs
nothing and cannot drift from f07; a separate comparison can. The tile's
second button ("Show only the reorder zone") scopes the board to exactly this
set, so the card and the filter cannot disagree.

---

## Card 2 · Overstock SKUs

| Layer | Source |
|---|---|
| **Count** | `count(state = "Overstock")` |
| **Rule** | `f07-inventory-state` |
| **Caption (money)** | `Σ f23-markdown-at-risk-gross` over Overstock rows only |
| **Feeds the caption** | `f06-maximum-inventory` supplies `max_inventory` |

```
f07  … IF(AND(perishable = "N", days_of_supply > 15), "Overstock", …)

f06  ROUND(ads × (MAX(1, lead + lead_adjust)
                + MAX(0, safety + safety_adjust)
                + horizon_coverage))

f23  IF(OR(state = "Overstock", state = "Slow-mover"),
       IF(MAX(0, position - max_inventory) > 0,
          (position - max_inventory) × price,
          position × 0.3 × price), …)
```

Two details the tile depends on:

- **The 30% fallback is included.** A row already classified Overstock but
  sitting at or below Max still carries 30% of its position as at-risk, not
  zero. The caption used to drop that branch by re-deriving the arithmetic
  itself; it now sums f23 and gets the whole rule.
- **f23 spans two states, this tile does not.** f23's branch covers Overstock
  *and* Slow-mover. The caption scopes to Overstock rows only, matching the
  tile's name.

`horizon_coverage` is `Constants` B24 (`hz_cov`, 4.0), carried in the payload
as `constants.hz_cov` so the browser re-derives Max against the same horizon
the baseline used.

---

## Card 3 · Expiry-risk units

| Layer | Source |
|---|---|
| **Value** | `Σ f22-expiry-units` |
| **Rule** | `f22-expiry-units` |
| **Caption (money)** | `Σ f23-markdown-at-risk-gross` over `state = "Expiry"` rows |
| **State rule** | `f07-inventory-state` |

```
f22  IF(perishable = "Y", MAX(0, ROUND(position - ads × shelf_life_days, 0)), 0)

f07  … IF(AND(perishable = "Y", days_of_supply > shelf_life_days), "Expiry", …)

f23  IF(state = "Expiry",
       MAX(0, position - ads × shelf_life_days) × price, …)
```

f23's Expiry branch and `f22 × price` agree exactly, so pricing the units
through f23 rather than multiplying locally changes no figure — it just means
one rule owns the money line on both this card and card 2.

Note the count/value distinction: f22 counts **units**, not SKUs. The mini-chart
beside it reuses the board's own expiry timeline buckets rather than inventing
a second bucketing.

---

## Card 4 · Slow-moving SKUs

| Layer | Source |
|---|---|
| **Count** | `count(state = "Slow-mover")` |
| **Rule** | `f07-inventory-state` |
| **Caption** | Static label, "Declining growth, high cover" |

```
f07  … IF(AND(velocity < 1, days_of_supply > 10), "Slow-mover", "Healthy"))
```

**This card reads 37, not 43, and that is not a discrepancy.** The A2 spec's
"Formula (card fx)" column and the workbook sheet beside it disagree, and the
spec presents them as if they did not:

| Predicate | Count |
|---|---|
| `growth < 1 and dos > 10`, evaluated raw | 43 |
| `state = "Slow-mover"` | 37 |

Six SKUs satisfy the raw predicate but were already claimed by a
higher-severity state — f07's branches are exclusive, in severity order.
Following the spec's column made the card contradict the state chart and the
risk register directly beneath it. The board follows f07.

The **gap is a property of the dataset, not a fixed number** — it was 62 vs 51
before the fixture was regenerated in `8c0f42c`, and several code comments
still cited those stale figures until this pass. Card 2 makes the same point
from the other side: `dos > 15` and `state = "Overstock"` both give 26 here,
but they agree only by luck of this dataset, because no perishable SKU sits
above 15 days' cover without being classified `Expiry` first.

---

## Card 5 · Avg days of supply

| Layer | Source |
|---|---|
| **Value** | `mean(f20-days-of-supply)` — `Σ dos ÷ count`, aggregation only |
| **Rule** | `f20-days-of-supply` |
| **Feeds it** | `f01-ads-per-store`, `f04-position` |
| **Caption** | Target band 7–21d, `DOS_TARGET` in `contract.js` |

```
f20  IF(ads > 0, position / ads, 0)

f01  base_ads × seasonality × arch_horizon_factor × store_size
     × (1 + demand_lever / 100)
     × IF(AND(promo_eligible = "Y", promo_lever > 0),
           1 + (promo_lever / 100) × 1.3 × (1 - promo_depth), 1)
```

The mean is arithmetic, not a rule — there is no catalogue entry for "average",
and inventing one would put a rule in the Formula Manager that describes a
chart rather than the business.

The **target band (7–21d) is a presentation threshold, not a formula.** It
decides whether the caption is tinted warn or good; it never changes the
number. It lives in `contract.js` because nothing upstream classifies against
it.

> **`arch_horizon_factor` is f01's, and the backend used to guess it.**
> v8.5 added an archetype/horizon multiplier to f01. `dim_item` carried the
> archetype *label* but never the multiplier the formula reads, so live queries
> fell back to `1.0` — silently returning an ADS the workbook never calculated,
> and with it a different DoS, state, and expiry figure. `sql/retail/008` adds
> the column, seeded from `ENGINE_STORE!archhz` (a per-SKU constant, verified
> identical across all 20 stores for all 800 SKUs).

---

## Card 6 · Inventory value

| Layer | Source |
|---|---|
| **Value** | `Σ f21-inventory-value` |
| **Rule** | `f21-inventory-value` |
| **Caption (at risk)** | `Σ f12-at-risk-value` |
| **State rule** | `f07-inventory-state` |

```
f21  ROUND(position × price)

f12  IF(state <> "Healthy", position × price, 0)
```

**The caption is labelled, deliberately.** `at_risk_value` is the *full
position value* of every non-Healthy SKU — not an expected loss. Beside a unit
measure like card 3's it overstates exposure, so it carries
`AT_RISK_VALUE_NOTE` rather than appearing as a bare currency figure. That is a
statement about what f12 means, not a correction to it.

---

## Summary

Unscoped, at zero levers, on the current dataset (800 chain-net SKUs):

| # | Card | Value |
|---|---|---|
| 1 | Stockout-risk SKUs | 345 |
| 2 | Overstock SKUs | 26 |
| 3 | Expiry-risk units | 5,562 |
| 4 | Slow-moving SKUs | 37 |
| 5 | Avg days of supply | 7.83d |
| 6 | Inventory value | 2,223,726,280,600 (at risk 739,163,141,900) |

| # | Card | Primary rule | Also evaluates |
|---|---|---|---|
| 1 | Stockout-risk SKUs | `f07` | `f04`, `f05`, `f20` |
| 2 | Overstock SKUs | `f07` | `f06`, `f23` |
| 3 | Expiry-risk units | `f22` | `f07`, `f23` |
| 4 | Slow-moving SKUs | `f07` | `f20` |
| 5 | Avg days of supply | `f20` | `f01`, `f04` |
| 6 | Inventory value | `f21` | `f07`, `f12` |

Eleven catalogue entries carry these six cards:

```
f01-ads-per-store          f07-inventory-state       f21-inventory-value
f03-open-po-per-store      f12-at-risk-value         f22-expiry-units
f04-position               f20-days-of-supply        f23-markdown-at-risk-gross
f05-rop
f06-maximum-inventory
```

A twelfth, `f02-on-hand`, is shipped in the payload but not evaluated by these
cards: it re-derives on-hand at a single store's health and size index, and
these rows are chain-net. The KPI **drill-down** evaluates it, in `engine.js`'s
`atStore`.

---

## Editing a rule

`retail.formula` is read **live and uncached** on every dashboard request, so a
Formula Manager save reaches the next page load with no deploy and no cache
bust. Both engines pick it up: the baseline because `build_items` re-evaluates
per request, the browser because the expressions ship inside the payload.

What that means in practice:

| Edit | Cards that move |
|---|---|
| `f07` thresholds | **All six** — every tile either counts a state or prices one |
| `f20` | 5, and 1/2/3/4 via f07's `days_of_supply` input |
| `f05` / `f04` | 1 directly, then all six through f07 |
| `f01` | Everything downstream of ADS — 3, 5, and all states |
| `f21` | 6 only |
| `f12` | 6's caption only |
| `f22` | 3's unit figure only |
| `f23` | 2's and 3's money captions only |
| `f06` | 2's caption (via f23's `max_inventory`) |

A missing id raises at build time and names the formula, rather than failing at
the first slider drag with a `NaN` — `formulas()` in
[`warehouse.py`](../backend/src/llm/agents/retail/common/warehouse.py) on the
server, `createEngine`'s `REQUIRED_FORMULAS` in the browser.

---

## Guardrails

| Check | What it proves |
|---|---|
| [`test_retail_dashboard_builders.py`](../backend/tests/test_retail_dashboard_builders.py) | The API payload reproduces the checked-in fixture field for field, so evaluating from the catalogue moved no number |
| `verify_engine_chain` in [`build_inventory_risk_fixture.py`](../scripts/build_inventory_risk_fixture.py) | The catalogue rebuilds all 800 chain rows from the workbook's own ENGINE sheet |
| `verify_store_derivation` (same file) | f01/f02/f03 reproduce all 16,000 `ENGINE_STORE` rows |
| [`test_retail_engine_formula_contract.py`](../backend/tests/test_retail_engine_formula_contract.py) | The payload carries every id the browser engine refuses to start without |
| `engine.test.js` | Zero levers return the fixture unchanged across all 800 rows |

The last one is the one that keeps the two engines honest: a lever at zero is
the setting the workbook itself was calculated at (`Constants` B16–B21), so
agreement there means both engines start from the same place.
