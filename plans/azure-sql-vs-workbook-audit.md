# Azure SQL against the workbook, and what the Retail boards still cannot read

Written when `feat/inventory-risk-ui` merged `main`. The question was narrow and
worth answering before anything else: **does `retail.*` in Azure SQL faithfully
represent the workbook?** It does. This records the reconciliation so nobody has
to derive it twice, and names the two things it does not carry.

Nothing here was run against Azure. Every figure comes from the checked-in
`sql/retail/001_create_retail_schema.sql`, `backend/src/retail_data_bootstrap/`,
and `resources/dbtemp/schema_with_data.json`.

## The row count reconciles exactly

| | rows |
|---|---:|
| Workbook extract | 21,939 |
| Azure `retail.*` (per the architecture handoff) | 21,571 |
| Difference | **368** |

**367** of those are 16 sheets deliberately not loaded — `a1`…`a9`,
`what_if_per_agent`, `what_if_simulator`, `uom_po_summary`, `vertical_rollup`,
`vendor_scorecard`, `constants`, `chart_series`. They are reporting and reference
sheets, not business rows.

The remaining **1** is `workforce`: 161 rows in the workbook, 160 in
`retail.WorkforceSnapshot`. The extra row is `store_id = 'TOTAL'`, a spreadsheet
total carrying `is_total`. **Dropping it is correct.** A totals row loaded as a
store would double every workforce figure that sums over stores.

Every other mapped sheet matches row for row:

| Azure table | Workbook sheet | rows |
|---|---|---:|
| `LegalEntity` | `verticals` | 8 |
| `Store` | `stores` | 160 |
| `Category` | `categories` | 160 |
| `Vendor` | `vendors` | 8 |
| `Brand` | `brand_performance` | 12 |
| `Sku` | `sku_master` | 800 |
| `TradeAgreement` | `trade_agreements` | 2,400 |
| `Promotion` | `promotion_discount_detail` | 48 |
| `InventorySnapshot` | `engine` | 800 |
| `StoreSkuSnapshot` | `engine_store` | 16,000 |
| `ReplenishmentProposal` | `replenishment_detail` | 800 |
| `BrandEvent` | `brand_events` | 23 |
| `MonthlySales` | `time_series_24mo` | 192 |

## Column-level: a normalisation, not a copy

Columns that look "missing" are relocated, not lost:

- `sku_master.category` → `retail.Category.category_name`
- `sku_master.sum_vert_size` → `retail.LegalEntity.total_store_size`
- `replenishment_detail.qty_on_hand` / `rop` / `max` → `retail.InventorySnapshot`,
  where they were always duplicated from
- `engine.perish`, `engine_store.seas` → `retail.Sku.is_perishable` /
  `seasonality_factor`

Azure also already carries the four columns this branch had to add to Postgres by
migration: `Sku.on_hand_days`, `Sku.stock_factor`, `Store.size_factor`,
`Store.health_factor`.

## The two gaps

These are the only facts the dashboards need that have no home in Azure.

### 1. `dashboard_label`

`verticals` carries both `short` and `dashboard_label`, and they differ on 2 of 8:

| | `short` | `dashboard_label` |
|---|---|---|
| GMR | Department Store | **General Merch** |
| DGT | Online | **Digital/Online** |

`retail.LegalEntity.short_name` is `short`. The A-sheets label those two
verticals the other way, so `reference_by_vertical` joins on `dashboard_label` —
substituting `short_name` mislabels two verticals on every board.

### 2. `agent_kpi_reference`

The `a1`/`a2`/`a3` sheets, 8 rows each. These are the figures every board is
reconciled against and the source of `reference_by_vertical`. Not loaded.

## A gap that is not one

Vertical ordering — Grocery first, not alphabetical — needs **no schema change**.
Every Azure table carries `source_row`, and for `verticals` it is monotonic with
sheet order (rows 6–13). `ORDER BY source_row` reproduces the workbook order.
This is worth knowing before anyone proposes adding a `sort_order` column.

## What a port would take

Not started, and deliberately so — `retail.*` is described as frozen, and the two
gaps need the schema owner's decision first (an additive `sql/retail/002_*.sql`,
or Python constants).

- `retail/common/warehouse.py`'s `_rows()` and `_scope_clause()` are the only two
  functions that touch the driver. The three builders never call SQLAlchemy
  directly, so that is the entire seam.
- SQLAlchemy cannot reach Azure as installed: no `mssql` dialect entry points, and
  the architecture handoff says not to replace the working driver stack. A port
  means `_rows()` over a raw `mssql_python` cursor, with `?` parameters instead of
  `:name`.
- Six `count(*) FILTER (WHERE …)` clauses are Postgres-only and become
  `SUM(CASE WHEN … THEN 1 ELSE 0 END)` — five in `inventory_risk/dashboard.py`,
  one in `replenishment/dashboard.py`.
- Table and column renames throughout: `dim_item`→`Sku`, `dim_store`→`Store`,
  `dim_vertical`→`LegalEntity`, `fact_inventory_chain_daily`→`InventorySnapshot`,
  `fact_inventory_daily`→`StoreSkuSnapshot`, `replenishment_proposal`→
  `ReplenishmentProposal`, `trade_agreement`→`TradeAgreement`,
  `fact_gmv_monthly`→`MonthlySales`.

## Running the tests after this merge

`EXCEL_WORKBOOK_PATH` is relative in `.env.example`, and `workbook_path()` used to
return it unresolved — so it depended on the process working directory. pytest runs
from `backend/`, found nothing, and 110 tests in `test_worked_example_cells.py`
skipped themselves as "workbook not deployed" while the file sat exactly where it
was configured. It now resolves against the repo root, matching
`retail_data_bootstrap/paths.py:resolve_workbook_path`. All 112 pass.

`generated/` is git-ignored and `test_retrieval.py` reads
`generated/retail_documents_sample.jsonl` unconditionally, so a fresh clone fails
that test until you run — offline, no Azure:

```
cd backend && ../.venv/Scripts/python.exe -m src.retail_data_bootstrap generate-documents
```
