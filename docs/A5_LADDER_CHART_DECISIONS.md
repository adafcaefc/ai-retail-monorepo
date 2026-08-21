# A5 "At-risk value: ladder vs no action" — the decisions behind the chart

Decision record, 2026-08-21 (revised the same day after a second round of feedback added a
history side, a Horizon control, a wiggle, and a stat strip — see §8 for what changed and why).
Same voice and purpose as
[A3_REQUIREMENT_CHART_DECISIONS.md](./A3_REQUIREMENT_CHART_DECISIONS.md): most of what this chart
does is a judgement call with an alternative that looks equally reasonable from the outside. Each
section says what was chosen, what it was chosen over, and what it costs.

Code:
[selectors.js](../frontend/src/agents/retail/pricing_markdown/data/selectors.js)
· `computeLadderHistory`,
[PricingRescueCharts.jsx](../frontend/src/agents/retail/pricing_markdown/components/PricingRescueCharts.jsx)
· `MarkdownLadderChart`,
[PricingMarkdownFilters.jsx](../frontend/src/agents/retail/pricing_markdown/components/PricingMarkdownFilters.jsx)
· the Horizon control,
[generate_synthetic_markdown_ladder_16w.py](../scripts/generate_synthetic_markdown_ladder_16w.py),
[dashboard.py](../backend/src/llm/agents/retail/pricing_markdown/dashboard.py)
· `_ladder_by_vertical`.

---

## 1. Both directions are a projection, not a history

The mockup's chart (`resources/[NEW] AI_360_Retail_Suite_v8.5_General_9Agents
20260819.html`, `pgA5`'s `ch-main`) draws 16 weeks of history and 16 of forecast, like
Replenishment's demand curve. Demand has real history to backtest against —
`synthetic.demand_store_sku_32w` fabricates its 16 actual weeks, but calibrates them against a
real workbook cell (`forecast_7d`) and A1's own accuracy metric. At-risk value has no such anchor:
it is a snapshot read off today's inventory position (f12/f14 over `fact_inventory_daily`), not a
rate anything backtests. There is no past reading of it anywhere in this warehouse to fabricate a
history against — this has not changed since the first version of this chart.

What changed on request: rather than dropping the history side (the first version's choice), it
is modelled the same way the forward side already was — one continuous assumption applied both
directions from a real anchor, not two different kinds of invention. `week: 0` ("Today") is the
one point on the chart that is genuinely real; every other week, on either side, is projected.

## 2. Today is not invented — and, as of §10, not even stored

`week: 0` is today's real, already-computed `at_risk_value`/`write_off_value` (the same f12/f14
formulas `build_pricing_markdown_fixture.py` and the live backend already run, and the same
numbers the Rescue waterfall and the "Value at risk" KPI tile already show). §10 moved this out of
`synthetic.markdown_ladder_store_sku_16w` entirely — `computeLadderHistory` (selectors.js) now
injects it from `dashboard.kpis` at render time instead of reading it out of a stored column, so
see §10 for the current mechanics; the reasoning below (today is real, not modelled) still holds.

Every other week — `-16..-1` (history) and `1..16` (forecast) — is where the chart becomes
synthetic, and is labelled as such everywhere it surfaces (table migrations, generator docstring,
manifest, the caveat under the chart).

## 3. Two rates, both read off the SKU's own real fields, one trend both directions

**No-action** accumulates going forward and recedes going back, along ONE linear trend through
today: `at_risk_value + offset x weekly_inflow`, where `weekly_inflow` is `at_risk_value x 0.025 x
growth_factor` and `growth_factor` is the SKU's own real SKU_Master `growth` index (0.91-1.39
across the whole catalogue), clamped to a defensive [0.8, 1.6]. A faster-growing SKU piles up
exposure faster ahead, and mirrors to having carried less of it 16 weeks ago. Going backward the
trend is floored at 20% of today's value (`HISTORY_FLOOR_FRACTION`) rather than let a slow-inflow
SKU's history run to zero and sit flat there for several weeks, which would read as measured, not
modelled. The 0.025 weekly rate and the 20% floor are both stated assumptions, not derived from
anything in the workbook — there is no real weekly at-risk accrual rate to read, in either
direction.

**Ladder** is not an independently invented curve. It is `no_action(offset) x (1 -
effective_recovery_rate)` at every offset except today (exact), where `effective_recovery_rate` is
the SKU's own real `recoverable_value / at_risk_value` — the same figure f14's elasticity-driven
recovery already implies — floored at 5% (`MIN_RECOVERY_RATE`) so a SKU with genuinely poor real
recovery still visibly separates from no-action. f14's own 0.95 cap already keeps the raw rate
under the generator's 95% ceiling for real data, so that clamp is a defensive no-op.

Tying the ladder line to the no-action line this way means both move together in absolute terms —
the ladder does not stay flat while no-action runs away, the way the mockup's fabricated curve
does. What it shows honestly is the gap: running the ladder means meaningfully less exposure at
every week, in the same proportion the SKU's own real recovery rate implies.

## 4. The wiggle, and why its phase is per-vertical

The first version's lines were smooth — a straight trend with no week-to-week texture, unlike the
mockup's visibly rippling reference. A deterministic sinusoidal wiggle (`WIGGLE_AMPLITUDE = 14%`,
`WIGGLE_CYCLE_WEEKS = 4`) is now applied multiplicatively to every week except today.

The phase is derived from `vertical_id`, not `sku_id` or a random draw, and this is load-bearing:
this table ships at (sku_id, store_id) grain, but every consumer sums it to 8 vertical rows before
the chart ever sees it. A phase that varied per SKU (random or hashed) would average out across
the ~2,000 rows in a vertical and cancel to a flat line on summation — reproducing the exact
smoothness problem the wiggle exists to fix. Phasing by `vertical_id` means every row in a
vertical ripples in lockstep, so the vertical (and chain) total ripples too, proportionally. The
phase function also runs on one continuous offset axis across the whole -16..+16 range, not two
separately-phased halves either side of "today," so the ripple reads as one texture through the
boundary rather than a seam.

## 5. Five gates

Mirrors A3's own §4: the properties are asserted, not eyeballed.
`generate_synthetic_markdown_ladder_16w.py` refuses to write the file otherwise. Gate 2 changed
shape from the first version — "no_action never decreases week over week" is no longer true by
design once a wiggle is applied, so it now checks the underlying TREND (pre-wiggle, re-derived
independently via `trend_value()`) instead, plus a non-negativity sweep across every generated
value.

| gate | why | measured (current run) |
|---|---|---|
| every candidate value equals trend x wiggle recomputed independently from that row's own real fields; non-candidates are zero throughout | today itself moved out of this table (§10), so this checks self-consistency of what IS stored, not a calibration against a stored anchor | exact, every row |
| the underlying trend never decreases going forward; no generated value is negative | genuine accumulation, not noise — checked independently of the now-permitted wiggle | true by construction |
| ladder separates from no-action at BOTH horizon edges, every at-risk row | the whole point of drawing two lines, on either side of today | true by construction (5% recovery floor) |
| every vertical clears a 3% separation floor at both edges | a chain-level check alone can hide a flat vertical (A3's own §3/§4 failure mode) | weakest vertical ~10-11% |

## 6. Horizon control lives in the filter bar, and never refetches

Mirrors `demand_forecasting`'s own Horizon control (`DEMAND_HORIZONS = [4, 8, 12, 16]`) exactly in
UI shape and placement — a segmented button group in the filter bar, not inside the chart's own
header. Unlike demand_forecasting's horizon (which changes what the backend computes, so moving it
reloads the dashboard), every week this chart could show is already computed and shipped in
`dashboard.ladder_history` — narrowing the horizon is a pure client-side slice
(`MarkdownLadderChart`'s `horizon` prop), never a network call. State is lifted to
`PricingMarkdownDashboard.jsx` but deliberately kept out of `scope`/`serializeScope`, so it cannot
accidentally start triggering a refetch later.

## 7. The stat strip is a deliberate exception to A3's own precedent

`docs/A3_REQUIREMENT_CHART_DECISIONS.md` §8 explicitly argues against a four-figure strip under
that board's chart, because the same numbers already sit in the KPI cards above the panel and a
second copy just gives the eye something to reconcile against. This chart adds one anyway (AT
RISK / RECOVER / WRITE-OFF / DEPTH, straight from `dashboard.kpis`, no new data) because it was
explicitly requested against a reference screenshot showing exactly that strip under this
specific chart. Recorded here rather than silently contradicting the earlier reasoning: the
argument in A3 still holds for A3.

## 8. What is deliberately not reproduced

- **Per-state "effective windows"** (Expiry 0-3 days / Overstock 14 days / Slow-mover 21 days).
  That language is mockup narrative describing a different table (the markdown ladder preview,
  not this chart) — it is not a real field anywhere in this codebase and was not smuggled into
  this projection as though it were measured.
- **A zero-anchored y-axis.** Framed on the plotted band instead, same reasoning and technique as
  `RequirementVsInboundPanel.jsx`.

## 9. Purely additive, twice over

First pass: one new table (`synthetic.markdown_ladder_store_sku_16w`, migration 012), one new
fixture/API field, one new chart. Second pass (this revision): one new migration
(`013_add_history_to_markdown_ladder_16w.sql`, `ALTER TABLE ... ADD` — 012 itself was never
edited), the same table widened from 34 to 66 columns, the same generator regenerated in place.
Nothing about `synthetic.demand_store_sku_32w`, `synthetic.inbound_store_sku_16w`, the two charts
shipped earlier in this same pass (Rescue waterfall, Elasticity vs depth), or any existing
KPI/candidate/simulation figure on this board is touched, regenerated, or renamed by either pass.
Confirmed both times by diffing the regenerated `fixture.json` against its pre-change version:
only `ladder_by_vertical` changes, field for field.

## 10. The off-by-one, and why today moved out of the table entirely

A user check against the rendered chart at the full 16-week horizon found the forward edge
stopping at W+15, not W+16. Root cause: the second revision's `no_action_w1`/`ladder_w1` stored
TODAY (offset 0), so the 16 forward columns actually spanned offsets 0..+15 — a "16-week forward
horizon" that was one week short of what it promised, the exact same shape of bug §1 of
`A3_REQUIREMENT_CHART_DECISIONS.md` describes for a different chart ("two different kinds of
quantity sharing one axis" — here, "today" and "N weeks out" sharing one column index).

Two fixes were available: add a 17th forward column, or stop storing today at all. The second was
taken. Today is never modelled — it is always a live figure, already computed and already
correct elsewhere on this exact board (`dashboard.kpis`, the Rescue waterfall, the "Value at risk"
KPI tile) — so storing a copy of it in a synthetic table was redundant even before the off-by-one
existed. Removing it fixes the bug (`w1..w16` now cleanly mean `+1..+16`, matching `hist_w1..
hist_w16` meaning `-1..-16`) and removes a duplicate source of truth in the same move.

`computeLadderHistory` (selectors.js) now takes `kpis` as a third argument and injects `week: 0`
from `kpis.at_risk_value`/`write_off_value` directly — no schema change, no new migration; the
existing `synthetic.markdown_ladder_store_sku_16w` columns just changed what offset each one
means, so this was a generator regeneration + reseed, not a DDL change. One side benefit: `week:
0` now reacts to the FULL current scope (category_group/store_id/state, not just
legal_entity_id), since `kpis` already does — a small improvement over the -16..-1/1..16 weeks,
which still only react to `legal_entity_id` (§5's documented limitation, unchanged).

Also fixed in the same pass: the DEPTH figure in the stat strip (§7) was rounded to a whole
percent (`{ digits: 0 }`); it now uses `formatPercent`'s default (one decimal), matching every
other percent figure on this board.
