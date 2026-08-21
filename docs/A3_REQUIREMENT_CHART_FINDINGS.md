# A3 "Requirement vs inbound supply" — why the chart differs from the prototype

> **Superseded, kept as history.** This note describes the chart as it stood on
> 2026-08-19: a 28-day forward-only view accumulating a flat ADS
> (`REQUIREMENT_DAYS`, `demandPerDay * day`). None of that code survives. The
> chart is now 33 weekly points with three series in units per week, drawing on
> two synthetic tables that did not exist when this was written. For the current
> shape and the reasoning behind it, see
> [A3_REQUIREMENT_CHART_DECISIONS.md](./A3_REQUIREMENT_CHART_DECISIONS.md).
>
> Section 1 is still worth reading: it is the diagnosis that led to the rewrite.

Investigation note, 2026-08-19. Prompted by the question: why does the React panel not
look like the prototype's version of the same chart?

Sources examined:

- [RequirementVsInboundPanel.jsx](../frontend/src/agents/retail/replenishment/components/RequirementVsInboundPanel.jsx)
- [selectors.js](../frontend/src/agents/retail/replenishment/data/selectors.js) · `computeRequirement`
- [contract.js](../frontend/src/agents/retail/replenishment/data/contract.js) · `REQUIREMENT_DAYS`, `REQUIREMENT_NOTE`
- `resources/AI_360_Retail_Suite_v8.2_General_9Agents 20260806.html` (the prototype)
- `resources/dbtemp/schema_with_data.json` (30-table workbook dump)
- [warehouse.py](../backend/src/llm/agents/retail/common/warehouse.py) · `constants()`

All numbers below are measured against the bundled fixture
(`frontend/src/agents/retail/replenishment/data/fixture.json`, 800 lines).

---

## 1. Four reasons the chart looks different

Every one of them is by construction, not a bug.

### 1.1 The React chart plots a running total; the prototype plots a level

[selectors.js:378](../frontend/src/agents/retail/replenishment/data/selectors.js#L378)
is `requirement: demandPerDay * day` — cumulative demand. The cumulative sum of a flat
rate is a straight line; no shape survives that integration.

The prototype's `req` is *per-period* demand (prototype line 1820), which is why it
oscillates.

### 1.2 There is no day-of-week curve in the data

The prototype shapes every point with `DOW[i%7]` plus random jitter
(`0.9 + r()*0.2`). The React ADS is one flat number per SKU summed across scope — the
workbook stores one ADS per SKU and no daily profile, so there is nothing to wiggle.
The docstring above `computeRequirement` already states this as a deliberate call.

### 1.3 No history half

The prototype runs `histN: 28` periods backwards, which is where its `D-28` axis and
its split line at today come from. The React loop is
[`for (let day = 0; day <= days; day += 1)`](../frontend/src/agents/retail/replenishment/data/selectors.js#L369)
— it starts at today, so the entire left side of the prototype does not exist.

### 1.4 No period toggle

Daily / Weekly / Monthly / Quarterly / Yearly is prototype-only state (`PERIODS`,
`setPeriod`, `periodMeta`). `ReplenishmentDashboard.jsx` has no period state at all,
and the horizon is fixed at `REQUIREMENT_DAYS = 28`
([contract.js:131](../frontend/src/agents/retail/replenishment/data/contract.js#L131)).

### 1.5 The flat green line is correct, not broken

In the prototype, "cover" is literally the demand curve times 0.88–1.08 (line 1820) —
it hugs requirement because it *is* requirement with noise on it. There is no
inventory in it at all.

The React version is real inventory:

| | Units |
|---|---|
| On-hand | 1,693,209 |
| Total open PO | 25,424 (1.5% of on-hand) |
| Cover at D+0 | 1,693,209 |
| Cover at D+28 | 1,718,633 |
| Requirement at D+28 | 6,224,562 |

All open PO lands by D+7 (lead days 2/4/7), so cover rises 1.5% and then stops. On a
0–8M axis that reads as flat. The two lines cross at D+7 and diverge because that is
what the data says.

### 1.6 The 1.02 lift was deliberately not copied

The prototype multiplies requirement by 1.02. Both
[selectors.js](../frontend/src/agents/retail/replenishment/data/selectors.js#L358-L361)
and
[RequirementVsInboundPanel.jsx](../frontend/src/agents/retail/replenishment/components/RequirementVsInboundPanel.jsx#L50-L53)
document that this was intentionally not reproduced, on the grounds that an invented
2% would read as a measured safety margin.

---

## 2. Can requirement be plotted per-period?

Yes — but one thing breaks first.

### 2.1 The cover series does not survive the switch

Requirement is a **flow** (units/day) and can be plotted per-period. "Inbound +
on-hand cover" is a **stock** — 1,693,209 units sitting on shelves today. A stock has
no per-day value. On a per-period axis the only genuinely per-period part is inbound
arrivals:

| Day | Arrivals |
|---|---|
| D+2 | 1,404 |
| D+4 | 21,389 |
| D+7 | 2,631 |
| all others | 0 |

Three spikes and a flatline. The prototype dodges this entirely by faking `inb`.

**Consequence:** per-period is a legitimate chart, but a different one — demand per
day, with on-hand as a horizontal reference line rather than a series. The two curves
only share an axis in the cumulative view.

### 2.2 Three options for the requirement line

| | Change | Data backing | Result |
|---|---|---|---|
| **A. Flat per-period** | `demandPerDay * day` → `demandPerDay` | Complete | Horizontal line at 222,306 u/day. ADS is an average rate; nothing to oscillate. Arguably worse than the cumulative view, which at least shows a crossing point. |
| **B. DOW-shaped** | multiply by `DOW[day % 7]` | Partial — see below | 188,960 → 300,113 u/day sawtooth. This is what makes the prototype look like the prototype. |
| **C. Monthly** | derive from `time_series_24mo` | Real, wrong grain | See section 3. |

### 2.3 Provenance of the DOW curve

`[0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25]`

| Real | Not real |
|---|---|
| `Constants!B7 = "DOW sum (7-day)" = 7.45` | The seven individual multipliers |
| Piped through as `dow_sum` in [warehouse.py:237](../backend/src/llm/agents/retail/common/warehouse.py#L237) | Appear only in the prototype JS (line 442) and [A1_Demand_Forecasting_Dashboard_Spec.md:142](../resources/A1_Demand_Forecasting_Dashboard_Spec.md#L142), which documents the prototype |
| Formula `f08` is literally `ADS × 7.45` | Infinitely many curves sum to 7.45 |

This is **not** the same case as the 1.02 lift. 1.02 stood for nothing anywhere. The
DOW curve is a named model parameter, its sum reconciles to a workbook cell, and it is
already the stated basis of A1's forecast-7d KPI. Adopting it is defensible — it just
has to be sourced as a spec constant, never implied to be measured.

### 2.4 Trap: DOW's mean is not 1.0

`7.45 / 7 = 1.0643`. A week is 7.45 ADS, not 7 ADS.

If per-day demand is shaped by DOW and then re-cumulated, the 28-day total moves
**6,224,562 → 6,624,713 (+6.4%)** and `cover_runs_out` shifts earlier. That is the
invented-safety-margin problem again, wearing a workbook cell as a disguise. Avoid it
by never re-cumulating a DOW-shaped series.

### 2.5 No precedent to copy

- The workbook has **no per-day requirement series anywhere**. `chart_series` (226
  rows) holds only the four breakdown bar charts per agent — no time-series block.
- **A1's React implementation has no DOW curve either.** There is no existing
  implementation in the codebase to follow.
- The `verticals` table carries a `peak_season` scalar, not a 12-month curve.

---

## 3. `time_series_24mo` — what it is and whether it helps

### 3.1 Where it lives

| | |
|---|---|
| Workbook sheet | **`Time Series 24mo`**, header row 5 |
| Shape in sheet | 8 wide columns, one per vertical |
| Normalized | 192 rows of `(month, vertical_id, gmv)` |
| Database table | **`retail.MonthlySales`** — `period_label`, `legal_entity_id`, `sales_amount` |
| DDL | [001_create_retail_schema.sql:377](../sql/retail/001_create_retail_schema.sql#L377) |

The only consumer today is the chat retrieval layer
([capabilities.py:118](../backend/src/retrieval/capabilities.py#L118), capped at 24
rows). **No dashboard builder queries it** — not A1, not A3. Using it means a new
accessor in `warehouse.py` plus a query in the A3 builder.

### 3.2 It is not history

[demand_forecasting/dashboard.py:22](../backend/src/llm/agents/retail/demand_forecasting/dashboard.py#L22)
already states it: *"Its second year is byte-identical to its first in all eight
verticals."* Verified — year 2 equals year 1 exactly, for every vertical.

It is one seasonal profile written twice. Year-on-year growth is zero by construction,
so it cannot back a `D-28` actuals line or any trend claim.

### 3.3 What it legitimately is: twelve seasonal indices

Normalizing each vertical's year against its own mean:

| Vertical | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Grocery | 0.91 | 0.88 | 0.94 | 0.96 | 1.01 | 1.05 | 1.08 | 1.06 | 0.98 | 0.95 | 1.02 | **1.16** |
| General Merch | 0.94 | 0.88 | 0.96 | 1.01 | 1.08 | 1.03 | 0.92 | 0.96 | 0.99 | 0.96 | 1.05 | **1.23** |
| Fashion | 0.93 | 0.88 | 0.97 | 1.04 | 1.13 | 1.08 | 0.91 | 0.88 | 0.98 | 0.95 | 1.04 | **1.22** |
| Health & Beauty | 1.01 | 0.98 | 0.95 | 0.96 | 1.03 | 1.01 | 1.00 | 0.99 | 0.97 | 1.00 | 1.04 | 1.09 |
| Electronics | 0.93 | 0.88 | 0.92 | 0.95 | 0.98 | 1.01 | 0.95 | 0.93 | 0.99 | 1.03 | 1.12 | **1.31** |
| Home & Living | 0.97 | 0.91 | 0.95 | 1.00 | 1.08 | 1.02 | 0.93 | 0.95 | 0.99 | 0.98 | 1.04 | **1.19** |
| Digital/Online | 0.93 | 0.86 | 0.90 | 0.94 | 0.97 | 0.95 | 0.92 | 0.94 | 0.99 | 0.97 | 1.28 | **1.37** |
| Omnichannel | 0.94 | 0.88 | 0.94 | 0.98 | 1.04 | 1.00 | 0.93 | 0.95 | 0.99 | 0.97 | 1.11 | **1.28** |

Better than the prototype's hardcoded `SEAS_DRY` / `SEAS_FRESH` arrays: derived from
workbook cells and reconcilable.

### 3.4 Problem: it contradicts the seasonality already in use

The per-SKU `seasonality_index` is a *typed* workbook value, not derived from this
series. The two disagree for every vertical:

| | Grocery | Gen Merch | Fashion | H&B | Electronics | H&L | Digital | Omni |
|---|---|---|---|---|---|---|---|---|
| Typed `seasonality_idx` | 1.14 | 1.00 | 0.98 | 1.05 | 1.02 | 1.00 | 1.04 | 1.02 |
| Derived (month 6) | 1.08 | 0.92 | 0.91 | 1.00 | 0.95 | 0.93 | 0.92 | 0.93 |

The ratios are not constant (1.05 to 1.13), so no single factor reconciles them. ADS
is already built on the typed value (`base_ads × seasonality × store_size`). Pulling
the curve in without reconciling puts two disagreeing seasonality numbers in one
dashboard — the "a second home for one number is how two numbers appear" failure that
`warehouse.constants()` warns about.

### 3.5 Problem: wrong grain, three ways

Rupiah not units; vertical not SKU; monthly not daily. On a 28-day horizon it
collapses to a single number — the current month's index — which the lines already
carry.

---

## 4. Conclusions

- **The current chart is not broken.** Every difference from the prototype is a
  deliberate choice, and the flat cover line is what the inventory data actually says.
- **The prototype's green line is not inventory** — it is the demand curve with noise
  applied. Matching it visually means giving up the chart's actual meaning.
- **Per-period is possible** but changes what the second series can be: on-hand
  becomes a reference line, not a curve.
- **`time_series_24mo` does not help a daily chart.** The shape problem is
  day-of-week; there is nothing daily in that table.
- **For a Monthly toggle**, `time_series_24mo` is the right and only source, and it is
  real — provided it is derived once in `warehouse.py`, reconciled against the typed
  `seasonality_idx` (or the divergence documented), and never drawn as an actuals line.

### Recommendation

For the daily chart: **day-of-week shaping on the requirement line, on-hand as a
reference line rather than a series.** Declare the DOW array as a named spec constant
beside `REQUIREMENT_NOTE`, with a comment recording that the workbook pins only its
sum. Never re-cumulate the shaped series (section 2.4).

### Open decisions

1. Daily DOW-shaped chart, or start with the flat per-period one-line change to see
   whether a level chart reads better than the cumulative one?
2. Is a Monthly/Quarterly toggle wanted at all — and if so, is reconciling the two
   seasonality sources in scope?
