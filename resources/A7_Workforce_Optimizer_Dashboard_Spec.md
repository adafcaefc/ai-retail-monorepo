## Agent 7 - Workforce Optimizer - Dashboard Documentation

**Source file:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Backing workbook:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Page function in code:** pgA7() -> renders via agentShell('a7', kpis, mainHTML)  
**Compute kernel:** K7(ov) over activeStores().map(st => workforceMetrics(st, ov)) plus event-driven demand lifts from Brand Events and productivity formulas from Stores / Verticals / Workforce.

Catatan penting: dashboard **tidak membaca sel Excel live**. Sama seperti A3/A4/A5/A6, UI menjalankan satu _shared engine_ yang mereplikasi formula workbook. Kolom "Data di workbook" menunjukkan **di mana angka yang sama tersimpan/dihitung** (A7 Workforce Optimizer, Workforce, A7 Charts, Brand Events, Stores, Verticals, Constants, dll.), bukan live-link.

---

### 1. Struktur halaman (urutan render)

`agentShell('a7', ...)` menyusun:

- **Scenario banner** kalau lever What-If aktif.
- **Inbox banner** untuk handoff dari A1 demand spike, A4 promotion/event activation, A6 assortment range expansion, and A9 executive command center.
- **6 KPI cards** untuk required roster, scheduled roster, coverage gap, and peak-shift staffing.
- **Main chart** - "Required vs scheduled FTE" (#ch-main).
- **Custom mainHTML:**
  - "Required FTE by vertical" (#ch-a7).
  - "Coverage gap by vertical" (#ch-a7b).
  - Tabel **Workforce coverage preview - per-store roster**.
- **Dimension charts**: vertical / store / cluster / channel / event / legal entity.
- **What-If Simulator + Compare Scenarios**.
- **Suggested Best Action** - add part-time positions, rebalance shifts, or redeploy surplus stores.
- **Chat rail** (Ask AI / Challenge mode).

---

### 2. Inti perhitungan Agent 7 (K7)

```
requiredFTE   = SUM(Workforce.Required)
scheduledFTE  = SUM(Workforce.Scheduled)
coverageGap   = SUM(max(0, Required - Scheduled))
coveragePct   = Scheduled / Required x 100
ptPositions   = coverageGap converted to part-time headcount or workbook PT plan count
peakShiftsWk  = PT positions x shift pattern / roster policy
surplusFTE    = SUM(max(0, Scheduled - Required))
```

Workbook formulas behind the shared engine:

```
Scheduled = ROUND(Size x WFbase x (0.99 + 0.16 x Health), 0)
Required  = MAX(1, ROUND(Size x WFbase x Peak x (1 + Event lift) x (0.80 + 0.17 x Footfall idx), 0))
Gap       = MAX(0, Required - Scheduled)
Surplus   = MAX(0, Scheduled - Required)
Coverage% = ROUND(Scheduled / Required x 100, 0)
```

**Data di workbook:** Workforce!L:P for scheduled, required, gap, surplus and coverage; A7 Workforce Optimizer for vertical rollup; A7 Charts for required/gap chart rollups; Stores for size, health, footfall, cluster and channel; Verticals for WF base and peak season; Brand Events for event lift.

Chain-level baseline from workbook:

| Metric | Baseline |
|---|---:|
| Required FTE | 3,941 |
| Scheduled FTE | 3,386 |
| Coverage gap | 567 FTE |
| Coverage % | 85.9% |
| PT positions | 1,110 |
| Peak shifts / week | 5,550 |
| Event stores | 23 |
| Stores with gap | 132 of 160 |
| Worst coverage vertical | Digital/Online, 72% |

---

### 3. KPI Cards (6 buah)

Dihitung `K7(ov)` pada scope aktif.

| # | KPI | Nilai | Tipe visual | Formula (card fx) | Data di workbook |
|---:|---|---|---|---|---|
| 1 | Required FTE | `fmt(k.requiredFTE)` | Sparkline **bars** | `Σ Required` | A7 Workforce Optimizer!B; Workforce!M |
| 2 | Scheduled FTE | `fmt(k.scheduledFTE)` | Sparkline **bars** | `Σ Scheduled` | A7 Workforce Optimizer!C; Workforce!L |
| 3 | Coverage gap | `fmt(k.coverageGap)` | Sparkline **area** | `Σ max(0, Required - Scheduled)` | A7 Workforce Optimizer!D; Workforce!N |
| 4 | Coverage % | `k.coveragePct%` | Sparkline **line** | `Scheduled / Required x 100` | A7 Workforce Optimizer!E; Workforce!P |
| 5 | PT positions | `fmt(k.ptPositions)` | Sparkline **bars** | part-time positions required to cover gap | A7 Workforce Optimizer!F; Constants part-time settings |
| 6 | Peak shifts/wk | `fmt(k.peakShiftsWk)` | Sparkline **line** | planned peak shifts per week | A7 Workforce Optimizer!G; Constants peak shift h |

---

### 4. Main Chart - "Required vs scheduled FTE" (#ch-main)

- **Fungsi:** `mainChartCard('a7')` + branch `aid==='a7'` in `renderMain()`.
- **Tipe chart:** **Grouped bar / variance chart**:
  - _Required FTE_ as demand-driven staffing need.
  - _Scheduled FTE_ as current roster.
  - _Coverage gap_ as red variance marker or bar.
- **Split** at baseline vs scenario if demand/promo/event staffing levers are active.
- **Metrics strip** (#main-stats): REQUIRED FTE, SCHEDULED FTE, GAP, COVERAGE.
- **Data di workbook:** A7 Workforce Optimizer!B:E, A7 Charts section 1 and 3, Workforce!L:P.

Concept formula:

```
coverageGap = max(0, Required - Scheduled)
coveragePct = Scheduled / Required
PT plan = convert gap into part-time positions and peak shifts
```

---

### 5. Custom mainHTML (dua chart + tabel)

#### 5a. "Required FTE by vertical" (#ch-a7)

- **Tipe:** **Vertical bar** with value labels.
- **Formula:** `SUM(Workforce!M)` by vertical.
- **Workbook values:** Grocery 678, General Merch 586, Digital/Online 530, Omnichannel 521, Fashion 475, Health & Beauty 455, Electronics 402, Home & Living 294.
- **Data di workbook:** A7 Charts section "1 - Required FTE by vertical"; A7 Workforce Optimizer!B; Workforce!M.

#### 5b. "Coverage gap by vertical" (#ch-a7b)

- **Tipe:** **Horizontal bar** sorted desc.
- **Formula:** `SUM(Workforce!N)` by vertical.
- **Workbook values:** Digital/Online 146, Omnichannel 98, General Merch 87, Fashion 72, Electronics 72, Grocery 53, Home & Living 28, Health & Beauty 11.
- **Data di workbook:** A7 Charts section "3 - Coverage gap by vertical"; A7 Workforce Optimizer!D; Workforce!N.

#### 5c. Tabel "Workforce coverage preview - per-store roster"

- **Tipe:** tabel scroll; all stores, sorted by Gap desc and event lift desc.
- **Kolom:** Store - Vertical - Store name - Cluster - Channel - Event - Event lift - Scheduled - Required - Gap - Surplus - Coverage % - Action.
- **Formula per kolom kunci:**
  - Scheduled = Size x WF base x health-adjusted roster factor.
  - Required = Size x WF base x peak season x event lift x footfall factor.
  - Gap = Required - Scheduled floor at zero.
  - Surplus = Scheduled - Required floor at zero.
  - Coverage % = Scheduled / Required.
- **Data di workbook:** Workforce columns A:P + Stores cluster/channel + Brand Events event lift. Klik baris -> `storeScope(id)`.
- **Largest store gaps:** S018 Grocery 18 Manado gap 16; S137 Online 17 Pekanbaru gap 16; S039 Department Store 19 Bogor gap 15; S025 Department Store 05 Medan gap 13; S046 Fashion 06 Semarang gap 13.

---

### 6. Dimension charts (6 buah) - dimRowHTML('a7') / renderDims('a7')

Measure A7: **Required FTE** or **Coverage gap FTE**, depending on chart title.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|---|---|---|---|---|
| #ch-dim-le | Required FTE by vertical | **Vertical bar** (+labels) | `SUM(Workforce!M)` by vertical | A7 Charts section 1; Workforce!B/M |
| #ch-dim-store | Coverage gap by store | **Horizontal bar** | `SUM(Workforce!N)` by store | Workforce!A/N/P |
| #ch-dim-clu | Required FTE by cluster | **Vertical bar** | `SUM(Workforce!M)` by cluster | A7 Charts section 2; Workforce!D/M |
| #ch-dim-channel | Gap by channel | **Horizontal bar** | `SUM(Workforce!N)` by channel | Workforce + Stores channel mapping |
| #ch-dim-event | Gap by event | **Vertical bar** | `SUM(Gap)` by Event/Event lift | Workforce!H/N; Brand Events |
| #ch-dim-cov | Coverage % by vertical | **Line or bar** | `Scheduled / Required` | A7 Workforce Optimizer!E; Workforce!L:M |

Catatan roll-up: Required FTE and Coverage gap tie out to A7 Workforce Optimizer if the same scope is used. Event charts only include stores with Brand Events or event labels, so they do not represent the full chain unless a "No event" bucket is included.

---

### 7. Suggested Best Action - Workforce optimization plan (fitur khas A7)

Plan preview A7 punya tab keputusan via `workforceTab()` / `buildWorkforceGroups()`:

- **4 tab:** Add PT Cover - Redeploy Surplus - Event Staffing - Schedule Rebalance.
- **workforceClassify(st):**
  - Add PT Cover when store gap is positive and coverage below target.
  - Redeploy Surplus when store surplus is positive and nearby stores have gaps.
  - Event Staffing when Event lift > 0 and required FTE exceeds scheduled roster.
  - Schedule Rebalance when coverage gap can be solved by shift movement rather than hiring.
- **Tabel action per tab:** Store - Cluster - Channel - Event - Scheduled - Required - Gap - Surplus - Coverage - Recommendation.
- **Export:** `exportWorkforceTab(k)` for selected tab and `exportWorkforceAll()` for full roster plan -> CSV.
- **Submit:** Best Action -> `submitERP('workforce')` -> workflow SoA approval and roster scheduling update.
- **Data di workbook:** A7 Workforce Optimizer + Workforce + Brand Events + Stores + Verticals + Constants full-time/part-time parameters.

Recommended action logic:

```
if Gap > 0 and Event lift > 0:
  recommendation = "Add event PT shifts"
elif Gap > 0 and Coverage < target:
  recommendation = "Add PT cover or rebalance schedule"
elif Surplus > 0:
  recommendation = "Redeploy surplus hours"
else:
  recommendation = "Hold roster"
```

---

### 8. Filter mechanism

#### 8a. Filter global (top bar)

| Kontrol | id | Efek pada A7 |
|---|---|---|
| All Verticals | f-le | activeStores() per vertical; rebuild store, cluster, channel and event charts |
| All Categories | f-cat | limited effect; can filter demand-driven staffing context if SKU/category demand is mapped |
| All Stores | f-store | filter store-level roster and coverage preview |
| Horizon (4/8/12/16 wk) | f-hz | affects peak shift schedule horizon and event planning window |
| Search | f-sku | for A7, search store name, store ID, cluster, channel, or event |
| Refresh | - | doRefresh() |
| Scope chip | scopechip | ringkasan + clearScope() |

#### 8b. Filter interaktif per-chart

- Klik **bar vertical/legal entity** -> `state.le`.
- Klik **bar store** -> `state.store`.
- Klik **bar cluster/channel** -> cluster/channel scope.
- Klik **bar event** -> event scope.
- Klik **baris Workforce coverage preview** -> `storeScope(id)`.
- **Workforce action tabs** -> `workforceTab()` changes action view, not global scope.
- **Sales View** (Daily...Yearly) -> `setPeriod()`.

#### 8c. Tooltip/reasoning

Tiap KPI, chart, and table cell displays formula (data-tt/data-fx), for example:

- `Scheduled = Size x WFbase x (0.99 + 0.16 x Health)`.
- `Required = Size x WFbase x Peak x (1 + Event lift) x (0.80 + 0.17 x Footfall idx)`.
- `Gap = MAX(0, Required - Scheduled)`.
- `Coverage % = Scheduled / Required`.

---

### 9. What-If - bagaimana perhitungannya (A7)

#### 9a. Lever (state.sim) -> sheet Constants B16-B21 and Workforce constants

| Lever (label A7) | Range | Sel Constants | Variabel engine | Efek di Workforce |
|---|---:|---|---|---|
| demand (Demand uplift) | -30...+40% | B16 | ADS / traffic demand context | can raise required FTE in demand-sensitive scopes |
| promo (Promo depth) | 0...50% | B17 | promo/event demand uplift | raises event staffing requirement where promo active |
| md (Markdown depth) | 0...60% | B18 | clearance/event activity | may raise staffing in markdown-heavy stores |
| inbound (Open PO) | -40...+60% | B19 | replenishment workload context | can add receiving/picking pressure in stores or hubs |
| lead (Vendor lead) | -2...+6 days | B20 | replenishment timing | may shift staffing timing around receiving windows |
| safety (Safety stock) | -2...+5 days | B21 | stock policy | may change workload for replenishment and shelf fill |
| full-time h/wk | static | B8 | roster capacity | converts FTE to hours |
| part-time h/wk | static | B9 | PT capacity | converts gap to part-time positions |
| peak shift h | static | B11 | shift length | converts PT plan to peak shifts |

#### 9b. Mesin hitung

- `curOv()/state.simApply`: when active, levers drive A7 KPI cards, charts, and roster action table scoring.
- Direct effects:
  - Event lift raises Required FTE through `(1 + Event lift)`.
  - Demand/promo levers can be used as stress multipliers for traffic and peak windows.
  - Part-time and peak-shift constants convert FTE gaps into execution plans.
  - Schedule rebalance reduces gap where surplus stores exist in the same cluster or nearby channel.

#### 9c. Panel What-If Simulator (simRowHTML + runSimA('a7'))

- **Chart:** #ch-simagent - **paired index bars** (Baseline=100 vs Scenario).
- **Metrik A7 dibandingkan** (METF.a7): Required FTE - Coverage gap - Coverage % - PT positions.
- **Metrics strip** (#sim-metrics): REQUIRED, GAP, COVERAGE, PT POSITIONS, PEAK SHIFTS, with delta vs baseline.
- Baseline `K7(baseOv())` vs scenario `K7(state.sim)`.

#### 9d. Compare Scenarios (#ch-compare)

- **Tipe:** **Multi-line overlay** (Baseline + <=4 saved scenarios); `saveScenario('a7')`, `exportScenarios()`.
- **Data di workbook:** What-If Simulator and What-If Per Agent. A7 uses Workforce, Brand Events, Stores, Verticals and Constants roster assumptions.

#### 9e. Central What-If page (referensi)

Baris A7 di central scenario matrix should compare:

- **Coverage gap** (lower is better / inverse).
- **Coverage %** (higher is better).
- **PT positions** (contextual: required capacity, but cost pressure).
- **Peak shifts/wk** (contextual workload and execution load).

---

### 10. Ringkasan pemetaan chart -> sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---|---|---|---|
| KPI Required FTE | Sparkline bars | A7 Workforce Optimizer; Workforce | Workforce!M |
| KPI Scheduled FTE | Sparkline bars | A7 Workforce Optimizer; Workforce | Workforce!L |
| KPI Coverage gap | Sparkline area | A7 Workforce Optimizer; Workforce | Workforce!N |
| KPI Coverage % | Sparkline line | A7 Workforce Optimizer; Workforce | Workforce!P |
| KPI PT positions | Sparkline bars | A7 Workforce Optimizer; Constants | PT plan count; part-time h/wk |
| KPI Peak shifts/wk | Sparkline line | A7 Workforce Optimizer; Constants | peak shift h, planned shifts |
| Main required vs scheduled | Grouped bar / variance | A7 Workforce Optimizer + Workforce | Required, Scheduled, Gap |
| Required FTE by vertical | Vertical bar | A7 Charts | section 1; Workforce!M by vertical |
| Coverage gap by vertical | Horizontal bar | A7 Charts | section 3; Workforce!N by vertical |
| Workforce coverage preview | Table | Workforce + Stores + Brand Events | Store, Event, Scheduled, Required, Gap, Coverage |
| Required FTE by cluster | Vertical bar | A7 Charts | section 2; Workforce!M by cluster |
| Coverage gap by store | Horizontal bar | Workforce | Workforce!N/P by store |
| Gap by event | Vertical bar | Workforce + Brand Events | Event lift and store gap |
| By legal entity | Vertical bar | A7 Workforce Optimizer + Verticals | vertical roll-up |
| Workforce action tabs | Tabbed table | Workforce + Brand Events + Stores | Add PT / Redeploy / Event Staffing / Rebalance |
| What-If Simulator | Paired index bars | Constants + What-If Simulator | B16-B21 and roster constants |
| Compare Scenarios | Multi-line | What-If Per Agent | saved scenario deltas |

---

### 11. Catatan kritis (bukan sekadar deskriptif)

- **A7 is store-level, not SKU-level.** The primary grain is store workforce coverage. SKU/category filters are only meaningful if demand or event context is mapped to staffing.
- **Coverage gap totals are additive, coverage % is ratio-based.** Chain coverage should be computed as total Scheduled divided by total Required, not averaged by store or vertical.
- **23 stores have event-driven staffing pressure.** Event lift materially affects Required FTE through the `(1 + Event lift)` multiplier, so event stores should be highlighted separately.
- **PT positions and peak shifts are execution outputs, not pure FTE.** The workbook stores PT positions and peak shifts by vertical, but the true conversion depends on Constants such as part-time hours and peak shift hours.
- **Digital/Online is the largest staffing risk.** It has the highest gap at 146 FTE and the lowest vertical coverage at 72%, so central prioritization should not use required FTE alone.
- **Surplus should be visible.** The Workforce sheet has a Surplus column; without showing surplus stores, the optimizer may over-hire instead of redeploying existing capacity.
- **Event labels are operational assumptions.** Brand Events drives staffing but does not represent a full labor scheduling calendar. A production version should include dates, shift times, employee availability, skills, and labor rules.
- **Required FTE formula is simplified.** It uses size, WF base, peak season, event lift and footfall. It does not yet model hourly demand curves, task standards, labor law constraints, or employee preferences.
