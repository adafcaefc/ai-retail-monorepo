# Disabled features — how to turn them back on

Two sidebar tiles are currently hidden. Nothing was deleted: each one is
commented out at its single point of registration, so the code, tests and
fixtures backing it are untouched and still on disk. This doc is the
reference for switching each one back on.

Promotion Effectiveness was the third, and is back on as of 2026-08-15 --
`"retail.promotion_effectiveness"` is uncommented in `ENABLED_MODULES` and its
`RETAIL_MODULES` entry is restored in `backend/tests/test_retail_module.py`.
The original hide (`a3a3621`, 2026-08-14) recorded no reason, so if it was
hidden for a demo or a scope call rather than a defect, say so and it can go
back behind the comment the same way.

## What If Simulator

**Where:** `frontend/src/pages/main/what_if_simulator/index.js`

The page descriptor's `export default` is commented out, so
`frontend/src/pages/registry.js`'s `import.meta.glob` discovery finds no
default export in that folder and skips it (`buildPages()` filters out
anything without an `id`/`component`).

**To re-enable:** uncomment the `import` and `export default` block in that
file. Nothing else references it — `WhatIfSimulator.jsx` was never touched.

## Data Source

**Where:** `frontend/src/pages/main/data_source/index.js`

Same mechanism as above: the `export default` is commented out, so the page
is invisible to `registry.js`'s glob discovery. `DataSource.jsx`,
`SheetGrid.jsx` and `cellStyle.js` are untouched.

**To re-enable:** uncomment the `import` and `export default` block in that
file.

**Tests to restore** in `frontend/src/App.test.jsx` once this page is back:
- `PAGE_COUNT` — set back to `3` (Formula Manager, What If Simulator, Data
  Source).
- In `"opens on the Main section's first static page..."`, uncomment the
  three `expect(pages...)` assertions about Data Source sorting last.
- The two `it.skip(...)` tests — `"renders the Data Source viewer with the
  workbook's own formatting"` and `"opens the worksheet a cell deep link
  names, not the default page"` — change back to `it(...)`.

Note: `frontend/src/pages/main/formula_manager/FormulaManager.test.jsx`
already asserts `href="#main.data_source?cell=..."` on citation links; that
test needed no change and does not need reverting.

## Promotion Effectiveness — brought up to spec parity (2026-08-18)

Re-enabling (see the note at the top of this doc) shipped the module as it
stood on disk. It has since been brought up to parity with
`resources/A4_Promotion_Effectiveness_Dashboard_Spec.md`: a Store filter,
by-store/cluster/channel and inventory-state dimension charts, a by-channel
mainHTML chart, and CSV export on the Suggested Best Action panel, all
following the exact patterns `inventory_risk` and `replenishment` already
established for the same kind of gap. See
`backend/src/llm/agents/retail/promotion_effectiveness/dashboard.py` and
`frontend/src/agents/retail/promotion_effectiveness/` for the current shape.
