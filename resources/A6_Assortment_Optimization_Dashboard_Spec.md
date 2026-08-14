## Agent 6 - Assortment Optimization - Dashboard Documentation

**Source file:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Backing workbook:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Page function in code:** pgA6() -> renders via agentShell('a6', kpis, mainHTML)  
**Compute kernel:** K6(ov) over activeSKUs().map(s => assortmentMetrics(s, ov)) plus store-level contribution rollups from ENGINE_STORE and SKU-level attributes from SKU_Master / ENGINE.

Catatan penting: dashboard **tidak membaca sel Excel live**. Sama seperti A3/A4/A5, UI menjalankan satu _shared engine_ yang mereplikasi formula workbook. Kolom "Data di workbook" menunjukkan **di mana angka yang sama tersimpan/dihitung** (A6 Assortment, A6 Charts, ENGINE, ENGINE_STORE, SKU_Master, Categories, Stores, Constants, dll.), bukan live-link.

---

### 1. Struktur halaman (urutan render)

`agentShell('a6', ...)` menyusun:

- **Scenario banner** kalau lever What-If aktif.
- **Inbox banner** untuk handoff dari A2 Inventory Risk, A3 Replenishment, A5 Pricing & Markdown, dan A8 Vendor & Brand.
- **6 KPI cards** untuk assortment health dan optimization value.
- **Main chart** - "Delist vs grow opportunity" (#ch-main).
- **Custom mainHTML:**
  - "Contribution/day by vertical" (#ch-a6).
  - "Contribution/day by channel" (#ch-a6b).
  - Tabel **Assortment action preview - Delist / Grow Candidates**.
- **Dimension charts**: kategori / toko / cluster / channel / inventory state / legal entity.
- **What-If Simulator + Compare Scenarios**.
- **Suggested Best Action** - delist tail SKUs, grow winners, rebalance range, or handoff to replenishment/markdown.
- **Chat rail** (Ask AI / Challenge mode).

---

### 2. Inti perhitungan Agent 6 (K6)

```
delistCandidates = SKUs flagged by low productivity, excess inventory, low GMROI, slow movement, or tail share
growCandidates   = SKUs with strong contribution/day, healthy state, high GMROI, growth potential
avgGMROI         = weighted average gross margin return on inventory
capitalFreed     = inventory capital released by delist/tail rationalization
contributionDay  = SUM(ENGINE_STORE.Contribution/day)
tailSharePct     = share of assortment or value in low-productivity tail
```

Workbook formulas behind the shared engine:

```
Contribution/day = ADS x Price x Margin %
Weekly GMV       = ADS x 7 x Price
Margin (Rp)      = Weekly GMV x Margin %
Funding (Rp)     = Weekly GMV x Fund %
Inventory value  = Position x Price
GMROI proxy      = Margin (Rp) / Inventory value
```

Assortment classification concept:

```
Delist = low GMROI or tail SKU or state in {Slow-mover, Overstock, Expiry}
Grow   = Healthy SKU with strong contribution/day, margin, growth, GMROI, and vendor/brand support
Hold   = neither delist nor grow but operationally acceptable
```

**Data di workbook:** Delist/Grow candidates, Avg GMROI, Tail share, Capital freed and Contribution/day in **A6 Assortment**; store-level Contribution/day in ENGINE_STORE!AB; SKU-level margin, funding, Weekly GMV, vendor, brand in ENGINE!S:U/Q:R; SKU attributes in SKU_Master.

Chain-level baseline from workbook:

| Metric | Baseline |
|---|---:|
| Delist candidates | 106 SKUs |
| Grow candidates | 64 SKUs |
| Weighted avg GMROI | 5.29x |
| Avg tail share | 47.13% |
| Capital freed | Rp 330.48B |
| Contribution/day | Rp 64.00B/day |
| Highest capital freed vertical | Electronics, Rp 170.20B |

---

### 3. KPI Cards (6 buah)

Dihitung `K6(ov)` pada scope aktif.

| # | KPI | Nilai | Tipe visual | Formula (card fx) | Data di workbook |
|---:|---|---|---|---|---|
| 1 | Delist candidates | `k.delist.length` | Sparkline **bars** | count SKUs meeting delist/tail conditions | A6 Assortment!B; ENGINE state/value; SKU_Master growth |
| 2 | Grow candidates | `k.grow.length` | Sparkline **bars** | count SKUs meeting grow/winner conditions | A6 Assortment!C; ENGINE margin/contribution; SKU_Master growth |
| 3 | Avg GMROI | `k.avgGMROI x` | Sparkline **line** | weighted GMROI by inventory or candidate value | A6 Assortment!D; ENGINE Margin / Inventory value |
| 4 | Tail share % | `k.tailShare%` | Sparkline **line** | low productivity tail share of range/value | A6 Assortment!E |
| 5 | Capital freed | `fmtRp(k.capitalFreed)` | Sparkline **area** | inventory value released by delist/range cleanup | A6 Assortment!F; ENGINE inventory value |
| 6 | Contribution/day | `fmtRp(k.contribDay)` | Sparkline **area** | `Σ ADS x Price x Margin %` | A6 Assortment!G; ENGINE_STORE!AB |

---

### 4. Main Chart - "Delist vs grow opportunity" (#ch-main)

- **Fungsi:** `mainChartCard('a6')` + branch `aid==='a6'` in `renderMain()`.
- **Tipe chart:** **Quadrant / bubble scatter**:
  - X-axis = GMROI or contribution/day index.
  - Y-axis = growth / demand signal.
  - Bubble size = inventory value or capital locked.
  - Color = Recommended action: Grow, Hold, Delist, Markdown.
- **Alternative fallback:** paired bars comparing Delist candidates, Grow candidates, Capital freed, Contribution/day by vertical.
- **Split** at baseline vs scenario if demand/promo/markdown levers are active.
- **Metrics strip** (#main-stats): DELIST, GROW, GMROI, CAPITAL FREED.
- **Data di workbook:** A6 Assortment!B:F, ENGINE!L/S/T, ENGINE_STORE!AB, SKU_Master growth/elasticity/brand/vendor.

Concept formula:

```
GMROI = Margin (Rp) / Inventory value
Contribution/day = ADS x Price x Margin %
Capital lock = Position x Price
Action = classify(GMROI, contribution, growth, state, tail share)
```

---

### 5. Custom mainHTML (dua chart + tabel)

#### 5a. "Contribution/day by vertical" (#ch-a6)

- **Tipe:** **Vertical bar** with value labels.
- **Formula:** `SUM(ENGINE_STORE!AB)` by vertical.
- **Workbook values:** Omnichannel Rp 21.38B/day, Electronics Rp 17.48B/day, Home & Living Rp 8.06B/day, Digital/Online Rp 7.60B/day, Fashion Rp 4.53B/day, General Merch Rp 3.49B/day, Health & Beauty Rp 1.15B/day, Grocery Rp 0.31B/day.
- **Data di workbook:** A6 Charts section "1 - By vertical"; ENGINE_STORE!AB by vertical.

#### 5b. "Contribution/day by channel" (#ch-a6b)

- **Tipe:** **Horizontal bar** sorted desc.
- **Formula:** `SUM(ENGINE_STORE!AB)` by `ENGINE_STORE.Channel`.
- **Workbook values:** Physical Rp 20.50B/day, Online Rp 14.69B/day, Click & Collect Rp 7.20B/day, Marketplace Rp 7.27B/day, Omni Rp 5.90B/day, Mobile App Rp 4.48B/day, Call Center Rp 2.88B/day, Fulfillment Hub Rp 1.09B/day.
- **Data di workbook:** A6 Charts section "3 - By channel"; ENGINE_STORE!AB/AE.

#### 5c. Tabel "Assortment action preview - Delist / Grow Candidates"

- **Tipe:** tabel scroll; action candidates sorted by capital freed for delist and contribution/day or margin for grow.
- **Kolom:** SKU - Category - Vendor - Brand - State - GMROI - Contribution/day - Inventory value - Weekly GMV - Margin (Rp) - Funding (Rp) - Action - Reason.
- **Formula per kolom kunci:**
  - GMROI = Margin (Rp) / Inventory value.
  - Contribution/day = ADS x Price x Margin %.
  - Capital freed = inventory value released when delisting or reducing range width.
  - Action = Delist / Grow / Hold / Markdown based on scorecard.
- **Data di workbook:** ENGINE!A:U, ENGINE_STORE!AB, SKU_Master growth, elasticity, vendor, brand, category.
- **Candidate examples:** Delist proxy examples include ELC-091, OMN-075, ELC-075, OMN-054 based on slow-mover state and high inventory lock. Grow proxy examples include OMN-031, OMN-097, OMN-053, OMN-093 based on healthy state and high margin productivity.

---

### 6. Dimension charts (6 buah) - dimRowHTML('a6') / renderDims('a6')

Measure A6: **Contribution/day, Rp** unless noted.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|---|---|---|---|---|
| #ch-dim-cat | Contribution/day by category | **Vertical bar** (klik -> filter) | `SUM(ENGINE_STORE!AB)` by category | ENGINE_STORE!D/AB + Categories |
| #ch-dim-store | Contribution/day by store | **Horizontal bar** | `SUM(ENGINE_STORE!AB)` by store | ENGINE_STORE!B/AB + Stores |
| #ch-dim-clu | Contribution/day by cluster | **Vertical bar** + labels | `SUM(ENGINE_STORE!AB)` by cluster | A6 Charts section "2 - By store cluster"; ENGINE_STORE!AD/AB |
| #ch-dim-channel | Contribution/day by channel | **Horizontal bar** | `SUM(ENGINE_STORE!AB)` by channel | A6 Charts section "3 - By channel"; ENGINE_STORE!AE/AB |
| #ch-dim-state | Inventory value by state | **Vertical bar** | inventory value by State | A6 Charts section "4 - By inventory state"; ENGINE_STORE!Q/S |
| #ch-dim-le | By legal entity | **Vertical bar** + labels | roll-up store -> LE -> chain | A6 Assortment; Verticals + ENGINE_STORE |

Catatan roll-up: Contribution/day charts tie to store-level contribution from ENGINE_STORE!AB. Delist/Grow candidates and capital freed are assortment decision metrics from A6 Assortment and may not tie directly to contribution/day charts.

---

### 7. Suggested Best Action - Assortment optimization plan (fitur khas A6)

Plan preview A6 punya tab keputusan via `assortmentTab()` / `buildAssortmentGroups()`:

- **4 tab:** Delist Tail - Grow Winners - Rebalance Space - Vendor/Brand Review.
- **assortmentClassify(s):**
  - Delist Tail if low GMROI, low contribution/day, slow movement, overstock, or high capital lock.
  - Grow Winners if healthy, high contribution/day, high GMROI, positive growth, and good vendor/brand signal.
  - Rebalance Space if category has high tail share or uneven contribution density.
  - Vendor/Brand Review if many actions cluster under a single vendor or brand.
- **Tabel action per tab:** SKU - Category - Vendor - Brand - State - Contribution/day - GMROI - Capital freed - Growth - Recommendation.
- **Export:** `exportAssortmentTab(k)` for selected tab and `exportAssortmentAll()` for full assortment plan -> CSV.
- **Submit:** Best Action -> `submitERP('assortment')` -> workflow SoA approval, category manager review, and D365 item/category status update.
- **Data di workbook:** A6 Assortment + A6 Charts + ENGINE + ENGINE_STORE + SKU_Master + Vendor/Brand fields.

Recommended action logic:

```
if low GMROI and slow/overstock state:
  recommendation = "Delist / reduce facing / stop reorder"
elif healthy and high contribution/day and high GMROI:
  recommendation = "Grow range / add space / expand stores"
elif high tail share by category:
  recommendation = "Rationalize tail and rebalance category"
elif weak vendor or brand cluster:
  recommendation = "Vendor or brand review"
else:
  recommendation = "Hold assortment"
```

---

### 8. Filter mechanism

#### 8a. Filter global (top bar)

| Kontrol | id | Efek pada A6 |
|---|---|---|
| All Verticals | f-le | activeSKUs()/activeStores() per vertical; rebuild category, store, cluster, channel and action tables |
| All Categories | f-cat | filter SKU/category and candidate scoring |
| All Stores | f-store | filter store-level contribution and local assortment productivity |
| Horizon (4/8/12/16 wk) | f-hz | affects contribution run-rate, range-growth horizon, and capital release scenario |
| Search | f-sku | filter SKU, item name, vendor, brand, or category text |
| Refresh | - | doRefresh() |
| Scope chip | scopechip | ringkasan + clearScope() |

#### 8b. Filter interaktif per-chart

- Klik **bar vertical/legal entity** -> `state.le`.
- Klik **bar kategori** -> `state.cat`.
- Klik **bar toko** -> `state.store`.
- Klik **bar cluster/channel** -> cluster/channel scope.
- Klik **bar inventory state** -> `state.invState`.
- Klik **baris Assortment action preview** -> `skuScope(id)`.
- **Assortment action tabs** -> `assortmentTab()` changes action view, not global scope.
- **Sales View** (Daily...Yearly) -> `setPeriod()`.

#### 8c. Tooltip/reasoning

Tiap KPI, chart, and table cell displays formula (data-tt/data-fx), for example:

- `Contribution/day = ADS x Price x Margin %`.
- `GMROI = Margin (Rp) / Inventory value`.
- `Capital freed = inventory value released by delist/reduce action`.
- `Tail share = low productivity range share`.

---

### 9. What-If - bagaimana perhitungannya (A6)

#### 9a. Lever (state.sim) -> sheet Constants B16-B21

| Lever (label A6) | Range | Sel Constants | Variabel engine | Efek di Assortment |
|---|---:|---|---|---|
| demand (Demand uplift) | -30...+40% | B16 | ADS x (1+demand/100) | changes contribution/day, GMROI, and grow/delist scoring |
| promo (Promo depth) | 0...50% | B17 | promo-SKU ADS uplift | may move promo SKUs from tail to grow/hold |
| md (Markdown depth) | 0...60% | B18 | markdown offset | can reduce capital lock before delist and affect A5 handoff |
| inbound (Open PO) | -40...+60% | B19 | OpenPO x (1+inbound/100) | changes inventory value and capital lock |
| lead (Vendor lead) | -2...+6 days | B20 | ROP/Max lead | changes stocking thresholds and excess/low state |
| safety (Safety stock) | -2...+5 days | B21 | ROP safety | changes stock state and range-risk classification |

#### 9b. Mesin hitung

- `curOv()/state.simApply`: when active, levers drive A6 KPI cards, charts, and candidate table scoring.
- Direct effects:
  - Demand lever raises ADS and contribution/day.
  - Promo lever can lift selected promo SKUs and lower tail share.
  - Markdown lever may reduce apparent excess/risk before pure delist.
  - Inbound lever increases position and capital locked, potentially raising delist or reduce-facing candidates.
  - Lead/safety levers change ROP/Max and inventory state.

#### 9c. Panel What-If Simulator (simRowHTML + runSimA('a6'))

- **Chart:** #ch-simagent - **paired index bars** (Baseline=100 vs Scenario).
- **Metrik A6 dibandingkan** (METF.a6): Delist candidates - Grow candidates - Avg GMROI - Capital freed.
- **Metrics strip** (#sim-metrics): DELIST, GROW, GMROI, CAPITAL FREED, CONTRIBUTION/DAY, with delta vs baseline.
- Baseline `K6(baseOv())` vs scenario `K6(state.sim)`.

#### 9d. Compare Scenarios (#ch-compare)

- **Tipe:** **Multi-line overlay** (Baseline + <=4 saved scenarios); `saveScenario('a6')`, `exportScenarios()`.
- **Data di workbook:** What-If Simulator and What-If Per Agent. A6 uses the same Constants levers and ENGINE/ENGINE_STORE productivity logic.

#### 9e. Central What-If page (referensi)

Baris A6 di central scenario matrix should compare:

- **Capital freed** (higher is better, if service/range guardrails remain intact).
- **Contribution/day** (higher is better).
- **Avg GMROI** (higher is better).
- **Tail share** (lower is better / inverse).

---

### 10. Ringkasan pemetaan chart -> sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---|---|---|---|
| KPI Delist candidates | Sparkline bars | A6 Assortment; ENGINE; SKU_Master | Delist/tail scoring, State, Growth, GMROI |
| KPI Grow candidates | Sparkline bars | A6 Assortment; ENGINE; SKU_Master | Grow scoring, Healthy state, high contribution |
| KPI Avg GMROI | Sparkline line | A6 Assortment; ENGINE | Margin (Rp) / Inv value |
| KPI Tail share % | Sparkline line | A6 Assortment | Tail share % |
| KPI Capital freed | Sparkline area | A6 Assortment; ENGINE | Inventory value freed |
| KPI Contribution/day | Sparkline area | A6 Assortment; ENGINE_STORE | ENGINE_STORE!AB |
| Main delist vs grow | Quadrant/bubble | A6 Assortment + ENGINE + SKU_Master | GMROI, growth, capital lock, contribution/day |
| Contribution/day by vertical | Vertical bar | A6 Charts | section 1; ENGINE_STORE!AB by vertical |
| Contribution/day by channel | Horizontal bar | A6 Charts | section 3; ENGINE_STORE!AB by channel |
| Assortment action preview | Table | ENGINE + SKU_Master | SKU, State, GMROI, Margin, Vendor, Brand |
| Contribution/day by category | Vertical bar | ENGINE_STORE + Categories | Cat, Contribution/day |
| Contribution/day by store | Horizontal bar | ENGINE_STORE + Stores | Store, Contribution/day |
| Contribution/day by cluster | Vertical bar | A6 Charts | section 2; Cluster |
| Inventory value by state | Vertical bar | A6 Charts | section 4; State inventory value |
| By legal entity | Vertical bar | A6 Assortment + Verticals | vertical roll-up |
| Assortment action tabs | Tabbed table | A6 Assortment + ENGINE + SKU_Master | Delist Tail / Grow Winners / Rebalance / Vendor Brand |
| What-If Simulator | Paired index bars | Constants + What-If Simulator | B16-B21 levers |
| Compare Scenarios | Multi-line | What-If Per Agent | saved scenario deltas |

---

### 11. Catatan kritis (bukan sekadar deskriptif)

- **A6 is contribution-led, not only inventory-risk-led.** A6 Charts use Contribution/day from ENGINE_STORE!AB, while A5 uses at-risk value. Do not read A6 as a markdown dashboard.
- **Capital freed is a decision value, not a cash receipt.** The workbook shows Rp 330.48B potential capital freed, but real release depends on selling down, markdown execution, returns, transfers, or delist timing.
- **Delist candidates and grow candidates are vertical-level outputs.** A6 Assortment stores counts by vertical, while line-level candidate explanation must be reconstructed from ENGINE/SKU_Master scoring.
- **GMROI is a proxy.** It is best interpreted as margin return on inventory using workbook margin and inventory value. Real GMROI should include time period, average inventory, and cost accounting rules.
- **Tail share is not fully decomposed by SKU in the workbook.** The dashboard should display the vertical KPI and use candidate tables to explain which SKUs make up the tail.
- **Store-gross and chain-level views may differ.** Contribution charts use store-level ENGINE_STORE rollups. Capital freed and candidate counts are vertical rollups in A6 Assortment.
- **A6 requires handoff governance.** Delisting a SKU can affect A3 replenishment, A4 promotions, A5 markdown, and A8 vendor/brand commitments, so Best Action should require category manager and vendor review before activation.
- **Electronics dominates capital freed.** Electronics contributes Rp 170.20B of potential freed capital, so executive views should show concentration risk and avoid treating all verticals equally.
