## Agent 5 - Pricing & Markdown - Dashboard Documentation

**Source file:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Backing workbook:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Page function in code:** pgA5() -> renders via agentShell('a5', kpis, mainHTML)  
**Compute kernel:** K5(ov) over activeSKUs().map(s => pricingMarkdownMetrics(s, ov)) plus chain-net rollups from ENGINE and store-level chart rollups from ENGINE_STORE.

Catatan penting: dashboard **tidak membaca sel Excel live**. Sama seperti A3/A4, UI menjalankan satu _shared engine_ yang mereplikasi formula workbook. Kolom "Data di workbook" menunjukkan **di mana angka yang sama tersimpan/dihitung** (ENGINE, ENGINE_STORE, A5 Pricing & Markdown, A5 Charts, SKU_Master, Constants, dll.), bukan live-link.

---

### 1. Struktur halaman (urutan render)

`agentShell('a5', ...)` menyusun:

- **Scenario banner** kalau lever What-If aktif.
- **Inbox banner** untuk handoff dari A2 Inventory Risk, A3 Replenishment, dan A4 Promotion.
- **6 KPI cards** untuk pricing and markdown effectiveness.
- **Main chart** - "At-risk value vs recoverable markdown" (#ch-main).
- **Custom mainHTML:**
  - "At-risk value by vertical" (#ch-a5).
  - "At-risk value by channel" (#ch-a5b).
  - Tabel **Markdown candidate preview - Pricing & Markdown**.
- **Dimension charts**: kategori / toko / cluster / channel / state / legal entity.
- **What-If Simulator + Compare Scenarios**.
- **Suggested Best Action** - approve markdown, suppress reorder, or trigger promo/clearance action.
- **Chat rail** (Ask AI / Challenge mode).

---

### 2. Inti perhitungan Agent 5 (K5)

```
markdownCandidates = SKUs where State in {Expiry, Overstock, Slow-mover}
avgDepthPct        = weighted average markdown depth by candidate value
atRiskValue        = SUM(ENGINE.At-risk) for markdown candidate states
recoverable        = estimated value saved after markdown action
writeOff           = atRiskValue - recoverable
compIdx            = average competitive index for active scope
recoveryRate       = recoverable / atRiskValue
```

Workbook formulas behind the shared engine:

```
State = IF(Position < ROP * 0.6, "Stockout",
        IF(Position < ROP, "Low",
        IF(Perishable="Y" and DoS > ExpiryDays, "Expiry",
        IF(Perishable="N" and DoS > 15, "Overstock",
        IF(Growth < 1 and DoS > 10, "Slow-mover", "Healthy")))))

At-risk value = IF(State <> "Healthy", Position x Price, 0)

Recover at-risk =
  Expiry:    max(0, Position - ADS x shelf-life) x Price
  Over/Slow: if max(0, Position - Max) > 0,
             (Position - Max) x Price,
             Position x 30% x Price
```

**Data di workbook:** State ENGINE!J / ENGINE_STORE!Q, Position ENGINE!F / ENGINE_STORE!M, Price ENGINE!K / ENGINE_STORE!R, At-risk ENGINE!M / ENGINE_STORE!T, Recover at-risk formula in Formulas sheet, store-level At-risk value ENGINE_STORE!AA, A5 chain-net rollup in **A5 Pricing & Markdown**, chart rollups in **A5 Charts**.

Chain-level baseline from workbook:

| Metric | Baseline |
|---|---:|
| Markdown candidates | 99 SKUs |
| Weighted avg depth | 28.40% |
| At-risk state value | Rp 52.02B |
| Recoverable | Rp 31.19B |
| Write-off | Rp 20.84B |
| Recovery rate | 59.95% |
| Highest risk vertical | Electronics, Rp 15.69B |

---

### 3. KPI Cards (6 buah)

Dihitung `K5(ov)` pada scope aktif.

| # | KPI | Nilai | Tipe visual | Formula (card fx) | Data di workbook |
|---:|---|---|---|---|---|
| 1 | Markdown candidates | `k.candidates.length` | Sparkline **bars** | `count(State in {Expiry, Overstock, Slow-mover})` | A5 Pricing & Markdown!B; ENGINE!J |
| 2 | Avg depth % | `k.avgDepth%` | Sparkline **line** | weighted markdown depth by candidate value | A5 Pricing & Markdown!C; Constants!B18 |
| 3 | At-risk value | `fmtRp(k.atRisk)` | Sparkline **area** | `Σ At-risk value where candidate state` | A5 Pricing & Markdown!D; ENGINE!M |
| 4 | Recoverable | `fmtRp(k.recoverable)` | Sparkline **area** | recover-at-risk rule by state | A5 Pricing & Markdown!E; Formulas sheet |
| 5 | Write-off | `fmtRp(k.writeOff)` | Sparkline **line** | `At-risk value - Recoverable` | A5 Pricing & Markdown!F |
| 6 | Comp idx | `k.compIdx` | Sparkline **line** | average competitive price index | A5 Pricing & Markdown!G; SKU_Master!R |

---

### 4. Main Chart - "At-risk value vs recoverable markdown" (#ch-main)

- **Fungsi:** `mainChartCard('a5')` + branch `aid==='a5'` in `renderMain()`.
- **Tipe chart:** **Combo chart**:
  - _At-risk value_ as red bars.
  - _Recoverable value_ as green bars or overlay line.
  - _Write-off residual_ as gray/orange residual marker.
- **Split** at baseline vs scenario if markdown lever is active.
- **Metrics strip** (#main-stats): CANDIDATES, AVG DEPTH, AT-RISK, RECOVERABLE.
- **Data di workbook:** A5 Pricing & Markdown!B:F; ENGINE!J/M; ENGINE_STORE!AA; A5 Charts.

Concept formula:

```
gap = At-risk value - Recoverable
markdown depth = scenario md lever or baseline depth by vertical
recovery rate = Recoverable / At-risk value
best action = markdown if recovery is high and cannib/reorder risks are controlled
```

---

### 5. Custom mainHTML (dua chart + tabel)

#### 5a. "At-risk value by vertical" (#ch-a5)

- **Tipe:** **Vertical bar** with value labels.
- **Formula:** store-level `SUM(ENGINE_STORE!AA)` by vertical.
- **Workbook values:** Electronics Rp 48.22B, Omnichannel Rp 24.91B, Digital/Online Rp 12.63B, Fashion Rp 12.36B, Home & Living Rp 9.99B, General Merch Rp 5.08B, Health & Beauty Rp 0.89B, Grocery Rp 0.36B.
- **Data di workbook:** A5 Charts section "1 - By vertical"; ENGINE_STORE!AA by vertical.
- **Note:** This chart is **store-level gross**, while headline A5 value is chain-net from A5 Pricing & Markdown / ENGINE.

#### 5b. "At-risk value by channel" (#ch-a5b)

- **Tipe:** **Horizontal bar** sorted desc.
- **Formula:** `SUM(ENGINE_STORE!AA)` by `ENGINE_STORE.Channel`.
- **Workbook values:** Physical Rp 47.42B, Online Rp 24.64B, Omni Rp 12.89B, Click & Collect Rp 12.44B, Marketplace Rp 9.13B, Call Center Rp 5.83B, Mobile App Rp 1.52B, Fulfillment Hub Rp 0.58B.
- **Data di workbook:** A5 Charts section "3 - By channel"; ENGINE_STORE!AA/AE.

#### 5c. Tabel "Markdown candidate preview - Pricing & Markdown"

- **Tipe:** tabel scroll; all candidate SKUs where State is Expiry, Overstock, or Slow-mover, sorted by at-risk value desc.
- **Kolom:** SKU - Category - State - Position - DoS - Price - At-risk value - Recommended depth - Recoverable - Write-off - Vendor - Brand - Reason.
- **Formula per kolom kunci:**
  - Reason = Expiry if perishable DoS exceeds shelf-life; Overstock if non-perishable DoS > 15; Slow-mover if growth < 1 and DoS > 10.
  - At-risk value = Position x Price when state is not Healthy.
  - Recoverable = state-specific recover-at-risk rule.
  - Write-off = At-risk - Recoverable.
- **Data di workbook:** ENGINE rows 6:805 for SKU, Cat, State, Position, DoS, Price, Inv value/At-risk, Vendor, Brand; SKU_Master for category, perishable, growth, shelf-life.
- **Top candidate examples:** ELC-091 Slow-mover Rp 19.28B, OMN-075 Slow-mover Rp 15.22B, ELC-075 Slow-mover Rp 14.76B, OMN-054 Slow-mover Rp 13.84B.

---

### 6. Dimension charts (6 buah) - dimRowHTML('a5') / renderDims('a5')

Measure A5: **At-risk value, Rp** unless noted.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|---|---|---|---|---|
| #ch-dim-cat | At-risk value by category | **Vertical bar** (klik -> filter) | `SUM(ENGINE_STORE!AA)` by category | ENGINE_STORE!D/AA + Categories |
| #ch-dim-store | At-risk value by store | **Horizontal bar** | `SUM(ENGINE_STORE!AA)` by store | ENGINE_STORE!B/AA + Stores |
| #ch-dim-clu | At-risk value by cluster | **Vertical bar** + labels | `SUM(ENGINE_STORE!AA)` by cluster | A5 Charts section "2 - By store cluster"; ENGINE_STORE!AD/AA |
| #ch-dim-channel | At-risk value by channel | **Horizontal bar** | `SUM(ENGINE_STORE!AA)` by channel | A5 Charts section "3 - By channel"; ENGINE_STORE!AE/AA |
| #ch-dim-state | Inventory value by state | **Vertical bar** | inventory value by State | A5 Charts section "4 - By inventory state"; ENGINE_STORE!Q/S |
| #ch-dim-le | By legal entity | **Vertical bar** + labels | roll-up store -> LE -> chain | A5 Pricing & Markdown; Verticals + ENGINE_STORE |

Catatan roll-up: vertical, store, cluster, and channel charts use **store-level gross at-risk value** from ENGINE_STORE!AA. Headline A5 KPI uses **chain-net markdown candidate value** from A5 Pricing & Markdown / ENGINE, so a difference between chart totals and KPI totals is expected.

---

### 7. Suggested Best Action - Markdown approval and price action (fitur khas A5)

Plan preview A5 punya tab keputusan via `markdownTab()` / `buildMarkdownGroups()`:

- **4 tab:** Expiry Markdown - Overstock Clearance - Slow-mover Price Cut - Suppress Reorder.
- **markdownClassify(s):**
  - Expiry if perishable and DoS > shelf-life.
  - Overstock if non-perishable and DoS > 15.
  - Slow-mover if growth < 1 and DoS > 10.
  - Suppress Reorder if item is simultaneously reorder-eligible but markdown state indicates excess risk.
- **Tabel action per tab:** SKU - Category - State - DoS - Position - Price - Depth - Recoverable - Write-off - A3 reorder flag - Action.
- **Export:** `exportMarkdownTab(k)` for selected tab and `exportMarkdownAll()` for full markdown list -> CSV.
- **Submit:** Best Action -> `submitERP('markdown')` -> workflow SoA approval and price/discount activation.
- **Data di workbook:** A5 Pricing & Markdown + ENGINE + ENGINE_STORE + SKU_Master + pricing/discount constructs from Promotion & Discount Detail where paired with campaign action.

Recommended action logic:

```
if State == "Expiry":
  recommendation = "Immediate markdown / short expiry clearance"
elif State == "Overstock":
  recommendation = "Clearance markdown and block replenishment"
elif State == "Slow-mover":
  recommendation = "Price cut or targeted promo"
elif State in {"Stockout", "Low"}:
  recommendation = "Do not markdown; handoff to A3 replenishment"
else:
  recommendation = "Hold price"
```

---

### 8. Filter mechanism

#### 8a. Filter global (top bar)

| Kontrol | id | Efek pada A5 |
|---|---|---|
| All Verticals | f-le | activeSKUs()/activeStores() per vertical; rebuild category, state, channel, store charts |
| All Categories | f-cat | filter SKU/category markdown candidates |
| All Stores | f-store | filter store-level at-risk charts |
| Horizon (4/8/12/16 wk) | f-hz | affects markdown window and recoverable horizon |
| Search | f-sku | filter SKU, item name, vendor, brand, or category text |
| Refresh | - | doRefresh() |
| Scope chip | scopechip | ringkasan + clearScope() |

#### 8b. Filter interaktif per-chart

- Klik **bar vertical/legal entity** -> `state.le`.
- Klik **bar kategori** -> `state.cat`.
- Klik **bar toko** -> `state.store`.
- Klik **bar cluster/channel** -> cluster/channel scope.
- Klik **bar inventory state** -> `state.invState`.
- Klik **baris Markdown candidate preview** -> `skuScope(id)`.
- **Markdown action tabs** -> `markdownTab()` changes action view, not global scope.
- **Sales View** (Daily...Yearly) -> `setPeriod()`.

#### 8c. Tooltip/reasoning

Tiap KPI, chart, and table cell displays formula (data-tt/data-fx), for example:

- `At-risk value = Position x Price where State <> Healthy`.
- `Recoverable = state-specific markdown recovery rule`.
- `Write-off = At-risk value - Recoverable`.
- `Depth = markdown lever or baseline depth by vertical`.

---

### 9. What-If - bagaimana perhitungannya (A5)

#### 9a. Lever (state.sim) -> sheet Constants B16-B21

| Lever (label A5) | Range | Sel Constants | Variabel engine | Efek di Pricing & Markdown |
|---|---:|---|---|---|
| demand (Demand uplift) | -30...+40% | B16 | ADS x (1+demand/100) | changes DoS, state, and overstock/slow-mover risk |
| promo (Promo depth) | 0...50% | B17 | promo-SKU ADS uplift | can reduce slow-moving stock through promo uplift |
| md (Markdown depth) | 0...60% | B18 | markdown offset | raises markdown recovery assumption but lowers net price |
| inbound (Open PO) | -40...+60% | B19 | OpenPO x (1+inbound/100) | can increase position and overstock risk |
| lead (Vendor lead) | -2...+6 days | B20 | ROP/Max lead | changes stock state thresholds through ROP/Max |
| safety (Safety stock) | -2...+5 days | B21 | ROP safety | changes Low/Healthy versus excess classification |

#### 9b. Mesin hitung

- `curOv()/state.simApply`: when active, levers drive A5 KPI cards, charts, and markdown table scoring.
- Direct effects:
  - Demand lever raises ADS and typically reduces DoS.
  - Markdown lever raises depth and recovery but may increase write-off if margin erosion exceeds recovery.
  - Inbound lever increases Position and can increase Overstock risk.
  - Lead/safety levers change ROP/Max and therefore the recovery formula for excess above Max.

#### 9c. Panel What-If Simulator (simRowHTML + runSimA('a5'))

- **Chart:** #ch-simagent - **paired index bars** (Baseline=100 vs Scenario).
- **Metrik A5 dibandingkan** (METF.a5): Markdown candidates - At-risk value - Recoverable - Write-off.
- **Metrics strip** (#sim-metrics): AT-RISK, RECOVERABLE, WRITE-OFF, RECOVERY RATE, with delta vs baseline.
- Baseline `K5(baseOv())` vs scenario `K5(state.sim)`.

#### 9d. Compare Scenarios (#ch-compare)

- **Tipe:** **Multi-line overlay** (Baseline + <=4 saved scenarios); `saveScenario('a5')`, `exportScenarios()`.
- **Data di workbook:** What-If Simulator and What-If Per Agent. A5 uses the same Constants levers and ENGINE/ENGINE_STORE state logic.

#### 9e. Central What-If page (referensi)

Baris A5 di central scenario matrix should compare:

- **Recoverable** (higher is better).
- **Write-off** (lower is better / inverse).
- **At-risk value** (lower is better / inverse).
- **Recovery rate** (higher is better).

---

### 10. Ringkasan pemetaan chart -> sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---|---|---|---|
| KPI Markdown candidates | Sparkline bars | A5 Pricing & Markdown; ENGINE | State in Expiry/Overstock/Slow-mover |
| KPI Avg depth % | Sparkline line | A5 Pricing & Markdown; Constants | Avg depth, Markdown depth lever B18 |
| KPI At-risk value | Sparkline area | A5 Pricing & Markdown; ENGINE | ENGINE!M, State filter |
| KPI Recoverable | Sparkline area | A5 Pricing & Markdown; Formulas | Recover at-risk rule |
| KPI Write-off | Sparkline line | A5 Pricing & Markdown | At-risk - Recoverable |
| KPI Comp idx | Sparkline line | A5 Pricing & Markdown; SKU_Master | SKU_Master!R |
| Main at-risk vs recoverable | Combo chart | A5 Pricing & Markdown + ENGINE | candidates, recoverable, write-off |
| At-risk value by vertical | Vertical bar | A5 Charts | section 1; ENGINE_STORE!AA by vertical |
| At-risk value by channel | Horizontal bar | A5 Charts | section 3; ENGINE_STORE!AA by channel |
| Markdown candidate preview | Table | ENGINE + SKU_Master | State, Position, DoS, Price, At-risk, Vendor/Brand |
| At-risk value by category | Vertical bar | ENGINE_STORE + Categories | Cat, At-risk value |
| At-risk value by store | Horizontal bar | ENGINE_STORE + Stores | Store, At-risk value |
| At-risk value by cluster | Vertical bar | A5 Charts | section 2; Cluster |
| Inventory value by state | Vertical bar | A5 Charts | section 4; State inventory value |
| By legal entity | Vertical bar | A5 Pricing & Markdown + Verticals | vertical roll-up |
| Markdown action tabs | Tabbed table | ENGINE + SKU_Master + A5 Pricing & Markdown | Expiry / Overstock / Slow-mover / Suppress reorder |
| What-If Simulator | Paired index bars | Constants + What-If Simulator | B16-B21 levers |
| Compare Scenarios | Multi-line | What-If Per Agent | saved scenario deltas |

---

### 11. Catatan kritis (bukan sekadar deskriptif)

- **Chain-net vs store-gross values differ.** A5 headline at-risk state value is Rp 52.02B from chain-net candidate rollups, while A5 Charts use store-level gross at-risk values from ENGINE_STORE!AA. These will not reconcile 1:1 and should be labelled clearly.
- **A5 candidates exclude Stockout and Low.** The markdown candidate count only uses Expiry, Overstock, and Slow-mover. Stockout and Low are inventory risk states, not markdown targets.
- **Inventory state chart uses inventory value by state.** A5 Charts section 4 shows broad inventory exposure by Stockout/Low/Overstock/Expiry/Slow-mover/Healthy, not only markdown candidates.
- **Recoverable is a rule-based proxy.** The workbook uses state formulas, including expiry excess over shelf-life and overstock/slow-mover excess or 30% position value. It is not an observed sell-through forecast.
- **Average depth is stored at vertical level.** A5 Pricing & Markdown has predefined depth values by vertical. For real implementation, depth should be optimized by SKU elasticity, competitor index, margin, and aging days.
- **Comp idx currently appears flat in A5 rollup.** A5 Pricing & Markdown shows Comp idx = 101 for all verticals. Use SKU-level SKU_Master!R for more granular pricing logic.
- **Slow-mover state can dominate value.** Several top candidates are Slow-mover SKUs with large at-risk values, especially Electronics and Omnichannel items, so the Best Action should not only focus on perishables.
- **Suppress reorder must be synced with A3.** If an item is Overstock or Slow-mover, markdown action should also prevent unnecessary reorder, especially where A3 order-up-to policies would otherwise replenish.
