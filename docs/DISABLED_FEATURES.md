# Disabled features — how to turn them back on

Three sidebar tiles are currently hidden. Nothing was deleted: each one is
commented out at its single point of registration, so the code, tests and
fixtures backing it are untouched and still on disk. This doc is the
reference for switching each one back on.

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

## Promotion Effectiveness

**Where:** `backend/src/llm/agents/modules.py`

`"retail.promotion_effectiveness"` is commented out of `ENABLED_MODULES`,
the single source of truth for both the backend registry and
`GET /api/html/agents` (which the frontend sidebar is built from). This is
the same mechanism already used above it to keep the Finance modules off —
see the docstring in that file. Nothing under
`backend/src/llm/agents/retail/promotion_effectiveness/` or
`frontend/src/agents/retail/promotion_effectiveness/` was touched; the
frontend override simply has no matching API id to attach to while disabled.

**To re-enable:** uncomment the `"retail.promotion_effectiveness"` line in
`ENABLED_MODULES`.

**Tests to restore** in `backend/tests/test_retail_module.py`: uncomment the
`("retail.promotion_effectiveness", "Promotion Effectiveness", "Ask
Promotion...")` entry in the `RETAIL_MODULES` tuple.

`backend/tests/test_retail_dashboard_builders.py` needed no change — it
imports the dashboard module directly by path rather than through
`ENABLED_MODULES`, so it already runs regardless of this flag.
