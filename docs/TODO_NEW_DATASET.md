# To-Do — Migrating to `Dataset_AI_Finance_Forum_V1.0`

**Status:** work plan. Supersedes the Indonesian `07_To_Do_List` sheet in the QC tracker,
which was written against the old four-workbook dataset and lists every finding as
*Belum selesai* even where the fix has since landed.
**Date:** 31 July 2026
**Decision it assumes:** Option C — incremental migration, one agent at a time
(see [DATASET_MIGRATION_OPTIONS.md](./DATASET_MIGRATION_OPTIONS.md) §7).

---

## 1. Where we actually are

Two things have to be separated, because the QC tracker conflates them:

**Fixed on the old dataset.** 27 findings are closed on branch `bug-fix-trial` and are
re-checkable at any time with `python ../scripts/verify_qc_fixes.py`:

> QC-001, 004, 005, 006, 007, 009, 013, 014, 015, 020, 021, 024, 027, 028, 029,
> 033, 034, 035, 036, 039, 043, 046, 049, 052, 054, 058, 059

**Still open, and structural.** QC-002 (four agents on four unrelated batches) and
QC-003 (Collection's revenue base ~15× Finance's) cannot be fixed by code. They are
properties of the data. This is the entire reason the dataset is being replaced.

Seven more are `MANUAL` — they need a human decision or a click, not a patch:
QC-010, 011, 016, 017, 019, 022, 045.

**Cost of the change:** every one of the 27 fixes above was verified against *old*
numbers. Section 6 says which survive the swap and which do not.

---

## 2. The new dataset in one table

One workbook, 30 sheets, one ledger. `Dataset_AI_Finance_Forum_V1.0_20260728.xlsx`.

| Group | Sheets | Rows |
|---|---|---:|
| Dimensions | `10_DIM_Legal_Entity`, `11_DIM_Store`, `12_DIM_Category`, `13_DIM_Item`, `14_DIM_Customer`, `15_DIM_Vendor` | 3 · 24 · 12 · 120 · 40 · 30 |
| Sales & cost facts | `20_FACT_Sales` | **25,592** |
| | `21_FACT_Budget` / `22_FACT_Opex` | 760 / 319 |
| Working-capital facts | `30_FACT_AR_Invoices` / `31_FACT_AP_Invoices` | 2,020 / 634 |
| Cash facts | `40_FACT_Cashflow_Lines`, `41_FACT_Cashflow_Weekly`, `42_FACT_FX_Exposure`, `43_FX_Assumptions` | 293 / 17 / 9 / 15 |
| Derived packs | `51_Finance_PL` … `57_Finance_By_Month`, `60_Collection_Worklist`, `61_Leakage_Cases` | 8 tables |
| **Acceptance** | `50_Agent_KPIs` | **26 values, each with its derivation** |
| **Control** | `90_Reconciliation` | **14 checks, all passing** |
| **Specification** | `91_Filter_Requirements` | **22 filters** |

The last three are what make this a migration rather than a data reload: the dataset
ships its own acceptance suite. Use it. Do not hand-check figures against screenshots.

**What it does not carry:** actions, recommendations, alerts, simulator lever bounds.
Those are ours to build — see §5.

---

## 3. Sequence

Order is not negotiable, and it is not the obvious one:

```
schema → filters → builders → chat → actions
```

All 47 board elements depend on the shape of the slice they are given. If the four
dashboard builders are rewritten against a fixed slice and filters are added
afterwards, **all four get rewritten twice.** Filters come first.

Agent order: **Finance → Leakage → Collection → Treasury.**
`FACT_Sales` is the spine; the other three derive from it.

---

## 4. The work

### 4.1 Schema and ingestion — blocks everything

- [ ] Create the star schema alongside the existing one. Do not drop the old schemas;
      Option C needs both alive during the transition.
- [ ] Six dimension tables with real primary keys. Today there are **no** dimension
      tables at all — vendor and customer names are repeated as text on transaction rows.
- [ ] Add `legal_entity_id` to every fact table. It is absent from all 32 current tables.
- [ ] Add `month` / `year` / `quarter` / `month_index`. Today the only discriminator is
      `import_batch_id`.
- [ ] Importer for the 29 data sheets, writing one `audit.import_batches` row for the
      whole workbook — one batch, not four.
- [ ] Port `90_Reconciliation` to a runnable check. All 14 must pass **before** any
      builder is touched. If a check fails, the dataset is broken, not the app.
- [ ] Port `50_Agent_KPIs` to a test fixture — 26 assertions with their derivations.
- [ ] Feature flag to switch an agent between old and new source.

### 4.2 Filters — 22 of them, none built

The current API exposes no filter parameter at all. `91_Filter_Requirements` and the
tracker's `05_Filter_Requirements` agree on the list; each row names its source column.

**Must have (13):**

| Filter | Applies to | Source column |
|---|---|---|
| Legal entity | all four | `legal_entity_id` |
| Period / date range | all four | `month`, `year`, `quarter` |
| Comparison basis | Finance | actual / budget / prior year |
| Store or branch | Finance, Collection | `store_id` |
| Category & category group | Finance, Leakage | `category_id`, `category_group` |
| Imported vs local | Finance, Treasury | `import_flag` |
| Customer | Collection | `customer_id` |
| Risk tier | Collection | `risk_tier` |
| Ageing bucket | Collection | `aging_bucket` |
| Vendor | Leakage | `vendor_id` |
| Leakage type | Leakage | `leakage_type` |
| Leakage status | Leakage | `leakage_status` |
| Week | Treasury | `week` |
| Commitment type | Treasury | `commitment_type` |

**Should have (6):** region/country, item/SKU (`abc_class`), channel, currency,
cash line, scenario reset.
**Nice to have (3):** segment & industry, spend category.

- [ ] Decide where filtering happens. Today [filters.js](../frontend/src/filters.js)
      filters the delivered payload client-side, which is correct for 3 products and
      wrong for 25,592 sales rows. Entity and period must move server-side; the
      narrow-a-chart behaviour can stay where it is.
- [ ] Keep the existing `dashboard.filters` declaration contract (`id`, `label`,
      `applies_to`, `column`) — it already works and the frontend already reads it.
- [ ] Keep the three display rules already solved in `filters.js`: a filtered line chart
      highlights rather than strands one dot; a filtered donut keeps the remainder as
      *Others*; a filter whose only target is a hidden panel brings that panel forward.

### 4.3 Dashboard builders — 47 elements, every figure moves

| Agent | KPIs | Charts | Tables | Side | Levers | Sparklines |
|---|---:|---:|---:|---:|---:|---:|
| Finance | 5 | 4 | 1 | 2 | 5 | 0 |
| Treasury | 5 | 3 | 1 | 2 | 4 | 1 |
| Collection | 5 | 4 | 1 | 2 | 2 | 0 |
| Leakage | 5 | 3 | 2 | 2 | 3 | 0 |

- [ ] **Finance first.** Rebuild from `51_Finance_PL`, `52_Finance_EBITDA_Bridge`,
      `53–57_Finance_By_*`. Verify against `50_Agent_KPIs` before starting Leakage.
- [ ] Adopt the mockup's EBITDA bridge definition, which settles QC-010:
      `price = −disc` (the discount actually given, from a real column) and
      `cost = gm − (bgm + vol + mix + price)` as an explicit residual.
- [ ] Leakage from `61_Leakage_Cases` and the `leakage_*` columns on `FACT_AP_Invoices`.
- [ ] Collection from `60_Collection_Worklist` and `FACT_AR_Invoices`.
- [ ] Treasury from `40_FACT_Cashflow_Lines` + `41_FACT_Cashflow_Weekly`.
- [ ] Update `infoRegistry.js` — the formulas themselves change, not just the inputs.
- [ ] Re-derive period labels from the `month` dimension. The current
      [period.py](../backend/src/llm/agents/common/tools/period.py) reverse-engineers a
      period from workbook filenames and week ranges because no row carries a date.
      That module becomes much smaller — and honest — once period is a real column.

### 4.4 Newly possible — do not skip these

Several findings were blocked by missing data rather than by difficulty. Choosing not
to migrate closes them *permanently*.

- [ ] **KPI sparklines (QC-054)** — 21 months of history instead of one. Currently 1 of
      20 KPIs has a trend line; it can be 20 of 20.
- [ ] **Prior-year comparison** — 2025 is included deliberately for year-on-year.
- [ ] **Drill-down** — 3 entities → 24 stores → 12 categories → 120 items, replacing a
      3-product hierarchy.
- [ ] **Vendor risk radar (QC-046)** — 30 vendors with `spend_category`, `payment_terms`
      and `bank_account_last_change`. Bank-change fraud is a date today, not a boolean.
- [ ] **"Why is Week 5 low" (QC-037)** — `cash_line` (7 types) + `counterparty` makes it
      answerable in one click.

### 4.5 Chat tools

- [ ] Make all four snapshot tools filter-aware. If chat reads the unfiltered ledger
      while the board shows one entity, chat and dashboard disagree on screen — which is
      QC-002 returning through a different door.

### 4.6 Actions and alerts — no source in the new dataset

The new dataset is rich in data and empty of decisions. That is the right call: an
action's impact belongs to arithmetic, not to a spreadsheet cell.

- [ ] **Simulator lever catalogue** — which levers per agent, units, bounds. This is the
      one genuinely new design task. It closes QC-016, 004, 017, 022.
- [ ] Narrow `simulate_impact` from free-form SQL to typed levers. QC-016 is not a
      measurement bug — the arithmetic is measured honestly, from the wrong query.
      The fix is the interface, not the model.
- [ ] Re-derive lever bounds (e.g. Leakage `hold` max moves from 3,800 to 6,250).
- [ ] `dso_days_released` on `60_Collection_Worklist` is already the correct
      per-customer DSO impact, and the values are disjoint per customer, so summing
      them is legitimate. That is exactly what QC-016 got wrong (5.21 days claimed
      where the arithmetic gives 10.43) and part of QC-022 for that lever.
- [ ] Alert thresholds are anchored to old figures. Re-anchor all of them.

---

## 5. Blocked — needs an answer before the work is worth starting

| # | Need | Why it blocks | Owner |
|---|---|---|---|
| 1 | **Confirmed demo date** | The dataset README puts the AR snapshot at 30 Sep 2026 and cash from 1 Oct 2026. The app and the old workbooks use August 2026. **Every Treasury figure shifts.** Also decides Option C vs Option A. | Client / PM |
| 2 | **10–15 filter combinations with expected values** | `50_Agent_KPIs` only gives the ALL totals. Without per-slice values, filter aggregation cannot be proven correct — only proven to run. | Data team |
| 3 | **Simulator lever bounds** | Only `43_FX_Assumptions` ships. Everything else is ours to define. | Us, then data team to confirm |

Item 1 is the real gate. While the event date is unconfirmed, the ability to stop
midway is worth more than the effort Option C costs over Option A.

---

## 6. What the swap does to the 27 fixes

| Survive — logic and formatting, dataset-independent | Need rework |
|---|---|
| QC-007, 009, 013, 027, 028, 029, 033, 034, 036, 039, 046 | **QC-015** — decision reversed, see below |
| QC-006, 020, 021, 035, 043, 049, 052, 054, 058, 059 | **QC-014** — `items_flagged` does not exist in the new dataset |
| The 98 backend tests stay valid as a regression net; their fixture values change | **QC-001, 024** — the tables are replaced outright |
| | **QC-004, 005** — logic survives, baselines move |

**QC-015 has to be reverted.** `90_Reconciliation` check #10 totals **9,795**, which puts
split-invoice exposure *inside* the at-risk total. On 30 July we did the opposite and
excluded it, following `is_direct_loss = false` in the old data. The new dataset decides
the other way. The dataset wins. Return QC-015 to Open in the tracker with a note that
the decision was reversed — not as a regression.

### Housekeeping for the QC workbook

- [ ] Add a column: **tested against which dataset** (`old` / `new`). Without it, Open
      and Fixed lose their meaning the moment the swap lands.
- [ ] Mark QC-002, 003, 010, 011, 035, 043, 044, 047 as **"no longer applicable —
      removed by the dataset change"**, not as *Fixed*. Different cause, different lesson.
- [ ] Freeze new findings until the new dataset is in. Finding bugs in an application
      whose data is being replaced is wasted effort.
- [ ] Replace the `07_To_Do_List` sheet with a pointer to this file, or regenerate it —
      it currently reports 58 open items, which has not been true since 30 July.

---

## 7. Demo readiness gate

From `06_Demo_Readiness_Gate`. Work top to bottom; do not start recording until the
*must clear* rows are green.

| # | Gate | Findings | Status |
|---|---|---|---|
| 1 | Leakage charts show real amounts | QC-001, 024 | Fixed on old data; recheck after swap |
| 2 | **All four agents run on one dataset** | QC-002, 003, 044 | **Open — this migration** |
| 3 | Action impact computed, not stored | QC-004, 005, 016, 017, 019 | Partly — 004/005 done, 016/017/019 need §4.6 |
| 4 | Conversation history cleaned | QC-006 | Fixed |
| 5 | "illustrative" removed from payloads | QC-039 | Fixed |
| 6 | One number per concept | QC-007, 008, 009, 011, 014 | Partly — 008, 011 open |
| 7 | Every chart states its period | QC-035 | Fixed; simplifies after swap |
| 8 | Alerts and actions deduplicated | QC-021, 023 | Partly — 023 open |
| 9 | Cross-agent handover computes | QC-047, 022 | Open |
| 10 | Filters live for entity, period, category | QC-043 | Client-side only; needs §4.2 |
| 11 | Manual checklist run twice | QC-045 | Open — demo owner |
| 12 | Cold start eliminated | MT-029 | Open — infrastructure |
| 13 | Price variance reconciled | QC-010 | Open — settled by the bridge definition in §4.3 |
| 14 | Full dry run at event resolution | MT-026, MT-031 | Open — demo owner |

Gate 2 is the migration. Gates 9, 12, 13, 14 are not.

---

## 8. What not to do

**Do not load the new data into the old schema.** It looks like the cheap route. The old
schema has no entity and no period dimension, so 25,592 sales rows must be
pre-aggregated into a single slice — discarding roughly 99% of them — QC-043 becomes
impossible because a filter has no column to stand on, and mockup v10.1 cannot be
delivered at all. It buys speed by destroying the thing that was bought.
