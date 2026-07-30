# Replacing the Dataset — Options and Trade-offs

**Status:** decision material. No code has been written for this.
**Date:** 30 July 2026
**Question:** should the schema and dataset be replaced wholesale, incrementally, or not at all?

---

## 1. The five references

| # | Source | Location | Role |
|---|---|---|---|
| 1 | Old workbooks (03A–03D) | `exisitingdb/` | the dataset **currently** in use |
| 2 | Existing database | Azure PostgreSQL | what those workbooks were imported into |
| 3 | Tech Priorities | `AI_Finance_Forum_Technical_Priorities_Bilingual_2026-07-29.xlsx..xlsx` | 62 QC findings, 15 failing formula checks |
| 4 | Mockup v10.1 | `03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html` | the **latest business requirement** |
| 5 | New dataset | `Dataset_AI_Finance_Forum_V1.0_20260728.xlsx` | the proposed replacement |

### 1.1 Old workbooks — `exisitingdb/`

Four files, authored separately, one per agent.

| File | Sheets | Fills | Batch |
|---|---|---|---|
| `03A_Financial Performance…xlsx` | 10 | `financial_performance.*` | 19 |
| `03B_Cash Flow…xlsx` | 12 | `cashflow.*` | 2 |
| `03C_Collections Credit…xlsx` | 9 | `collections.*` | 11 |
| `03D_Payment Leakage Fraud…xlsx` | 9 | `payment_leakage.*` | 17 |

Company: **PT Future Manufacturing Tbk**, named explicitly in 03A and 03B. Every storyline sheet states *"Same company as the other agents"* — cross-agent consistency was the intent, it was simply never enforced.

**The structural problem is period, not company.** Each workbook covers a different span, and no figure states its own:

| Workbook | Period | Evidence in the file |
|---|---|---|
| 03A | one month (August 2026) | sheet title `02 P&L Actual vs Budget (Aug…)` |
| 03B | 13 weeks forward | `Horizon (weeks) = 13` |
| 03C | one year | `Annual credit sales = 700,000` |
| 03D | two weeks (sample) | `Sample period (weeks) = 2` |

QC-003 reports *"Collection is about 15 times Finance"*. That compares a **monthly** figure (46,510) against an **annual** one (700,000). The real gap is 1.25×, not 15×. It is still wrong — credit sales cannot exceed total sales — but the root cause is an unstated period, not two different companies. The same root cause produces QC-035 (*"No chart states its period"*).

### 1.2 Existing database

| Schema | Tables | Columns |
|---|---:|---:|
| `financial_performance` | 11 | 124 |
| `collections` | 7 | 103 |
| `cashflow` | 7 | 103 |
| `payment_leakage` | 7 | 98 |
| **Subtotal in scope** | **32** | **428** |
| `chat` | 4 | 26 |
| `audit` | 1 | 13 |

Dependent code: **11 Python files, 59 referencing lines**.

There is no **entity** dimension and no **period** dimension. The only discriminator is `import_batch_id`, and the four agents sit on four unrelated batches.

### 1.3 Tech Priorities

62 findings · 34 High · 39 demo blockers · 15 failing formula checks. Target dates 31 Jul – 13 Aug 2026.

As of 30 July, 15 findings are fixed on branch `bug-fix-trial` (commits `53daa2c`, `f448e66`).

### 1.4 Mockup v10.1 — the latest requirement

The company changes: **the Nusantara group**, three legal entities.

```
ID01  PT Nusantara Manufaktur Indonesia
SG01  Nusantara Trading Pte Ltd
MY01  Nusantara Malaysia Sdn Bhd
```

Its internal data block (`var DS`) holds 752 rows across 12 months (Oct 2025 – Sep 2026) and 5 segments, with an Entity × Period × Segment filter engine.

Its EBITDA bridge also settles QC-010, which had been open pending a definition:

```js
price = -disc                            // price effect is the discount given,
                                         // taken from a real column
cost  = gm - (bgm + vol + mix + price)   // explicit residual
```

### 1.5 New dataset — `Dataset_AI_Finance_Forum_V1.0`

A star schema: 29 sheets, roughly 30,000 fact rows.

| Group | Sheets | Rows |
|---|---|---:|
| Dimensions | `10_DIM_Legal_Entity` … `15_DIM_Vendor` | 6 tables |
| Facts | `20_FACT_Sales` | **25,592** |
| | `30_FACT_AR_Invoices` | 2,020 |
| | `31_FACT_AP_Invoices` | 634 |
| | `21_FACT_Budget` / `22_FACT_Opex` | 760 / 319 |
| | `40–42_FACT_Cashflow*`, `FX_Exposure` | 293 / 17 / 9 |
| Derived | `51–57_Finance_*`, `60`, `61` | 8 tables |
| **Control** | **`90_Reconciliation`** | **14 checks, all passing** |
| **Acceptance** | **`50_Agent_KPIs`** | **26 values with derivations** |
| **Specification** | **`91_Filter_Requirements`** | **22 filters** |

Those last three sheets are what set this dataset apart: **it ships its own means of validation.**

> `90_Reconciliation`: *"Every check below recalculates from the fact tables. If a check fails, the dataset is broken, not the app."*

Its README names our bug as the reason it exists:

> *"Collection assumes annual credit sales of IDR 700,000 mn while Finance reports revenue of IDR 46,510 mn. This dataset replaces all four batches with one ledger."*

---

## 2. How the figures change

| Metric | Current | New dataset |
|---|---|---|
| Revenue | 46,510 (one month) | **614,632** (12 months) |
| EBITDA % | 9.2% | **8.7%** (budget 15.5%) |
| AR | 110,000 | **104,961** |
| DSO | 57.4 days | **62.3 days** |
| Cash freed at target | 19,863 | **25,816** |
| Leakage at risk | 7,845 | **9,795** |
| Lowest weekly cash | 6,997.5 (W5) | **5,788.9**, two weeks below buffer |
| Recommended hedge | 2,000,000 USD | **1,800,000 USD** (60% policy) |

**Practically every figure cited in the 62 QC findings moves.**

---

## 3. Options

### Option A — Replace everything now

Build the new star schema, point all four agents at one ledger, add filters end to end.

**For**
- Closes **eight findings structurally**: QC-002, 003, 010, 011, 035, 043, 044, 047. Not patched — the conditions that caused them stop existing.
- `90_Reconciliation` proves the data is coherent before any code is touched.
- `50_Agent_KPIs` is a ready-made acceptance suite: 26 values, each with its derivation.
- Matches mockup v10.1, the current requirement.
- One ledger, so a CFO's cross-agent question no longer falls apart.

**Against**
- 32 tables and 11 Python files rewritten.
- **All 62 QC findings need retesting** — their reference values all change.
- Two of the 15 fixes made on 30 July conflict (see §5).
- The new dataset carries no action or alert data, so 47 action cards lose their source.
- The event date is unconfirmed. If it is mid-August, this is a high-risk path.

**Effort:** large. Every block is touched — schema and ingestion, filters, the four builders, chat tools, actions.

---

### Option B — Keep the old schema, load the new data into it

**For**
- Minimal code change, quickest route to something running.

**Against**
- **It defeats its own purpose.** The old schema has no entity or period dimension, so:
  - QC-043 (filters) becomes **impossible** — there is nowhere for a filter to attach.
  - QC-044 (volume) fails — 30,000 rows must be pre-aggregated into a single slice, discarding roughly 99% of them.
  - Mockup v10.1 cannot be delivered at all.
- Creates a new reconciliation problem: data that was internally consistent is forced into a shape that cannot express it.

**Effort:** small — but it buys something that does not solve the problem.
**Assessment: not recommended.**

---

### Option C — Migrate one agent at a time *(recommended)*

Build the new star schema alongside the old one. Move agents across individually behind a feature flag. The old schema stays live until the last agent moves.

Order: **Finance → Leakage → Collection → Treasury**
(Finance first because `FACT_Sales` is the spine; the other three derive from it.)

**For**
- The demo is **never fully broken**. If time runs out, stop after any agent and the rest still works.
- Each agent is verified against `50_Agent_KPIs` before the next one starts.
- QC findings are retested per agent instead of all 62 at once.
- Can be abandoned cheaply if the event date turns out to be tight.

**Against**
- Two data paths alive at the same time, temporarily.
- Needs a feature flag and the discipline to remove it afterwards.
- Slightly more total work than Option A — there is a bridging cost.
- During the transition, figures can differ between agents. This **must** be signposted in the UI.

**Effort:** large, but divided and interruptible. That is the difference from Option A.

---

### Option D — Do not migrate; fix bugs on the old data

**For**
- Lowest risk. Today's demo keeps working.
- Effort stays focused on the 34 High findings.

**Against**
- QC-002, 003, 043, 044, 035 and 047 stay open **permanently**. All are demo blockers.
- Mockup v10.1 cannot be delivered.
- The dataset the data team has already built goes unused.
- QC-010 and QC-011 stay unresolved for want of a definition.

**Effort:** small.
**When it makes sense:** if the event is under two weeks away and mockup v10.1 is not a commitment to the client.

---

## 4. Options at a glance

| | A · Replace | B · Old schema | C · Incremental | D · Don't migrate |
|---|---|---|---|---|
| Closes QC-002/003/043/044 | Yes | No | Yes | No |
| Can deliver mockup v10.1 | Yes | No | Yes | No |
| Demo safe during the work | No | Partly | Yes | Yes |
| Can be stopped midway | No | — | Yes | — |
| Effort | Large | Small | Large, divided | Small |
| Risk to the event date | High | Medium | **Contained** | Low |

---

## 5. Two conflicts to settle

**QC-015 — the 30 July fix has to be reverted.**
`90_Reconciliation` check #10 reads *"Fixes the current bug where split-invoice exposure…"* and totals **9,795**, which puts split-invoice exposure **inside** the at-risk total. On 30 July we did the opposite and excluded it, following `is_direct_loss = false` in the old data. The new dataset decides the other way, and the dataset wins.

**QC-004 / QC-005 — already addressed in the data.**
Check #13 reads *"Fixes the current bug where headroom…"*.

### Which of the 30 July fixes survive

| Survive (logic and formatting, dataset-independent) | Need review |
|---|---|
| QC-007, 009, 013, 027, 028, 029, 033, 034, 036, 039, 046 | **QC-015** — the decision is reversed |
| The 62 tests remain valid as a safety net | **QC-014** — `items_flagged` does not exist in the new dataset |
| | **QC-001, 024** — the tables are replaced outright |

---

## 6. What is still needed

| # | Need | Why | From |
|---|---|---|---|
| 1 | **Simulator lever catalogue** — which levers per agent, units, bounds | Actions must be **computed**, not written. Closes QC-016/004/017/022 | our team |
| 2 | **10–15 filter combinations with their correct values** | `50_Agent_KPIs` only gives the ALL totals. Without per-slice values, filter aggregation cannot be proven correct | data team |
| 3 | **Confirmed demo date** | The dataset README says AR snapshot 30 Sep 2026 and cash from 1 Oct 2026. The app and the old workbooks use August 2026. This shifts every Treasury figure | client / PM |
| 4 | **Simulator lever bounds** | The new dataset only carries `43_FX_Assumptions` | data team |

**On actions:** the new dataset has no action, recommendation or alert sheet. This is not a blocker — an LLM can write the action narrative. What it must not write is **the numbers**. The correct architecture already exists (`simulate_impact` in `monitoring_tools.py`), but the model currently supplies **free-form SQL**, and that is where QC-016 comes from: the arithmetic is measured honestly, from the wrong query. The fix is to narrow the interface to typed levers, not to change the model.

---

## 7. Recommendation

**Option C — incremental migration**, once need #3 (the demo date) is answered.

Not because it is the cheapest; it is not. Because it is the only option that **can be stopped midway without breaking the demo**. While the event date is unconfirmed, that property is worth more than the difference in effort.

If the event turns out to be four or more weeks away, Option A is cleaner: no bridging cost, no two data paths.

**What not to do:** Option B. It looks economical, but it discards 99% of the new data and still cannot deliver mockup v10.1.

---

## 8. Feature impact

Replacing the dataset is not only a change of numbers. This is the surface affected, measured from the payloads running today:

| Agent | KPIs | Charts | Tables | Side | Levers | Sparklines |
|---|---:|---:|---:|---:|---:|---:|
| Finance | 5 | 4 | 1 | 2 | 5 | 0 |
| Treasury | 5 | 3 | 1 | 2 | 4 | 1 |
| Collection | 5 | 4 | 1 | 2 | 2 | 0 |
| Leakage | 5 | 3 | 2 | 2 | 3 | 0 |
| **Total** | **20** | **14** | **5** | **8** | **14** | **1** |

**47 board elements display numbers.** Every one of them changes.

### 8.1 Must be updated, or it breaks

| Feature | Why | Size |
|---|---|---|
| 47 board elements | every reference figure changes | Large |
| 14 simulator levers | baselines and bounds move (e.g. `hold` max goes from fraud 3,800 to 6,250) | Medium |
| Formula panel (`infoRegistry.js`) | the formulas themselves change — `price = −disc` | Medium |
| 4 chat snapshot tools | must become filter-aware, or chat disagrees with the dashboard again | Medium |
| Alerts | thresholds are anchored to the old figures | Medium |
| 62 tests | fixture values all change | Small, but required |

### 8.2 Newly possible — the part that is easy to miss

Several QC findings were blocked by missing data rather than by difficulty:

| Feature | QC | Why it was impossible | Why it is possible now |
|---|---|---|---|
| **KPI sparklines** | QC-054 | one month of data — no line to draw | 21 months. Currently 1 of 20 KPIs has one; it could be 20 of 20 |
| **Filters** | QC-043 | no entity or period dimension to attach to | 22 filters, each with its source column |
| **Period labels** | QC-035 | no period to state | period is a dimension |
| **Prior-year comparison** | — | only August 2026 existed | 2025 is included **deliberately** for year-on-year |
| **Drill-down** | — | 3 products | 3 entities → 24 stores → 12 categories → 120 items |
| **Vendor risk radar** | QC-046 | few vendors | 30 vendors with `spend_category` and `payment_terms` |

This matters for the decision: choosing Option D closes QC-054, QC-043 and QC-035 **permanently**, not temporarily. There is no way to build them on one month of data.

### 8.3 Loses its source

| Feature | State |
|---|---|
| 47 action cards | the new dataset has **no** action or recommendation sheet |
| Alerts | same |
| Simulator lever bounds | only `43_FX_Assumptions` exists |

These we prepare ourselves rather than request — see the note on actions in §6.

### 8.4 Consequence for sequencing

Because all 47 elements depend on the shape of the data, **filters must be built before the dashboards are rewritten, not after.** If the four builders are rewritten against a fixed slice and filters are added later, all four get rewritten twice.

Correct order: `schema → filters → builders → chat → actions`.

---

## 9. What the new dataset adds

### 9.1 Dimensions that do not exist today

| Dimension | Current | New |
|---|---|---|
| **`legal_entity_id`** | **absent from all 32 tables** | present on nearly every fact table |
| **`month` / `year` / `quarter`** | absent — only `import_batch_id` | 21 months, plus `month_index` for ordering |
| **`store_id`** | absent | 24 stores |
| **`item_id`** | `product_name` only (3 products) | 120 SKUs |
| **`category_id` / `category_group`** | absent | 12 categories in 5 groups |
| **`channel`** | absent | Retail · Wholesale · B2B Contract · E-commerce |
| **`import_flag`** | a global 55% assumption | per item |

Six of these seven have **nowhere to live** in the current schema. That is the technical reason QC-043 could never be built: a filter had no column to stand on.

### 9.2 Six master tables that never existed

Today there are no dimension tables at all — vendor and customer names are repeated as text on transaction rows.

| New master | Notable columns |
|---|---|
| `DIM_Legal_Entity` | `fx_to_idr`, `tax_regime`, `share` |
| `DIM_Store` | `region`, `store_format`, `size_band`, `monthly_target_idr_mn` |
| `DIM_Category` | `benchmark_gm_pct` — a margin benchmark per category |
| `DIM_Item` | `std_cost`, `list_price`, `target_gm_pct`, `abc_class` |
| `DIM_Customer` | `credit_rating`, `expected_recovery_pct`, `on_time_payment_pct` |
| `DIM_Vendor` | `vendor_master_status`, **`bank_account_last_change`**, `three_way_match_required` |

`bank_account_last_change` directly supports bank-change fraud detection, which today is only a boolean flag.

### 9.3 A jump from aggregates to transactions

| | Current | New | Factor |
|---|---:|---:|---|
| Sales | 3 product rows | **25,592** transactions | ~8,500× |
| AR | 12 aggregated customers | **2,020** invoices | invoice level |
| AP | ~30 transactions | **634** invoices | 21× |
| Cashflow | weekly only | **293 lines** + 17 weekly | line detail |

This changes what the application is: from displaying prepared figures to **tracing a figure back to the transaction it came from**.

### 9.4 Columns that unlock features directly

| New column | Unlocks |
|---|---|
| `cash_line` (7 types) + `counterparty` | **QC-037** — *"why is Week 5 low"* answerable in one click |
| `commitment_type` (Committed / Deferrable / Forecast) | the Treasury defer lever becomes data-driven |
| `days_past_due` + `aging_bucket` per invoice | ageing is computed, not stored as a result |
| `expected_settlement_date` | when the cash actually lands |
| **`dso_days_released`** | **the DSO impact per customer, already computed correctly** |
| `three_way_match_gap_idr_mn` per invoice | overbilling visible per invoice, not as a total |
| `leakage_type` + `leakage_status` | Blocked / Recoverable / Lost become columns, not derivations |
| `abc_class`, `benchmark_gm_pct` | ABC analysis and category benchmarking |

**On `dso_days_released` —** this is worth calling out. It is `expected_recovery_idr_mn / daily_credit_sales`, verified against the sheet:

```
Kallang   3,808.78 / 1,683.92 = 2.262   sheet 2.26
Cahaya    1,403.07 / 1,683.92 = 0.833   sheet 0.83
Surya     1,146.93 / 1,683.92 = 0.681   sheet 0.68
```

That is exactly the calculation QC-016 got wrong (the card claimed 5.21 days where the arithmetic gives 10.43). The new dataset ships the per-customer collection impact already computed, which reduces the work behind need #1 in §6 for the Collection agent. The values are also disjoint per customer, so summing them is legitimate — which handles part of QC-022 for this lever.

### 9.5 What is lost

| Lost | Currently holds | Consequence |
|---|---|---|
| **`*.recommendations`** (4 tables) | `expected_impact`, `action_title`, `approval_route` | 47 action cards lose their source |
| **`simulator_levers`** plus 2 simulator tables | `financial_performance.*` | slider bounds disappear |
| **`*.assumptions`** (4 tables) | per-agent assumptions | partly replaced by `43_FX_Assumptions` |
| `collections.risk_scores` | a computed risk score | components survive (`on_time_payment_pct`, `days_past_due`, `credit_rating`); the score must be recomputed |
| `payment_leakage.anomaly_detections` | per-transaction detection | superseded by the `leakage_*` columns on `FACT_AP_Invoices` |
| `cashflow.fx_scenarios` | hedge scenarios | `43_FX_Assumptions` may suffice; needs checking |

### 9.6 The shape of the change

Added: 6 dimensions, 6 master tables, transaction-level granularity, and roughly 15 columns that unlock features.
Removed: actions, simulator bounds, and per-agent assumptions.

The pattern is that the new dataset is **rich in data and empty of decisions**. It supplies far better raw material but says nothing about which action to propose — which is appropriate, because an action's impact should be computed from the data rather than typed into a spreadsheet.

---

## 10. Notes for the QC workbook

Once the dataset changes, most of the 62 findings **cannot be retested as written** — the thing they described no longer exists. QC-014 is the clearest case: the new dataset has neither `items_flagged` nor 22 anomalies. That finding is not passing and not failing; it **no longer applies**.

Suggested handling:

1. Add a column: **"tested against which dataset"** (`old` / `new`). Without it, Open and Fixed lose their meaning.
2. Mark the eight findings listed under Option A as **"no longer applicable — removed by the dataset change"**, not as *Fixed*. Different cause, different lesson.
3. **Return QC-015 to Open**, noting that the decision was reversed.
4. Freeze new findings until the new dataset is in place. Finding bugs in an application whose data is being replaced is wasted effort.
