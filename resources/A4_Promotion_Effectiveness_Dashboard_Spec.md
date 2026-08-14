## Agent 4 - Promotion Effectiveness - Dashboard Documentation

**Source file:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Backing workbook:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Page function in code:** pgA4() -> renders via agentShell('a4', kpis, mainHTML)  
**Compute kernel:** K4(ov) over activeSKUs().map(s => promoMetrics(s, ov)) plus store-level rollups from ENGINE_STORE and campaign rows from Promotion & Discount Detail.

Catatan penting: dashboard **tidak membaca sel Excel live**. Sama seperti A3, UI menjalankan satu _shared engine_ yang mereplikasi formula workbook. Kolom "Data di workbook" menunjukkan **di mana angka yang sama tersimpan/dihitung** (ENGINE_STORE, SKU_Master, A4 Promotion, A4 Charts, Promotion & Discount Detail, Constants, dll.), bukan live-link.

---

### 1. Struktur halaman (urutan render)

`agentShell('a4', ...)` menyusun:

- **Scenario banner** kalau lever What-If aktif.
- **Inbox banner** untuk handoff dari Demand, Inventory Risk, Replenishment, Pricing/Markdown.
- **6 KPI cards** untuk efektivitas promosi.
- **Main chart** - "Promotion uplift vs margin quality" (#ch-main).
- **Custom mainHTML:**
  - "Incremental margin by vertical" (#ch-a4).
  - "Incremental margin by channel" (#ch-a4b).
  - Tabel **Promotion calendar preview - Promotion & Discount Detail**.
- **Dimension charts**: kategori / toko / cluster / channel / inventory state / legal entity.
- **What-If Simulator + Compare Scenarios**.
- **Suggested Best Action** - approve promo plan, adjust funding, trigger pre-buy or markdown handoff.
- **Chat rail** (Ask AI / Challenge mode).

---

### 2. Inti perhitungan Agent 4 (K4)

```
promoSKUs      = SKUs where SKU_Master.Promo = "Y"
upliftPct      = weighted average expected uplift or modeled promo uplift
incMargin      = SUM(ENGINE_STORE.Promo incr margin)
roi            = incMargin / promoInvestment
cannibPct      = average SKU_Master.Cannib % for active promo SKUs
fundingPct     = average SKU_Master.Fund % or campaign Supplier funding %
preBuyUnits    = SUM(Promotion & Discount Detail.Pre-buy uplift units)
activeCampaign = rows in Promotion & Discount Detail within active date/season scope
```

Workbook formulas behind the engine:

```
ADS = base ADS x seasonality x store size x (1 + demand lever)
    x IF(Promo SKU and promo lever > 0,
         1 + promo lever/100 x 1.3 x (1 - cannib%),
         1)

Promo incr margin = IF(Promo SKU,
  ((ADS x 7 x price) x (0.15 x 2.2 x (1 - cannib%)) x 0.85) x (margin% + 0.16)
  - ((ADS x 7 x price) x 0.15 x (1 - fund%)) x 0.55,
  0)
```

**Data di workbook:** Promo flag SKU_Master!U, fund% SKU_Master!S, cannib% SKU_Master!T, ADS/price/margin in ENGINE_STORE!J/R plus SKU_Master margin, incremental margin ENGINE_STORE!Z, A4 rollup in **A4 Promotion**, campaign mechanics in **Promotion & Discount Detail**, chart rollups in **A4 Charts**.

Chain-level baseline from workbook:

| Metric | Baseline |
|---|---:|
| Active promo SKUs | 241 |
| Weighted uplift | 25.65% |
| Incremental margin | Rp 21.04B |
| Avg ROI | 2.49x |
| Avg cannibalization | 22.38% |
| Avg funding | 42.00% |
| Campaign rows | 48 |
| Total pre-buy uplift | 98,174 units |

---

### 3. KPI Cards (6 buah)

Dihitung `K4(ov)` pada scope aktif.

| # | KPI | Nilai | Tipe visual | Formula (card fx) | Data di workbook |
|---:|---|---|---|---|---|
| 1 | Active promo SKUs | `k.promoSKUs.length` | Sparkline **bars** | `count(SKU_Master.Promo="Y")` | A4 Promotion!B; SKU_Master!U |
| 2 | Uplift % | `k.upliftPct%` | Sparkline **line** | weighted avg expected uplift / modeled promo uplift | A4 Promotion!C; Promotion & Discount Detail!N; Constants!B17 |
| 3 | Incremental margin | `fmtRp(k.incMargin)` | Sparkline **area** | `SUM(ENGINE_STORE.Promo incr margin)` | A4 Promotion!D; ENGINE_STORE!Z |
| 4 | ROI (x) | `k.roi x` | Sparkline **line** | `Incremental margin / promo investment` | A4 Promotion!E; derived engine |
| 5 | Cannib % | `k.cannibPct%` | Sparkline **line** | avg `SKU_Master.Cannib %` for promo SKUs | A4 Promotion!F; SKU_Master!T |
| 6 | Funding % | `k.fundingPct%` | Sparkline **bars** | avg supplier/vendor funding | A4 Promotion!G; SKU_Master!S; Promotion & Discount Detail!M |

---

### 4. Main Chart - "Promotion uplift vs margin quality" (#ch-main)

- **Fungsi:** `mainChartCard('a4')` + branch `aid==='a4'` in `renderMain()`.
- **Tipe chart:** **Combo chart**:
  - _Expected uplift %_ as line.
  - _Incremental margin_ as vertical bars.
  - _Cannibalization drag_ as optional dashed line.
- **Split** at baseline vs scenario if What-If promo lever is active.
- **Metrics strip** (#main-stats): PROMO SKUS, UPLIFT, INCR MARGIN, ROI.
- **Data di workbook:** A4 Promotion!B:E, Promo detail expected uplift, ENGINE_STORE!Z, SKU_Master cannib/funding.

Concept formula:

```
Scenario ADS = baseline ADS x (1 + demand/100)
             x promo uplift factor for promo SKUs
Scenario incremental margin = modeled incremental revenue margin
                            - giveaway / discount cost net of funding
ROI = incremental margin / promo investment
```

---

### 5. Custom mainHTML (dua chart + tabel)

#### 5a. "Incremental margin by vertical" (#ch-a4)

- **Tipe:** **Vertical bar** dengan value labels.
- **Formula:** `SUM(ENGINE_STORE!Z)` by vertical.
- **Workbook values:** Omnichannel Rp 6.59B, Electronics Rp 5.33B, Home & Living Rp 2.95B, Digital/Online Rp 2.17B, Fashion Rp 2.04B, General Merch Rp 1.44B, Health & Beauty Rp 0.42B, Grocery Rp 0.10B.
- **Data di workbook:** A4 Charts section "1 - By vertical"; A4 Promotion!D.

#### 5b. "Incremental margin by channel" (#ch-a4b)

- **Tipe:** **Horizontal bar** sorted desc.
- **Formula:** `SUM(ENGINE_STORE!Z)` by `ENGINE_STORE.Channel`.
- **Workbook values:** Physical Rp 7.12B, Online Rp 4.67B, Click & Collect Rp 2.34B, Marketplace Rp 2.27B, Omni Rp 2.09B, Mobile App Rp 1.35B, Call Center Rp 0.89B, Fulfillment Hub Rp 0.31B.
- **Data di workbook:** A4 Charts section "3 - By channel"; ENGINE_STORE!Z/AE.

#### 5c. Tabel "Promotion calendar preview - Promotion & Discount Detail"

- **Tipe:** tabel scroll; semua baris promosi aktif/scope, sorted by expected uplift or pre-buy uplift.
- **Kolom:** Promo ID - Promo name - Discount type - Scope - Vertical - Target category - Season - Peak month - Mechanism - Discount % - Value/rule - Min qty/threshold - Supplier funding % - Expected uplift % - Pre-buy uplift units - Valid from - Valid to - D365 construct.
- **Formula per kolom kunci:**
  - Expected uplift % = campaign planned uplift.
  - Pre-buy uplift units = incremental units to secure before campaign.
  - Supplier funding % = vendor funding offset against promo cost.
  - D365 construct maps to RetailPeriodicDiscount, PriceDiscTable, EndDisc, MultilineDisc, MixAndMatch, RetailDiscountCode.
- **Data di workbook:** Promotion & Discount Detail columns A:R. Klik baris -> `promoScope(id)`.

---

### 6. Dimension charts (6 buah) - dimRowHTML('a4') / renderDims('a4')

Measure A4: **Incremental margin, Rp** where promotion applies unless noted.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|---|---|---|---|---|
| #ch-dim-cat | Incremental margin by category | **Vertical bar** (klik -> filter) | `SUM(ENGINE_STORE!Z)` by category | ENGINE_STORE!D/Z + Categories |
| #ch-dim-store | Incremental margin by store | **Horizontal bar** | `SUM(ENGINE_STORE!Z)` by store | ENGINE_STORE!B/Z + Stores |
| #ch-dim-clu | Incremental margin by cluster | **Vertical bar** + labels | `SUM(ENGINE_STORE!Z)` by cluster | A4 Charts section "2 - By store cluster"; ENGINE_STORE!AD/Z |
| #ch-dim-sea | Campaign mix by season/type | **Stacked bar** | count promo rows or pre-buy units by season/type | Promotion & Discount Detail!C/G/O |
| #ch-dim-channel | Incremental margin by channel | **Horizontal bar** | `SUM(ENGINE_STORE!Z)` by channel | A4 Charts section "3 - By channel"; ENGINE_STORE!AE/Z |
| #ch-dim-state | Inventory state exposure | **Vertical bar** | inventory value by State | A4 Charts section "4 - By inventory state"; ENGINE_STORE!Q/S |
| #ch-dim-le | By legal entity | **Vertical bar** + labels | roll-up store -> LE -> chain | A4 Promotion; Verticals + ENGINE_STORE |

Catatan roll-up: vertical, cluster, channel, category, and store measures should tie out to total incremental margin when using the same store-level basis. Inventory state chart uses **inventory value**, not incremental margin, so it intentionally does not tie to the headline incremental margin.

---

### 7. Suggested Best Action - Promo plan approval (fitur khas A4)

Plan preview A4 punya tab keputusan via `promoTab()` / `buildPromoGroups()`:

- **3 tab:** High ROI - Funding Gap - Pre-buy Required.
- **promoClassify(p):**
  - High ROI when ROI and uplift are above target and cannib is controlled.
  - Funding Gap when expected uplift is high but supplier funding is below guardrail.
  - Pre-buy Required when pre-buy units or supply risk is high.
- **Tabel action per tab:** Promo ID - Type - Vertical - Category - Uplift - Funding - Cannib - Pre-buy - D365 construct - Recommendation.
- **Export:** `exportPromoPlan(k)` for selected tab and `exportPromoAll()` for full campaign plan -> CSV.
- **Submit:** Best Action -> `submitERP('promo')` -> workflow SoA approval and D365 Commerce discount activation.
- **Data di workbook:** Promotion & Discount Detail + A4 Promotion + ENGINE_STORE incremental margin + SKU_Master promo/funding/cannib flags.

Recommended action logic:

```
if ROI >= target and funding >= guardrail and cannib <= cap:
  recommendation = "Approve promo"
elif uplift high and funding low:
  recommendation = "Negotiate supplier funding"
elif preBuyUnits high or order gap exists:
  recommendation = "Trigger A3 pre-buy PO"
elif cannib high:
  recommendation = "Reduce depth / narrow scope"
```

---

### 8. Filter mechanism

#### 8a. Filter global (top bar)

| Kontrol | id | Efek pada A4 |
|---|---|---|
| All Verticals | f-le | activeSKUs()/activeStores() per vertical; rebuild category, campaign, channel, and store charts |
| All Categories | f-cat | filter SKU/campaign category |
| All Stores | f-store | filter store-level incremental margin and channel/cluster charts |
| Horizon (4/8/12/16 wk) | f-hz | affects promo window, pre-buy horizon, uplift projection |
| Search | f-sku | filter SKU, promo name, Promo ID, or category text |
| Refresh | - | doRefresh() |
| Scope chip | scopechip | ringkasan + clearScope() |

#### 8b. Filter interaktif per-chart

- Klik **bar vertical/legal entity** -> `state.le`.
- Klik **bar kategori** -> `state.cat`.
- Klik **bar toko** -> `state.store`.
- Klik **bar cluster/channel** -> cluster/channel scope.
- Klik **bar inventory state** -> risk-aware promo scope.
- Klik **baris Promotion calendar preview** -> `promoScope(id)`.
- **Promo action tabs** -> `promoTab()` changes action view, not global scope.
- **Sales View** (Daily...Yearly) -> `setPeriod()`.

#### 8c. Tooltip/reasoning

Tiap KPI, chart, dan tabel menampilkan formula (data-tt/data-fx), contoh:

- `Incremental margin = uplift revenue x margin uplift - discount cost net of supplier funding`.
- `ROI = incremental margin / promo investment`.
- `Pre-buy uplift units = campaign units required before valid-from date`.
- `Funding % = supplier funding offset used in promo economics`.

---

### 9. What-If - bagaimana perhitungannya (A4)

#### 9a. Lever (state.sim) -> sheet Constants B16-B21

| Lever (label A4) | Range | Sel Constants | Variabel engine | Efek di Promotion |
|---|---:|---|---|---|
| demand (Demand uplift) | -30...+40% | B16 | ADS x (1+demand/100) | raises base traffic and promo volume |
| promo (Promo depth) | 0...50% | B17 | promo-SKU ADS uplift | raises expected uplift, discount cost, cannib impact |
| md (Markdown depth) | 0...60% | B18 | markdown offset | may shift clearance/overstock economics |
| inbound (Open PO) | -40...+60% | B19 | OpenPO x (1+inbound/100) | supports promo availability and pre-buy readiness |
| lead (Vendor lead) | -2...+6 days | B20 | ROP/Max lead | affects A3 pre-buy feasibility |
| safety (Safety stock) | -2...+5 days | B21 | ROP safety | affects availability and order-up-to need |

#### 9b. Mesin hitung

- `curOv()/state.simApply`: when active, levers drive A4 KPI cards, charts, and table scoring.
- Direct effects:
  - Demand lever raises ADS.
  - Promo lever applies only to SKUs where `SKU_Master.Promo = "Y"`.
  - Cannibalization reduces net sales uplift.
  - Funding offsets discount/giveaway cost.
  - Inbound/lead/safety influence pre-buy handoff to A3.

#### 9c. Panel What-If Simulator (simRowHTML + runSimA('a4'))

- **Chart:** #ch-simagent - **paired index bars** (Baseline=100 vs Scenario).
- **Metrik A4 dibandingkan** (METF.a4): Promo SKUs - Uplift % - Incremental margin - ROI.
- **Metrics strip** (#sim-metrics): INCR MARGIN, ROI, CANNIB, FUNDING / PRE-BUY, with delta vs baseline.
- Baseline `K4(baseOv())` vs scenario `K4(state.sim)`.

#### 9d. Compare Scenarios (#ch-compare)

- **Tipe:** **Multi-line overlay** (Baseline + <=4 saved scenarios); `saveScenario('a4')`, `exportScenarios()`.
- **Data di workbook:** What-If Simulator and What-If Per Agent. A4 uses the same Constants levers and store-level engine.

#### 9e. Central What-If page (referensi)

Baris A4 di central scenario matrix should compare:

- **Incremental margin** (higher is better).
- **ROI** (higher is better).
- **Cannib %** (lower is better / inverse).
- **Pre-buy units** (contextual: availability positive, purchasing pressure negative).

---

### 10. Ringkasan pemetaan chart -> sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---|---|---|---|
| KPI Active promo SKUs | Sparkline bars | A4 Promotion; SKU_Master | Promo flag SKU_Master!U |
| KPI Uplift % | Sparkline line | A4 Promotion; Promotion & Discount Detail | Expected uplift %, promo lever B17 |
| KPI Incremental margin | Sparkline area | A4 Promotion; ENGINE_STORE | ENGINE_STORE!Z |
| KPI ROI (x) | Sparkline line | A4 Promotion | ROI x |
| KPI Cannib % | Sparkline line | A4 Promotion; SKU_Master | Cannib % SKU_Master!T |
| KPI Funding % | Sparkline bars | A4 Promotion; SKU_Master; Promotion Detail | Fund % / Supplier funding % |
| Main uplift vs margin quality | Combo chart | A4 Promotion + ENGINE_STORE + Promo Detail | uplift, inc margin, cannib |
| Incremental margin by vertical | Vertical bar | A4 Charts | section 1; ENGINE_STORE!Z by vertical |
| Incremental margin by channel | Horizontal bar | A4 Charts | section 3; ENGINE_STORE!Z by channel |
| Promotion calendar preview | Table | Promotion & Discount Detail | Promo ID, type, mechanics, dates, D365 construct |
| Incremental margin by category | Vertical bar | ENGINE_STORE + Categories | Cat, Promo incr margin |
| Incremental margin by store | Horizontal bar | ENGINE_STORE + Stores | Store, Promo incr margin |
| Incremental margin by cluster | Vertical bar | A4 Charts | section 2; cluster |
| Campaign mix by season/type | Stacked bar | Promotion & Discount Detail | Season, Discount type, Pre-buy units |
| Inventory state exposure | Vertical bar | A4 Charts | section 4; State value |
| By legal entity | Vertical bar | A4 Promotion + Verticals | vertical roll-up |
| Promo action tabs | Tabbed table | Promotion & Discount Detail + A4 Promotion | High ROI / Funding Gap / Pre-buy Required |
| What-If Simulator | Paired index bars | Constants + What-If Simulator | B16-B21 levers |
| Compare Scenarios | Multi-line | What-If Per Agent | saved scenario deltas |

---

### 11. Catatan kritis (bukan sekadar deskriptif)

- **ROI is stored as a rounded KPI, not a fully exposed investment model.** A4 Promotion provides ROI values around 2.4x-2.6x, but the workbook does not expose a separate promo investment column. If finance needs reconciliation, add a derived `Promo investment = Incremental margin / ROI` or create an explicit spend/funding table.
- **Uplift has two meanings.** A4 Promotion uses a vertical uplift KPI near 25.3%-26.0%, while Promotion & Discount Detail contains campaign-level expected uplift averaging about 46.8%. UI labels should distinguish **modeled net uplift** vs **campaign planned uplift**.
- **Incremental margin is store-level gross, not chain-net.** ENGINE_STORE!Z is summed across store-SKU rows, so vertical, store, cluster, and channel views tie to a store-level gross margin measure.
- **Inventory state chart is not incremental margin.** A4 Charts section 4 is inventory value by state, useful for choosing clearance/promo targets, but it should not be reconciled to the A4 headline incremental margin.
- **Cannibalization is a simple SKU parameter.** It reduces promo economics using a per-SKU Cannib % assumption. It is not a basket-level or substitution model.
- **Supplier funding is an offset, not guaranteed cash collection.** Funding % should be treated as planned vendor support until tied to trade agreement, claim, or accrual workflow.
- **Pre-buy units require A3 handoff.** Promotion & Discount Detail has 98,174 total pre-buy uplift units, but purchase-unit rounding, vendor lead time, MOQ, and open PO availability remain A3 responsibilities.
- **D365 construct mapping is campaign construct-level.** It maps to RetailPeriodicDiscount, PriceDiscTable, EndDisc, MultilineDisc, MixAndMatch, and RetailDiscountCode, but item/category qualification still needs technical validation before activation.
