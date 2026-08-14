## Agent 9 - AI Explaination & Summary - Dashboard Documentation

**Source file:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Backing workbook:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Page function in code:** pgA9() -> renders via agentShell('a9', kpis, mainHTML)  
**Compute kernel:** K9(ov) over consolidated agent outputs: K1..K8 plus A9 AI Summary, Command Center Charts, Vertical Rollup, What-If Simulator, and What-If Per Agent.

Catatan penting: dashboard **tidak membaca sel Excel live**. Sama seperti A3-A8, UI menjalankan satu _shared engine_ yang mereplikasi formula workbook. Kolom "Data di workbook" menunjukkan **di mana angka yang sama tersimpan/dihitung** (A9 AI Summary, Command Center Charts, Vertical Rollup, ENGINE, ENGINE_STORE, Workforce, What-If Simulator, dll.), bukan live-link.

---

### 1. Struktur halaman (urutan render)

`agentShell('a9', ...)` menyusun:

- **Scenario banner** kalau lever What-If aktif.
- **Inbox banner** untuk executive handoff dari Agents 1-8.
- **6 KPI cards** untuk consolidated value-at-stake and operational pressure.
- **Main chart** - "Value at stake by agent" (#ch-main).
- **Custom mainHTML:**
  - "Consolidated value by vertical" (#ch-a9).
  - "Forecast by vertical" (#ch-a9b).
  - Tabel **Executive summary preview - A9 AI Summary**.
  - Tabel **Vertical rollup - all agents consolidated**.
- **Dimension charts**: agent / vertical / risk type / workforce gap / scenario delta / legal entity.
- **What-If Simulator + Compare Scenarios**.
- **Suggested Best Action** - prioritize highest-impact cross-agent action bundle.
- **Chat rail** (Ask AI / Challenge mode) with executive narrative, challenge-mode assumptions, and drill-through to A1-A8.

---

### 2. Inti perhitungan Agent 9 (K9)

```
inventoryAtRisk  = SUM(A9 AI Summary.Inventory at risk)
orderValue       = SUM(A9 AI Summary.Order value)
promoMargin      = SUM(A9 AI Summary.Promo incr margin)
markdownRecover  = SUM(A9 AI Summary.Markdown recover)
workforceGap     = SUM(A9 AI Summary.Workforce gap FTE)
salesAtRiskWF    = SUM(A9 AI Summary.Sales at risk WF)
valueAtStake     = normalized multi-agent value stack across A2-A7
priorityScore    = impact x urgency x confidence x feasibility
```

Workbook formulas behind the shared engine:

```
Inventory at risk = SUMIFS(ENGINE.At-risk, vertical)
Order value       = SUMIFS(ENGINE.Order value, vertical)
Promo incr margin = SUMIFS(ENGINE_STORE.Promo incr margin, vertical)
Markdown recover  = A5 recoverable value by vertical
Workforce gap     = SUMIFS(Workforce.Gap, vertical)
Sales at risk WF  = workforce gap x sales-risk conversion assumption
```

Command Center values use store-level gross rollups:

```
Value at stake by agent:
Inventory at risk        = SUM(ENGINE_STORE.At-risk)
Replenishment            = SUM(ENGINE_STORE.Order value)
Promotion                = SUM(ENGINE_STORE.Promo incr margin)
Markdown                 = SUM(ENGINE_STORE.At-risk value / recoverable proxy)
Assortment               = SUM(ENGINE_STORE.Contribution/day)
Workforce sales at risk  = SUM(Workforce.Gap) x 6,200,000
```

**Data di workbook:** A9 AI Summary columns A:G; Command Center Charts for cross-agent value-at-stake and forecast chart; Vertical Rollup for consolidated per-vertical agent metrics; ENGINE, ENGINE_STORE and Workforce as underlying sources; What-If Simulator and What-If Per Agent for scenario deltas.

Chain-level baseline from workbook (A9 chain-net summary):

| Metric | Baseline |
|---|---:|
| Inventory at risk | Rp 732.54B |
| Order value | Rp 581.38B |
| Promo incremental margin | Rp 21.04B |
| Markdown recover | Rp 31.19B |
| Workforce gap | 567 FTE |
| Workforce sales at risk | Rp 3.52B |
| Top inventory risk vertical | Electronics, Rp 222.86B |
| Top order value vertical | Electronics, Rp 183.45B |
| Top promo margin vertical | Omnichannel, Rp 6.59B |
| Top workforce gap vertical | Digital/Online, 146 FTE |

Chain-level Command Center values (store-level gross):

| Agent value stack | Baseline |
|---|---:|
| Inventory at risk | Rp 914.31B |
| Replenishment | Rp 643.14B |
| Promotion | Rp 21.04B |
| Markdown | Rp 114.44B |
| Assortment | Rp 64.00B |
| Workforce sales at risk | Rp 3.52B |

---

### 3. KPI Cards (6 buah)

Dihitung `K9(ov)` pada consolidated active scope.

| # | KPI | Nilai | Tipe visual | Formula (card fx) | Data di workbook |
|---:|---|---|---|---|---|
| 1 | Inventory at risk | `fmtRp(k.inventoryAtRisk)` | Sparkline **area** | `Σ ENGINE.At-risk` by active vertical | A9 AI Summary!B; ENGINE!M |
| 2 | Order value | `fmtRp(k.orderValue)` | Sparkline **bars** | `Σ ENGINE.Order value` by active vertical | A9 AI Summary!C; ENGINE!P |
| 3 | Promo incr margin | `fmtRp(k.promoMargin)` | Sparkline **area** | `Σ ENGINE_STORE.Promo incr margin` | A9 AI Summary!D; ENGINE_STORE!Z |
| 4 | Markdown recover | `fmtRp(k.markdownRecover)` | Sparkline **line** | A5 recoverable markdown value | A9 AI Summary!E; A5 Pricing & Markdown!E |
| 5 | Workforce gap | `fmt(k.workforceGap)` | Sparkline **bars** | `Σ Workforce.Gap` | A9 AI Summary!F; Workforce!N |
| 6 | Sales at risk (WF) | `fmtRp(k.salesAtRiskWF)` | Sparkline **line** | workforce gap x sales-risk assumption | A9 AI Summary!G; Command Center Charts |

---

### 4. Main Chart - "Value at stake by agent" (#ch-main)

- **Fungsi:** `mainChartCard('a9')` + branch `aid==='a9'` in `renderMain()`.
- **Tipe chart:** **Ranked horizontal bar**:
  - Inventory at risk.
  - Replenishment.
  - Markdown.
  - Assortment.
  - Promotion.
  - Workforce sales at risk.
- **Optional overlay:** confidence / action readiness marker per agent.
- **Metrics strip** (#main-stats): INVENTORY RISK, ORDER VALUE, PROMO MARGIN, WF GAP.
- **Data di workbook:** Command Center Charts section "Value at stake by agent"; A9 AI Summary for chain-net executive KPIs.

Concept formula:

```
priorityScore(agent) = valueAtStake x urgencyWeight x confidenceWeight x feasibilityWeight
bestActionBundle = top actions from A2-A8 with duplicate risk removed
```

---

### 5. Custom mainHTML (dua chart + dua tabel)

#### 5a. "Consolidated value by vertical" (#ch-a9)

- **Tipe:** **Stacked bar** by vertical.
- **Formula:** stack inventory risk, order value, promo margin, markdown recover, and workforce sales at risk by vertical.
- **Primary workbook values:** A9 AI Summary vertical rows.
- **Interpretation:** highlights which vertical is driving which type of business pressure.
- **Data di workbook:** A9 AI Summary!A:G.

Key observations:

- Electronics leads both inventory at risk and order value in the A9 chain-net summary.
- Omnichannel leads promotional incremental margin.
- Digital/Online has the highest workforce gap.

#### 5b. "Forecast by vertical" (#ch-a9b)

- **Tipe:** **Vertical bar** or **line**.
- **Formula:** `SUM(ENGINE_STORE.Forecast 7d)` by vertical.
- **Workbook values:** Grocery 442,050; Digital/Online 358,333; Health & Beauty 240,575; Omnichannel 209,338; General Merch 163,318; Fashion 130,249; Electronics 66,902; Home & Living 45,413.
- **Data di workbook:** Command Center Charts "Forecast by vertical" and Vertical Rollup!D.

#### 5c. Tabel "Executive summary preview - A9 AI Summary"

- **Tipe:** table; one row per vertical.
- **Kolom:** Vertical - Inventory at risk - Order value - Promo incr margin - Markdown recover - Workforce gap (FTE) - Sales at risk (WF) - Executive action.
- **Formula per kolom kunci:**
  - Inventory at risk = chain-net risk from ENGINE.
  - Order value = chain-net order value from ENGINE.
  - Promo incr margin = store-level promo margin from ENGINE_STORE.
  - Markdown recover = A5 recoverability value.
  - Workforce gap = Workforce gap FTE.
  - Sales at risk = Workforce gap converted to sales value.
- **Data di workbook:** A9 AI Summary columns A:G. Klik row -> `verticalScope(id)` and drill to relevant agent cards.

#### 5d. Tabel "Vertical rollup - all agents consolidated"

- **Tipe:** table; one row per legal entity / vertical ID.
- **Kolom:** Vertical - Stores - Items - Forecast 7d - Inventory value - At-risk value - Order value - Promo incr margin - Recover at-risk - Contribution/day - WF required - WF gap.
- **Formula per kolom kunci:**
  - Stores = COUNTIF(Stores.Vertical).
  - Items = COUNTIF(SKU_Master.Vertical).
  - Forecast 7d = SUMIFS(ENGINE_STORE.Forecast 7d).
  - Inventory/At-risk/Order/Promo/Recover/Contribution = store-level rollups.
  - WF required/gap = Workforce rollups.
- **Data di workbook:** Vertical Rollup columns A:L.
- **Baseline:** 160 stores, 800 items, 1.656M forecast units over 7 days, Rp 2.224T inventory value, Rp 914.31B store-level at-risk value, 3,941 required FTE, and 567 WF gap.

---

### 6. Dimension charts (6 buah) - dimRowHTML('a9') / renderDims('a9')

Measure A9: **executive value-at-stake**, selected per chart.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|---|---|---|---|---|
| #ch-dim-agent | Value at stake by agent | **Horizontal bar** | Command Center agent value stack | Command Center Charts rows 7:12 |
| #ch-dim-vertical | Consolidated value by vertical | **Stacked bar** | A9 metrics by vertical | A9 AI Summary!A:G |
| #ch-dim-forecast | Forecast by vertical | **Vertical bar** | `SUM(ENGINE_STORE!U)` by vertical | Command Center Charts forecast + Vertical Rollup!D |
| #ch-dim-wf | Workforce gap by vertical | **Vertical bar** | `SUM(Workforce!N)` by vertical | A9 AI Summary!F; A7 Workforce Optimizer |
| #ch-dim-risk | At-risk vs order by vertical | **Grouped bar** | Inventory at risk vs order value | A9 AI Summary!B:C |
| #ch-dim-scenario | Scenario delta by vertical | **Multi-line / bar** | What-If live vs baseline deltas | What-If Simulator + What-If Per Agent |

Catatan roll-up: A9 uses both **chain-net** measures (A9 AI Summary / ENGINE) and **store-level gross** measures (Command Center Charts / Vertical Rollup / ENGINE_STORE). Both are useful, but must be labelled separately to avoid false reconciliation checks.

---

### 7. Suggested Best Action - Executive action bundle (fitur khas A9)

Plan preview A9 punya tab keputusan via `summaryTab()` / `buildExecActionGroups()`:

- **5 tab:** Inventory Risk - Replenishment - Promo/Markdown - Workforce - Vendor/Brand / Assortment.
- **execClassify(row):**
  - Inventory Risk when at-risk value is high or service risk is high.
  - Replenishment when order value is high and fill rate risk exists.
  - Promo/Markdown when promo margin or recoverable value is material.
  - Workforce when FTE gap or sales-at-risk is high.
  - Vendor/Brand / Assortment when supplier concentration, at-risk exposure, or tail-share issues require portfolio action.
- **Tabel action per tab:** Vertical - Primary agent - Value at stake - KPI driver - Suggested action - Owner - Confidence - Dependency.
- **Export:** `exportExecSummary(k)` for selected tab and `exportExecAll()` for full action bundle -> CSV.
- **Submit:** Best Action -> `submitERP('execSummary')` -> sends action bundle to relevant agent workflows instead of directly posting ERP transactions.
- **Data di workbook:** A9 AI Summary + Command Center Charts + Vertical Rollup + What-If Simulator + A1-A8 sheets.

Recommended action logic:

```
if inventoryAtRisk is highest and markdownRecover is material:
  recommendation = "Prioritize A2/A5 risk recovery bundle"
elif orderValue is high and fill/stockout is weak:
  recommendation = "Prioritize A3 replenishment release"
elif promoMargin is high and funding exists:
  recommendation = "Prioritize A4 promo plan"
elif workforceGap is high:
  recommendation = "Prioritize A7 workforce coverage"
else:
  recommendation = "Monitor and drill down"
```

---

### 8. Filter mechanism

#### 8a. Filter global (top bar)

| Kontrol | id | Efek pada A9 |
|---|---|---|
| All Verticals | f-le | filters executive metrics to selected legal entity / vertical |
| All Categories | f-cat | filters underlying SKU/store metrics where source agent supports category |
| All Stores | f-store | filters store-level Command Center and Workforce-related views |
| Horizon (4/8/12/16 wk) | f-hz | affects forecast, scenario runway, and action-window narrative |
| Search | f-sku | search vertical, agent, SKU, vendor, brand, store, or executive action text |
| Refresh | - | doRefresh() |
| Scope chip | scopechip | summary and clearScope() |

#### 8b. Filter interaktif per-chart

- Klik **bar agent** -> `agentScope(aid)` and drill to A1-A8.
- Klik **bar vertical/legal entity** -> `state.le`.
- Klik **bar workforce gap** -> jump/filter to A7.
- Klik **bar risk/order** -> jump/filter to A2/A3/A5.
- Klik **row Executive summary preview** -> `verticalScope(id)`.
- Klik **row action bundle** -> dynamic drill-through to relevant agent.
- **Executive action tabs** -> `summaryTab()` changes action view, not global scope.
- **Sales View** (Daily...Yearly) -> `setPeriod()`.

#### 8c. Tooltip/reasoning

Tiap KPI, chart, and table cell displays formula (data-tt/data-fx), for example:

- `Inventory at risk = SUMIFS(ENGINE.At-risk, vertical)`.
- `Order value = SUMIFS(ENGINE.Order value, vertical)`.
- `Value at stake by agent = Command Center consolidated measure`.
- `Executive priority = impact x urgency x confidence x feasibility`.

---

### 9. What-If - bagaimana perhitungannya (A9)

#### 9a. Lever (state.sim) -> sheet Constants B16-B21

| Lever (label A9) | Range | Sel Constants | Variabel engine | Efek di Executive Summary |
|---|---:|---|---|---|
| demand (Demand uplift) | -30...+40% | B16 | ADS x (1+demand/100) | affects forecast, inventory risk, replenishment, GMV, workforce pressure |
| promo (Promo depth) | 0...50% | B17 | promo-SKU ADS uplift | affects promo margin, supplier funding, forecast, replenishment |
| md (Markdown depth) | 0...60% | B18 | markdown offset | affects markdown recovery and at-risk action priority |
| inbound (Open PO) | -40...+60% | B19 | OpenPO x (1+inbound/100) | affects position, order need, inventory risk |
| lead (Vendor lead) | -2...+6 days | B20 | ROP/Max lead | affects ROP/Max, stock state, order value |
| safety (Safety stock) | -2...+5 days | B21 | ROP safety | affects stock health, order value, risk classification |

#### 9b. Mesin hitung

- `curOv()/state.simApply`: when active, levers drive all consolidated A9 KPI cards, charts, and executive action scoring.
- A9 itself should not duplicate all agent logic manually. It should call or mirror K1...K8 measures, then normalize into a common narrative and priority model.
- Direct effects:
  - Demand lever flows through A1 forecast, A2 risk, A3 order, A8 GMV, and A7 staffing pressure.
  - Promo lever flows through A4 / A8 / A3 and may affect A7 event staffing.
  - Markdown lever flows through A5 recovery and A6 assortment actions.
  - Inbound / lead / safety levers flow through A2/A3 and can alter overall value-at-stake.

#### 9c. Panel What-If Simulator (simRowHTML + runSimA('a9'))

- **Chart:** #ch-simagent - **paired index bars** (Baseline=100 vs Scenario).
- **Metrik A9 dibandingkan** (METF.a9): Inventory at risk - Order value - Promo margin - Workforce gap.
- **Metrics strip** (#sim-metrics): TOTAL IMPACT, RISK, ORDER, PROMO, WF GAP, with delta vs baseline.
- Baseline `K9(baseOv())` vs scenario `K9(state.sim)`.

#### 9d. Compare Scenarios (#ch-compare)

- **Tipe:** **Multi-line overlay** (Baseline + <=4 saved scenarios); `saveScenario('a9')`, `exportScenarios()`.
- **Data di workbook:** What-If Simulator and What-If Per Agent. A9 uses all agent deltas and should show a ranked scenario impact by vertical and by agent.

#### 9e. Central What-If page (referensi)

Baris A9 di central scenario matrix should compare:

- **Total value at stake** (lower is better if risk/cost, higher if contribution/recovery).
- **Inventory at risk** (lower is better / inverse).
- **Order value** (contextual: required investment, not purely bad).
- **Promo margin / markdown recover** (higher is better).
- **Workforce gap** (lower is better / inverse).

---

### 10. Ringkasan pemetaan chart -> sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---|---|---|---|
| KPI Inventory at risk | Sparkline area | A9 AI Summary; ENGINE | A9!B; ENGINE!M |
| KPI Order value | Sparkline bars | A9 AI Summary; ENGINE | A9!C; ENGINE!P |
| KPI Promo incr margin | Sparkline area | A9 AI Summary; ENGINE_STORE | A9!D; ENGINE_STORE!Z |
| KPI Markdown recover | Sparkline line | A9 AI Summary; A5 Pricing & Markdown | A9!E; A5!E |
| KPI Workforce gap | Sparkline bars | A9 AI Summary; Workforce | A9!F; Workforce!N |
| KPI Sales at risk WF | Sparkline line | A9 AI Summary; Command Center Charts | A9!G; WF gap conversion |
| Main value at stake by agent | Horizontal bar | Command Center Charts | rows Inventory, Replenishment, Promotion, Markdown, Assortment, Workforce |
| Consolidated value by vertical | Stacked bar | A9 AI Summary | B:G by vertical |
| Forecast by vertical | Vertical bar | Command Center Charts; Vertical Rollup | Forecast 7d |
| Executive summary preview | Table | A9 AI Summary | vertical rows A:G |
| Vertical rollup table | Table | Vertical Rollup | stores, items, forecast, inventory, risk, order, promo, recover, contribution, workforce |
| Scenario delta chart | Multi-line / bar | What-If Simulator; What-If Per Agent | baseline/live/delta |
| Executive action tabs | Tabbed table | A9 + A1-A8 sheets | cross-agent priority and dependencies |
| Compare Scenarios | Multi-line | What-If Per Agent | saved scenario deltas |

---

### 11. Catatan kritis (bukan sekadar deskriptif)

- **A9 mixes chain-net and store-gross measures.** A9 AI Summary uses chain-net measures for some KPIs, while Command Center Charts and Vertical Rollup use store-level gross measures. The dashboard must label which basis is shown.
- **Value-at-stake is not a single additive profit number.** Inventory risk, replenishment order value, promo margin, markdown recovery, contribution/day, and workforce sales-at-risk have different meanings and directions. A9 should rank and explain them, not simply sum them.
- **Order value is investment pressure, not value lost.** Replenishment order value indicates cash/purchasing action to restore service level, so it should not be interpreted the same way as inventory at risk.
- **Promotion and markdown values point in opposite business directions.** Promo incr margin and markdown recover are opportunities, while inventory at risk and workforce sales-at-risk are risks. The executive narrative should separate risk avoided and value captured.
- **Workforce sales-at-risk uses a simple conversion.** Command Center uses `SUM(Workforce gap) x 6,200,000`, so it is a directional estimate, not a labor-optimized forecast.
- **Electronics dominates risk and replenishment pressure.** Electronics is the top A9 vertical for inventory at risk and order value, so executive prioritization should show concentration and dependencies with A2/A3/A5/A8.
- **Digital/Online is the workforce exception.** It has the highest workforce gap and sales-at-risk signal even though Electronics is the larger inventory risk driver.
- **A9 should be narrative-first but drillable.** The value is in explaining cross-agent tradeoffs and linking to the originating agent, formula, and source sheet for auditability.
- **Scenario comparisons need directionality metadata.** Some metrics are better when higher (promo margin, markdown recover), others better when lower (inventory risk, workforce gap), and some are contextual (order value, top-vendor concentration).
