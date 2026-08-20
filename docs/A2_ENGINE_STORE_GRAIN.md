# A2 Inventory Risk: why the cards moved to ENGINE_STORE

Date: 2026-08-20. Companion to
[A2_KPI_FORMULA_PAIRING.md](./A2_KPI_FORMULA_PAIRING.md), which answers "which
rule does this tile run". This file answers a different question: **which rows
does it run that rule over**, and why the answer changed.

## The report

The Slow-moving SKUs tile read **37**, and the board's owner said the workbook
says otherwise. The first diagnosis — "the slow-mover formula isn't being
computed in the backend" — turned out to be wrong, and the conclusion right.

`f07-inventory-state` *was* being evaluated live, per row, on every load, read
from the `retail.formula` table
([inventory_risk/dashboard.py](../backend/src/llm/agents/retail/inventory_risk/dashboard.py)'s
`build_items`). Nothing was hardcoded and nothing was stale.

The rule was right. The population was not.

## Two sheets, two answers

The workbook carries the same decision at two grains:

| Sheet | Rows | What one row is |
|---|---|---|
| `ENGINE` | 800 | one SKU, netted across its stores |
| `ENGINE_STORE` | 16,000 | one SKU **at one store** — "the Formula Manager's primary source" |

`items` read `ENGINE` (via `fact_inventory_chain_daily`). Netting is what
produced 37: a SKU slow-moving in six stores and healthy in fourteen nets to
healthy and disappears from the count. The grid a buyer actually filters holds
**755 slow-moving rows across 75 distinct SKUs**.

## What the numbers had to match

Three figures were quoted from the workbook's own dropdown, reproduced exactly
from `resources/dbtemp/schema_with_data.json` before any code changed:

| Workbook | Reproduced | Rule |
|---|---|---|
| Stockout risk 247 | 247 | distinct SKUs with `Position < 0.6 × ROP` (f07's first branch) |
| Risk value 1482… | 148,200,588,900 | Σ at-risk value over Stockout rows |
| Overstock 47,633,362,800 | 47,633,362,800 | Σ (Position − Max) × Price over Overstock rows |

Nine more were predicted from the pattern and confirmed by the owner. The
pattern is the contract this board now follows:

> **Source = ENGINE_STORE. Each tile is scoped to its own state's rows. Counts
> are DISTINCT SKUs. Money sums every row, over the problem portion only —
> Stockout the whole position, Overstock the excess above Max, Expiry the
> units past shelf life.**

`scripts/build_inventory_risk_fixture.py` pins all twelve
(`EXPECTED_CHAIN_KPIS` / `EXPECTED_CHAIN_MONEY`) and refuses to write a fixture
that drifts.

## The numbers

| Tile | Was (chain) | Now (grid) |
|---|---|---|
| Slow-moving SKUs | 37 | **75** (755 rows) |
| Stockout SKUs | — | **247** · Rp 148,200,588,900 |
| Low SKUs | — | 457 |
| Below reorder point | 302 | **524** (7,090 rows) |
| Overstock SKUs | 26 | **104** · Rp 47,633,362,800 excess |
| Expiry SKUs | 8 | 11 · 5,624 units · Rp 124,355,878 |
| Inventory value | — | Rp 2,223,869,209,600 |
| At-risk value | — | Rp 873,041,521,900 |

## Where the rule itself comes from

Worth stating plainly, because "is it hardcoded, or read from the JSON, or
actually the database?" is the first question anyone asks:

| Path | Catalogue source |
|---|---|
| Live API — `dashboard.build()` | `warehouse.formulas()` → `_catalogue()` → `repository.load()` → `SELECT … FROM retail.formula`, **uncached, every request** |
| Fixture builder — `scripts/build_inventory_risk_fixture.py` | the same `repository.load()`, so the fixture is built from the table too |
| Offline bundle — `fixture.json` | a **frozen copy** of the above, written at build time |

`resources/dbtemp/formula.json` is the **seed** for that table
(`scripts/import_formulas_to_db.py`), not a runtime source. Nothing under
`backend/src/` reads it — `constants.FORMULA_STORE` still names the path but
has no remaining reader.

Demonstrated rather than asserted: patching `f07`'s expression in memory (
`velocity < 1` → `velocity < 2`) through `repository.load` moves the board's
slow-moving count **75 → 368**, and restoring it returns **75**. A hardcoded or
JSON-backed rule could not do that.

**The one gap.** A standalone bundle (`npm run build:standalone`, which sets
`VITE_DATA_SOURCE=fixture`) evaluates the frozen expressions, so a rule edited
in the Formula Manager does not reach it until the fixture is rebuilt. The
default build has no such flag and talks to the API, where there is no gap.

Note A5 and A6's fixture builders still read `formula.json` directly
(`FORMULA_CATALOGUE`) rather than the table. A2's does not; that difference is
worth closing, in that direction.

## Counts are distinct SKUs — the trap

`.length` over the rows is wrong by roughly 10x and looks entirely plausible.
`computeKpis` uses `distinctSkus`; `kpis_for` in the fixture builder and the
`count(DISTINCT item_key)` in
[tools/inventory_data.py](../backend/src/llm/agents/retail/inventory_risk/tools/inventory_data.py)
do the same, so the card, the fixture and the chat answer cannot disagree.

Distinct counts do **not** add up across stores, and that is not a defect:

- Healthy 532 + non-Healthy 661 > 800, because **393 SKUs are both** — healthy
  in some stores, in trouble in others.
- The two Suggested-Best-Action routes overlap by **33 SKUs** that need
  replenishing at one store and marking down at another. Chain-net could not
  represent that at all; the two positions cancelled and the SKU read Healthy.

They *do* add up across categories and verticals, since a SKU belongs to one of
each.

## What this deliberately broke

**The `A2 Inventory Risk` summary sheet no longer matches the cards.** That
sheet is chain-net: 345 below-ROP and 26 overstock SKUs. It is still carried as
`reference_by_vertical` and still asserted — as a benchmark from the other
grain, not a target. `reconcile()` in the fixture builder used to diff against
it and would now fail by construction, so it was repointed at the grid figures
above rather than deleted.

**`atStore` and `f02-on-hand` are gone.** They reconstructed a store's row from
SKU × store attributes so a chain-net board could show one store. The board
ships the grid now. Worth recording: the reconstruction was *slightly wrong* —
for GRC-001 at S001 it returned ROP 88 / Max 204 / ADS 29.1669 where the
workbook holds 86 / 201 / 28.7556, because it rebuilt ROP from a lead time the
grid does not use. Reading the row fixed a ~2% error in a panel whose whole
claim was exactness.

## Cost

| | Chain | Grid |
|---|---|---|
| `fixture.json` | 759 KB | 14.1 MB |
| `build()` on the live API | — | 19.6 s, 15.8 MB payload |

The formula evaluation is **not** the expensive part: 16,000 rows × 11
expressions is 1.05 s. The cost is the SQL fetch (7.7 s for 16,000 joined rows
from Azure SQL) and serialising the payload. A5 Pricing & Markdown made the
same trade in `c48cdfa` (15.2 MB). If the live API path matters more than the
bundled-fixture path, caching the payload per scope is the obvious lever — the
dataset is a single fixed snapshot date and never changes between requests.

## Still open

- **A5 Pricing & Markdown counts rows, not SKUs.** `c48cdfa` moved it to
  ENGINE_STORE grain and reported **1,638 candidates**, which is the row count;
  under the convention confirmed here it should be distinct SKUs. That commit
  message also states 1,638 matches the A5 sheet — the sheet says **71**, which
  is the chain-net figure (8 Expiry + 26 Overstock + 37 Slow-mover). Both the
  number and its justification need revisiting.
- **The +20% What-If scenario has never reconciled**, and this change did not
  affect it: with HEAD's engine and HEAD's chain fixture it produces the same
  figures it does now (GRC 121,891 against the workbook's 148,300, ~82% across
  all eight verticals). `engine.test.js`'s
  "reproduces the workbook's published +20% demand scenario" has been left
  failing rather than adjusted to pass.
