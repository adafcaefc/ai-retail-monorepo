# Manual validation — A2 Inventory Risk and A6 Assortment Optimization

The automated half of this lives in
[`backend/tests/test_a2_a6_workbook_baseline.py`](../backend/tests/test_a2_a6_workbook_baseline.py).
It proves the warehouse carries the workbook and that both agents' **tools**
return the workbook's figures. Run it first — everything below assumes it is
green, because a manual pass over a database that does not match the workbook
just discovers the same failure eight slower ways.

```bash
cd backend
./.venv/Scripts/python.exe -m pytest tests/test_a2_a6_workbook_baseline.py -q
```

What the automated suite **cannot** cover is the part that only exists at
runtime: whether the model reaches for the right tool, whether the number it
speaks is the number the tool returned, and whether the board and the chat
panel agree while a human is looking at both. That is what this document is
for.

---

## 0 · The baseline

Every figure below was read from the seeded warehouse and reconciled against
`resources/dbtemp/schema_with_data.json`. These are the numbers a correct
answer contains. Anything else on screen or in chat is a finding.

### A2 · Inventory Risk — ENGINE_STORE grain, 16,000 rows over 800 SKUs

Read straight off the `ENGINE_STORE` grid in `RM ENGINE DATA FOR RETAIL.xlsx`
with no filter applied, and confirmed against the workbook by the board's
owner. **Counts are DISTINCT SKUs; money and units sum every store row** — the
board follows the same split, so a count here is directly comparable with a
tile and a row count is not.

| Figure | Value |
|---|---|
| Rows (SKU × store) | 16,000 |
| SKUs | 800 |
| Inventory value | Rp 2,223,869,209,600 |
| At-risk value | Rp 873,041,521,900 |
| Stockout SKUs | **247** · Rp 148,200,588,900 at risk |
| Low SKUs | 457 |
| Below reorder point (Stockout + Low) | **524** |
| Overstock SKUs | **104** · Rp 47,633,362,800 excess |
| Slow-mover SKUs | **75** |
| Expiry SKUs | 11 · 5,624 units · Rp 124,355,878 write-off |
| Avg days of supply | 7.85 |

States, as distinct SKUs: Healthy 532 · Low 457 · Stockout 247 · Slow-mover 75
· Overstock 104 · Expiry 11. These do not sum to 800: a SKU healthy in one
store can be Stockout in another, and 393 SKUs are in both camps.

Per vertical — distinct SKUs, from the same grid:

| Vertical | Below ROP | Stockout | Overstock | Slow-mover | At-risk value |
|---|---|---|---|---|---|
| Grocery | 78 | 37 | 2 | 5 | Rp 4,457,260,000 |
| General Merch | 46 | 21 | 15 | 10 | Rp 31,254,454,300 |
| Fashion | 68 | 32 | 40 | 14 | Rp 73,171,687,700 |
| Health & Beauty | 78 | 39 | 4 | 7 | Rp 10,099,854,800 |
| Electronics | 55 | 25 | 14 | 10 | Rp 307,663,999,000 |
| Home & Living | 62 | 29 | 11 | 10 | Rp 67,309,259,400 |
| Digital | 70 | 32 | 9 | 10 | Rp 152,598,665,200 |
| Omnichannel | 67 | 32 | 9 | 9 | Rp 226,486,341,500 |

**Do not compare these with the workbook's `A2 Inventory Risk` summary sheet.**
That sheet is CHAIN-NET — it totals 345 below-ROP and 26 overstock SKUs over
the 800-row `ENGINE` rollup, where the grid holds 524 and 104. Both are right
about different questions. The board still carries the sheet as
`reference_by_vertical`, labelled as a benchmark from the other grain.

### A6 · Assortment Optimization — chain-net, 800 SKUs

| Figure | Value |
|---|---|
| SKUs | 800 |
| Delist candidates | **404** |
| Grow candidates | 12 |
| Hold | 384 |
| Tail SKUs | 200 (25.0%) |
| Average GMROI | 0.3336 |
| Contribution per day | Rp 63,999,028,330 |
| Capital freed by a full delist | Rp 1,258,870,351,500 |

Cutoffs (identical on the board and in the tools):

| Cutoff | Value |
|---|---|
| P25 GMROI, chain | 0.16491933 |
| P25 contribution, chain | 11,226,903.04 |
| P75 GMROI, within Healthy | 0.28496461 |
| P75 contribution, within Healthy | 125,553,001.15 |

### The two grains

This dataset carries the same inventory at two grains and both are correct.
Confusing them is the single most likely thing to go wrong in a manual pass.

| | Rows | Inventory value |
|---|---|---|
| Chain-net (`fact_inventory_chain_daily`) | 800 | Rp 2,223,694,053,300 |
| Per-store gross (`fact_inventory_daily`) | 16,000 | Rp 2,223,849,163,800 |

A2's `store_gross_*` block and A6's `store_gross` block are the per-store
grain. The board's A6 **state chart** (`by_state_value`) is also per-store, on
purpose. Everything else on both boards is chain-net.

---

## 1 · Setup

```bash
# backend — from backend/
uvicorn main:app --reload --port 8000

# frontend — from frontend/, API mode is the default (no VITE_DATA_SOURCE set)
npm run dev
```

Confirm the warehouse is the seeded one before anything else:

```bash
cd backend
./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); \
from src.db.db import get_engine; from sqlalchemy import text; \
print([ (t, get_engine().connect().execute(text(f'SELECT count(*) FROM retail.{t}')).scalar_one()) \
for t in ('fact_inventory_chain_daily','fact_inventory_daily','dim_item','dim_store')])"
```

Expect `800 / 16000 / 800 / 160`. Any other number and stop here.

---

## 2 · Board: fixture mode against API mode

The point of this step is that **nothing moves**. Both modes run the same
selectors; only the source of the rows differs.

1. Build or run the board in fixture mode (`VITE_DATA_SOURCE=fixture`, which is
   what `npm run build:standalone` sets). Screenshot A2's KPI row and A6's KPI
   row.
2. Switch to API mode (default `npm run dev`). Screenshot the same two rows.
3. Diff the screenshots.

**Pass:** every KPI identical, to the rupiah.
**Fail:** any difference at all — even a rounding one. The automated builder
test asserts field-for-field equality, so a visible difference means the board
is not reading what the test read.

Then, in API mode only:

4. Change the **legal entity** filter to Grocery on both boards. SKU counts
   must drop to 100. A2's at-risk value must become Rp 4,232,178,400.
5. Change it back to All. The figures must return to the table in §0 — not to
   something near them.

---

## 3.0 · What a correct answer looks like (applies to every ask below)

Check this once, then stop thinking about it. It is the same criterion for
every question in §3 and §4.

**The reader never sees JSON.** The tool's JSON reaches the model and stops
there. The model must return `FinanceAgentOutput.components[]`, each component
carrying a `format` (`text`, `bullet_list`, `table`, `chart`, `recommendation`,
`simulation`, `next_route`, `confidence`) and a `content` string matching that
format's schema. `render_ui_blocks()` turns those into HTML and chart blocks
and streams them over SSE.

So "how many SKUs should we delist?" arrives as a **card** — a text block whose
prose contains 404, probably a table of the per-vertical split, probably a
confidence block. Not `{"delist_candidates": 404}`.

Three ways that fails, and they look different on purpose:

| On screen | Cause |
|---|---|
| A box titled **"Unknown Component"** with JSON in it | `component.format` is not a recognised name — the model invented one (`list`, `json`, `data`). This is `render_unknown()` in `html_renderer.py`, the only path that puts raw content in front of a reader. |
| An empty card, or a heading with nothing under it | `content` was not valid JSON. `render_ui_blocks` swallows the parse error and passes `{}` to the renderer, so the block renders empty rather than wrong. |
| A well-formed text card whose paragraph is a JSON dump | `format` and `content` are both valid; the model pasted the tool payload into `content.content`. |

The third is the one to watch for. It renders perfectly and reads as garbage,
and no automated test can catch it — the schema is satisfied. Only a human
looking at the card will notice.

Record which of the three you saw; they point at different fixes.

---

## 3 · A2 chat

Open Inventory Risk and ask each of these. The **expected** column is what the
tool returns; the answer must contain that figure, not a figure near it.

| Ask | Expected | What a failure looks like |
|---|---|---|
| "How many SKUs are below reorder point?" | 302 | 106 (Stockout only) or 438 (a withdrawn workbook revision) |
| "How much inventory value is at risk?" | Rp 732,540,101,900 | The full Rp 2.22t — that is inventory, not risk |
| "Break the at-risk value down by state." | Low 358.8b · Slow-mover 202.9b · Stockout 112.0b · Overstock 58.5b · Expiry 0.45b · Healthy 0 | Healthy carrying any at-risk value |
| "How many expiry units, and where?" | 6,252, all Grocery | Units spread across verticals |
| "Which vertical has the most capital at risk?" | Electronics, Rp 222,864,021,100 | Any other vertical named first |
| "How many SKUs are overstocked?" | 40 | 91 (overstock + slow-mover collapsed together) |

**Grain trap — ask this one deliberately:**

> "Which stores have the most at-risk SKUs?"

The answer must be per-store **and say so**. The snapshot hands the model a
`store_gross_note` warning that these counts are gross and exceed the chain
figures. An answer that presents a store count as if it were a chain total, or
that adds store counts up to a total, is a real failure — it is the one this
dataset is built to provoke.

**Cross-agent trap:**

> "Should Replenishment or Pricing fix the at-risk value?"

This is a shipped starter prompt and no single board answers it. A good answer
splits the 302 below-ROP SKUs (a Replenishment decision) from the 91 overstock
and slow-mover SKUs (a Pricing/markdown decision) rather than recommending one
lever for all of it.

---

## 4 · A6 chat

| Ask | Expected | What a failure looks like |
|---|---|---|
| "How many SKUs should we delist?" | 404 | 106 — that is the stale `A6` sheet's own column B, see §6 |
| "How much capital would delisting the tail free?" | Rp 1,258,870,351,500 | Rp 1,258,863,668,500 — the pre-fix off-by-one, see §6 |
| "What is our average GMROI?" | 0.3336 | Anything in the single digits — the sheet's stale GMROI column |
| "How big is the tail?" | 200 SKUs, 25% | Any share that is not a quarter |
| "Which SKUs should we grow?" | 12 candidates | 0, or a number in the hundreds |
| "Name the worst delist candidates." | ≤12 named SKUs, worst first by capital freed, each with why it qualified | An unranked list, or a count presented as a list |
| "What is the daily contribution?" | Rp 63,999,028,330 | Rp 63,999,028,323 is the *per-store* figure — close enough to look right, which is exactly why it is listed here |

**Do the arithmetic out loud:** delist 404 + grow 12 + hold 384 = 800. If the
three numbers in one answer do not add to 800, the model mixed two scopes.

**Simulation:**

> "What if we only delisted the worst half?"

Expect 202 SKUs and Rp 1,231,837,842,500 freed. Then ask for the full 100%:
expect **404** SKUs (not 403) and the same Rp 1,258,870,351,500 as the headline.
That equality between the simulation and the snapshot is the check — they are
two different queries over one population and they must land on one number.

**Vendor and category:**

> "Which vendors should we review rather than cut line by line?"

Expect 8 vendors listed. Note that this dataset only *has* 8 vendors, and every
one of them carries at least 5 delist candidates — so "vendor review" catches
the whole population. Worth a judgement call from the business side about
whether that threshold is useful here; it is not a code defect.

---

## 5 · Monitoring

Hit **Recalculate** on both boards.

- A2 must run three passes: `stockout`, `expiry`, `overstock`.
- A6 must run three passes: `delist`, `grow`, `space`.

Check each raised alert cites a figure that appears in §0. The monitoring
passes each receive the whole snapshot inlined, so an alert quoting a number
that is not in the snapshot means the model invented it.

Specifically check the A6 `space` pass: it should raise categories losing half
their range or more, and vendors carrying five or more candidates — not
per-SKU delist recommendations, which is what the `delist` pass is for.

---

## 6 · Known findings to keep in view

**The `A6` workbook sheet is partly stale, by audit.** Columns B–F of
`A6!B6:F13` — delist, grow, GMROI, tail share, capital freed — are pasted
values from an old snapshot, flagged as AUDIT RC-2. The sheet says 106 delist
candidates; the engine says 404. **The engine is right.** Column G
(`contribution_day`) is outside that range, is live, and reproduces to the
rupiah. The automated suite asserts both halves of this — that G matches and
that B–F deliberately do not — so if the two ever line up, that is a
regression, not a fix.

The `A2` sheet, by contrast, is trustworthy end to end, which is why it is
carried into the snapshot as `reference_by_vertical`.

**Fixed on this branch:** `simulate_assortment_rationalization` at 100% acted
on 403 of 404 candidates. `percent_rank()` puts the last row at exactly 1.0 and
the filter was `< share`, so the smallest candidate fell off the end and the
simulation reported Rp 6,683,000 less capital than the snapshot's own headline
— two figures from one population, in one response, disagreeing. Now
`cume_dist() <= share`. Verify manually with the 100% simulation in §4.

**Worth a business judgement, not a bug:** chain-wide quartiles make all 100
Grocery SKUs delist candidates, because Grocery's daily contribution
(Rp 306m) sits an order of magnitude below Electronics' (Rp 17,478m) and the
P25 cutoff is taken across the whole chain. The classification is doing exactly
what it is defined to do. Whether "delist the entire Grocery range" is a
recommendation the board should surface is a product decision — and note that
scoping the board to Grocery re-derives the quartiles *within* Grocery and
gives a sensible answer, so the two views will differ. Expect that, and say
which one is being read.
