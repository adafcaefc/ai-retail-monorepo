# A3 "Requirement vs inbound supply" — the decisions behind the chart

Decision record, 2026-08-21. Supersedes
[A3_REQUIREMENT_CHART_FINDINGS.md](./A3_REQUIREMENT_CHART_FINDINGS.md), which
describes the chart as it was before any of this and is kept only as history.

Written because most of what this panel does now is a judgement call with an
alternative that looks equally reasonable from the outside. Each section says
what was chosen, what it was chosen over, and what it costs.

Code: [selectors.js](../frontend/src/agents/retail/replenishment/data/selectors.js)
· `computeRequirement`,
[RequirementVsInboundPanel.jsx](../frontend/src/agents/retail/replenishment/components/RequirementVsInboundPanel.jsx),
[generate_synthetic_inbound_16w.py](../scripts/generate_synthetic_inbound_16w.py),
[dashboard.py](../backend/src/llm/agents/retail/replenishment/dashboard.py).

---

## 1. Everything on the chart is a rate

The panel has been wrong three times, and every time it was the same mistake:
two different *kinds* of quantity sharing one axis.

| | the cover line was | against demand |
|---|---|---|
| v1 | a running total (~29M) | 16× |
| v2 | a stock — units on the shelf | 2.9× |
| **v3** | **a rate — units arriving per week** | **~1.0×** |

v1 diverged without bound, so the panel reported "Cover runs out at W+1" for
every scope on the board. v2's gap was arithmetically correct — a shelf
restocked fortnightly *has* to hold about two weeks of demand — but it was the
wrong quantity to draw beside a weekly rate, and it read as a 3M surplus.

Now *Actual demand*, *Requirement* and *Inbound supply* are all units per week.
Demand out per week against stock in per week.

**Cost.** The stock is genuinely useful and is no longer a line. It is kept as
`on_hand_after`, shown in the tooltip, and it is what `cover_runs_out` is
derived from — a week where inbound dips under demand is ordinary and the shelf
absorbs it, so reading shortfall off the gap between the lines would flag 8
weeks in 16 as needing a purchase order.

## 2. Today is a real point, carried by both demand series

History used to stop at W-1 and the forward curves start at Today, with
`connectNulls={false}` between them, so the chart drew a visible gap at the
divider.

The fix is *not* to bridge across a null: that would draw a line between
quantities that were never the same thing. Today carries W-1's measured value
in both `actual_demand` and `requirement` — the same number written twice, not
an interpolation — so the two series meet at a point they genuinely share.
`connectNulls` stays `false`.

## 3. The synthetic inbound table

No table in this warehouse records when an inbound order arrives. The workbook
stores how much is on order (`open_po_qty`) and never a date. With only a lead
time to go on, the chart placed every open PO on its SKU's lead day; all three
routes lead under a week, so everything landed in W+1 and cover was flat
afterwards.

`synthetic.inbound_store_sku_16w` invents the missing arrival calendar, and is
labelled synthetic everywhere it surfaces (`DERIVATION`, the manifest, the
caveat under the chart).

**Demand-anchored.** Total arrivals across the horizon reproduce total forecast
demand. This is what stops the gap running away — an inbound stream that
under-delivers by construction would reproduce the defect it replaced.

**Batched by store, ranked within vertical.** Delivery frequency follows store
volume: the smallest 5% of each vertical's stores share a fortnightly
consolidation run, everyone else receives weekly. All of a store's SKUs travel
on that store's calendar whatever route they came in on, because one truck
carries the lot.

Ranking **within each vertical** is load-bearing and was got wrong first. Mean
store volume differs about tenfold between verticals — HNL averages 40,631 over
the horizon against GRC's 390,265 — so a chain-wide "smallest 12%" selected
whole verticals rather than small stores inside each: 14 stores in HNL, 5 in
ELC, and **zero in the other six**. Six of eight scopes drew a flat line while
the chain-level figure sat comfortably inside its band.

**The dial is coarse.** Verticals hold 20 stores each, so the share resolves to
a whole number of stores — two usable settings, not a continuum:

| stores per vertical | chain gap | per-vertical |
|---|---|---|
| 2 | 5.93% | 5.3 – 6.4% |
| **1** | **2.88%** | **2.7 – 3.2%** |
| 0 | flat, rejected by gate 2 | |

## 4. Four generation gates

The schedule is invented, so the properties it must have are asserted rather
than eyeballed. `generate_synthetic_inbound_16w.py` refuses to write the file
otherwise, and `build_replenishment_fixture.py` re-checks the first at build
time.

| gate | why | measured |
|---|---|---|
| inbound/demand ratio in [0.98, 1.02] | no creep | 1.0001 |
| max gap from weekly demand ≥ 0.5% | the line is visible at all | 2.88% |
| max gap from weekly demand ≤ 4% | it reads as one comparison | 2.88% |
| every vertical above the floor | **the chain figure hides flat scopes** | 2.71% weakest |

The fourth exists because of the failure in §3: a chain-level check cannot see
a vertical drawing a flat line, and this board is almost always read through a
legal-entity filter.

## 5. History inbound is modelled at a flat 97%

The supply line used to start at Today, leaving the 16 history weeks bare.

No table records past receipts. What *can* be said is narrow: over 16 weeks the
chain neither ran dry nor buried itself, so receipts must have tracked sales
closely — slightly under, because the position the board opens with today is
lower than it was. So history draws at a flat `HISTORY_INBOUND_RATIO` (0.97) of
that week's measured demand.

**Flat, not shaped.** A fabricated wiggle would imply weekly receipt data
nobody has. A flat offset reads as what it is: one assumption applied evenly.
The caveat says so and the history tooltip labels the figure "modelled".

`on_hand_after` stays null across history and is deliberately not
back-computed — running a modelled inbound backwards would compound 16 weeks of
assumption into a stock figure the tooltip would then state as though counted.

## 6. The demand seam, and why it is fixed only here

`synthetic.demand_store_sku_32w` is two halves that were never joined.
`forecast_w1` is pinned to a measured value (v8.5's
`fact_inventory_daily.forecast_7d`); the 16 actual weeks were synthesised
independently of it. The result is a step at the divider:

| | W-2 → W-1 | W-1 → W+1 |
|---|---|---|
| chain | +0.74% | **+4.32%**, 5.9× |

Every vertical shows it, between +4.20% and +4.42%. On screen it reads as a
spike at Today that no demand event caused.

`join_history_to_forecast` in
[dashboard.py](../backend/src/llm/agents/retail/replenishment/dashboard.py)
multiplies history by a single factor — shape untouched, level moved — so the
last actual week runs into `forecast_w1` at the rate history was already
growing. It continues that trend rather than landing exactly on `forecast_w1`,
because equal values would draw a flat segment across the divider, which is its
own artifact. `forecast_w1` is never modified, so the `ads × week_factor`
calibration still holds. `verify_demand_seam` checks the result at build time:
now +0.74% against +0.73% for the week before.

**The decision.** The seam is a defect in shared data, and A1's Demand Trend
reads the same table, so the source would be the better place to fix it. It was
fixed in A3's two loaders instead — the fixture builder and the backend query —
as a deliberate call to keep the blast radius on this board, since correcting
the table moves A1's history by about 4% as well.

> **Known consequence:** A3 and A1 draw slightly different history for the same
> SKUs until the seam is fixed at source. If A1 is ever corrected, delete
> `join_history_to_forecast` and its two call sites rather than leaving both
> corrections stacked.

## 7. The y-axis is framed on its data, not anchored at zero

Every series is a weekly rate in one narrow band — demand runs 1.60M to 1.91M.
Anchored at zero the axis spent 80% of its height on empty space and squeezed
the comparison into the top tenth of the panel: a real 2.4% swing came out as
6 pixels, and the demand curve's genuine 19% climb across the horizon was 44
pixels of near-flat line.

Framed on the plotted values with 20% padding, and the panel grown 280px →
380px:

| | before | after |
|---|---|---|
| ripple, peak to mid | 6.2px | 34.0px |
| backbone W-16 → W+16 | 43.7px | 239.6px |

**This is not automatic.** A non-zero baseline flatters data and needs a
reason. The reason here is that this is a comparison of two *like* quantities
rather than a magnitude chart, and the axis ticks state the range they cover so
nothing is concealed. A bar chart would stay anchored at zero. The rationale
sits in the component so it is not copied to a chart where it does not hold.

## 8. What is deliberately not reproduced

- **The mockup's 1.02 lift on requirement.** In no workbook cell, stands for
  nothing. Reproduced, it would read as a measured safety margin.
- **The mockup's every-fourth-week cover dips.** Invented shortfalls.
- **Spec 4's `#main-stats` strip** (reorder count, order quantity, PO value,
  fill). Those four are already the KPI cards immediately above the panel, read
  from the same selector — the strip restated them a few hundred pixels lower
  and gave the eye a second copy to reconcile against. The test asserts it is
  absent so it cannot drift back in.

## 9. Open

- The seam fix is A3-only; see §6.
- Two copies of the demand dataset exist — `resources/demand_store_sku_32w_poc_v1.csv`
  (read by A3) and `artifacts/demand_store_sku_32w_poc_v1.csv` (read by the
  newer `backend/scripts/load_demand_store_sku_32w.py`) — with two loaders and
  two DDL locations (`sql/retail/010`, `sql/synthetic/001`). Same data, two
  homes. Worth settling before it sets.
- A 104-week demand set now exists and may supersede the 32-week one this chart
  reads.
- 8 tests in `ReplenishmentDashboard.test.jsx` fail on a pre-existing assertion
  unrelated to this work: it rounds `avg_cover_days` to one decimal and then
  demands six-digit equality against a full-precision reference, so it cannot
  pass at any commit.
