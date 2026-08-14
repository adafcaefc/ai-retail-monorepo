## Agent 8 - Vendor & Brand Performance - Dashboard Documentation

**Source file:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Backing workbook:** Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx  
**Page function in code:** pgA8() -> renders via agentShell('a8', kpis, mainHTML)  
**Compute kernel:** K8(ov) over activeSKUs().map(s => vendorBrandMetrics(s, ov)) plus vendor scorecard and brand performance rollups from ENGINE, Main Vendor, Vendor Scorecard, Brand Performance, and A8 Charts.

Catatan penting: dashboard **tidak membaca sel Excel live**. Sama seperti A3/A4/A5/A6/A7, UI menjalankan satu _shared engine_ yang mereplikasi formula workbook. Kolom "Data di workbook" menunjukkan **di mana angka yang sama tersimpan/dihitung** (A8 Vendor & Brand, Vendor Scorecard, Brand Performance, A8 Charts, Main Vendor, Trade Agreement, ENGINE, SKU_Master, dll.), bukan live-link.

---

### 1. Struktur halaman (urutan render)

`agentShell('a8', ...)` menyusun:

- **Scenario banner** kalau lever What-If aktif.
- **Inbox banner** untuk handoff dari A3 replenishment, A4 supplier funding, A5 at-risk/markdown, A6 assortment, and A9 executive summary.
- **6 KPI cards** untuk vendor/brand sales, service, funding, and concentration.
- **Main chart** - "Vendor score vs GMV exposure" (#ch-main).
- **Custom mainHTML:**
  - "GMV by vendor" (#ch-a8).
  - "GMV by brand" (#ch-a8b).
  - Tabel **Vendor scorecard preview - Vendor Scorecard**.
  - Tabel **Brand performance preview - Brand Performance**.
- **Dimension charts**: vendor / brand / vertical / at-risk exposure / category / legal entity.
- **What-If Simulator + Compare Scenarios**.
- **Suggested Best Action** - vendor negotiation, funding recovery, risk mitigation, brand expansion or rationalization.
- **Chat rail** (Ask AI / Challenge mode).

---

### 2. Inti perhitungan Agent 8 (K8)

```
weeklyGMV       = SUM(ENGINE.Weekly GMV)
avgOTIF         = weighted average vendor OTIF by GMV or vertical scope
supplierFunding = SUM(ENGINE.Funding Rp)
topVendorPct    = largest vendor GMV / total GMV x 100
vendorCount     = distinct vendors in scope
brandCount      = distinct brands in scope
vendorScore     = OTIF x 0.35 + Fill x 0.30 + Lead adherence x 0.20 + defect penalty component x 0.15
atRiskExposure  = SUM(ENGINE.At-risk) by vendor
```

Workbook formulas behind the shared engine:

```
Weekly GMV = ADS x 7 x Price
Margin (Rp) = Weekly GMV x Margin %
Funding (Rp) = Weekly GMV x Fund %
Vendor Score = ROUND(OTIF x 0.35 + Fill x 0.30 + Lead adherence x 0.20 + (100 - Defect% x 8) x 0.15, 0)
Funding % = Funding (Rp) / Weekly GMV x 100
Brand Share % = Brand Weekly GMV / Total Weekly GMV x 100
```

**Data di workbook:** Weekly GMV ENGINE!S, Margin ENGINE!T, Funding ENGINE!U, Vendor ENGINE!Q, Brand ENGINE!R, at-risk ENGINE!M, vendor master metrics Main Vendor!J:M, vertical rollup A8 Vendor & Brand, detailed rollups in Vendor Scorecard and Brand Performance, chart data in A8 Charts.

Chain-level baseline from workbook:

| Metric | Baseline |
|---|---:|
| Weekly GMV | Rp 1.815T |
| Weighted avg OTIF | 93.64% |
| Supplier funding | Rp 756.22B |
| Avg top-vendor concentration | 18.54% |
| Vendors | 8 |
| Brands | 12 total in Brand Performance, 7 max per vertical |
| Top GMV vertical | Electronics, Rp 662.47B |
| Highest vendor score | Vendor E, 95 |
| Top brand by GMV/share | Nimbus, Rp 197.65B / 10.9% |

---

### 3. KPI Cards (6 buah)

Dihitung `K8(ov)` pada scope aktif.

| # | KPI | Nilai | Tipe visual | Formula (card fx) | Data di workbook |
|---:|---|---|---|---|---|
| 1 | Weekly GMV | `fmtRp(k.weeklyGMV)` | Sparkline **area** | `Σ ENGINE.Weekly GMV` | A8 Vendor & Brand!B; ENGINE!S |
| 2 | Avg OTIF % | `k.avgOTIF%` | Sparkline **line** | weighted average vendor OTIF | A8 Vendor & Brand!C; Main Vendor!J |
| 3 | Supplier funding | `fmtRp(k.funding)` | Sparkline **area** | `Σ ENGINE.Funding Rp` | A8 Vendor & Brand!D; ENGINE!U |
| 4 | Top-vendor % | `k.topVendorPct%` | Sparkline **line** | largest vendor GMV / total GMV | A8 Vendor & Brand!E; ENGINE!Q/S |
| 5 | Vendors | `k.vendorCount` | Sparkline **bars** | distinct vendor count in scope | A8 Vendor & Brand!F; Vendor Scorecard |
| 6 | Brands | `k.brandCount` | Sparkline **bars** | distinct brand count in scope | A8 Vendor & Brand!G; Brand Performance |

---

### 4. Main Chart - "Vendor score vs GMV exposure" (#ch-main)

- **Fungsi:** `mainChartCard('a8')` + branch `aid==='a8'` in `renderMain()`.
- **Tipe chart:** **Bubble scatter**:
  - X-axis = Vendor Score.
  - Y-axis = Weekly GMV.
  - Bubble size = At-risk exposure.
  - Color = vendor status: Monitor, Negotiate, Grow, or Hold.
- **Alternative fallback:** ranked bar of GMV by vendor with overlaid score line.
- **Metrics strip** (#main-stats): WEEKLY GMV, AVG OTIF, FUNDING, TOP VENDOR %.
- **Data di workbook:** Vendor Scorecard!A:K, A8 Charts GMV by vendor, A8 Vendor & Brand!B:E.

Concept formula:

```
Vendor exposure = Weekly GMV + At-risk exposure
Vendor health = Score x service reliability x funding support
Action priority = high GMV x low score or high at-risk exposure
```

---

### 5. Custom mainHTML (dua chart + dua tabel)

#### 5a. "GMV by vendor" (#ch-a8)

- **Tipe:** **Horizontal bar** sorted desc.
- **Formula:** `SUM(ENGINE!S)` by `ENGINE.Vendor`.
- **Workbook values:** Vendor G Rp 260.61B, Vendor C Rp 237.11B, Vendor F Rp 225.37B, Vendor D Rp 224.86B, Vendor A Rp 222.49B, Vendor E Rp 222.24B, Vendor H Rp 214.29B, Vendor B Rp 207.67B.
- **Data di workbook:** A8 Charts section "GMV by vendor"; ENGINE!Q/S.

#### 5b. "GMV by brand" (#ch-a8b)

- **Tipe:** **Horizontal bar** sorted desc.
- **Formula:** `SUM(ENGINE!S)` by `ENGINE.Brand`.
- **Workbook values:** Nimbus Rp 197.65B, Vertex Rp 188.76B, Meridian Rp 176.94B, Aurora Rp 175.60B, Private Label Rp 173.08B, Pulse Rp 157.46B, Kirana Rp 149.37B, Brava Rp 142.92B, Zephyr Rp 131.55B, Sentosa Rp 115.02B, Onyx Rp 105.59B, Altura Rp 100.69B.
- **Data di workbook:** A8 Charts section "GMV by brand"; ENGINE!R/S.

#### 5c. Tabel "Vendor scorecard preview - Vendor Scorecard"

- **Tipe:** tabel scroll; sorted by action priority, using score, GMV, funding, and at-risk exposure.
- **Kolom:** Vendor - SKUs - Weekly GMV - Margin % - OTIF % - Fill % - Lead adh % - Funding % - Defect % - Score - At-risk value - Recommendation.
- **Formula per kolom kunci:**
  - Margin % = Margin Rp / Weekly GMV.
  - Funding % = Funding Rp / Weekly GMV.
  - Score = OTIF 35% + Fill 30% + Lead adherence 20% + defect-adjusted component 15%.
  - At-risk value = SUM(ENGINE.At-risk) by vendor.
- **Data di workbook:** Vendor Scorecard columns A:K; Main Vendor service metrics; ENGINE vendor rollups.
- **Examples:** Highest score Vendor E = 95; lowest score Vendor F = 89; top GMV and at-risk exposure Vendor G.

#### 5d. Tabel "Brand performance preview - Brand Performance"

- **Tipe:** tabel scroll; sorted by GMV, share, or GMROI.
- **Kolom:** Brand - SKUs - Weekly GMV - Margin % - Growth % - GMROI - Share % - Recommendation.
- **Formula per kolom kunci:**
  - Margin % = brand margin / brand GMV.
  - Share % = brand GMV / total GMV.
  - GMROI = gross margin return on inventory proxy.
  - Growth % = brand growth assumption / performance metric.
- **Data di workbook:** Brand Performance columns A:G; ENGINE Brand/GMV/Margin rollups.
- **Examples:** Nimbus is top GMV/share; Kirana has top GMROI; Brava has the lowest growth in the Brand Performance table.

---

### 6. Dimension charts (6 buah) - dimRowHTML('a8') / renderDims('a8')

Measure A8: **Weekly GMV, Rp** unless noted.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|---|---|---|---|---|
| #ch-dim-vendor | GMV by vendor | **Horizontal bar** (klik -> filter) | `SUM(ENGINE!S)` by Vendor | A8 Charts GMV by vendor; ENGINE!Q/S |
| #ch-dim-brand | GMV by brand | **Horizontal bar** | `SUM(ENGINE!S)` by Brand | A8 Charts GMV by brand; ENGINE!R/S |
| #ch-dim-le | GMV by vertical | **Vertical bar** + labels | `SUM(ENGINE!S)` by vertical | A8 Charts GMV by vertical; A8 Vendor & Brand |
| #ch-dim-risk | At-risk exposure by vendor | **Vertical bar** | `SUM(ENGINE!M)` by Vendor | A8 Charts At-risk by vendor; Vendor Scorecard!K |
| #ch-dim-score | Vendor score by vendor | **Line/bar** | Vendor composite score | Vendor Scorecard!J |
| #ch-dim-brandgmroi | Brand GMROI / share | **Scatter or bar** | GMROI and share by brand | Brand Performance!F:G |

Catatan roll-up: GMV charts tie to ENGINE!S. At-risk exposure charts tie to ENGINE!M and are not the same measure as GMV. Brand counts in the vertical KPI represent distinct brands within a vertical, while Brand Performance contains the full cross-vertical brand roster.

---

### 7. Suggested Best Action - Vendor and brand performance plan (fitur khas A8)

Plan preview A8 punya tab keputusan via `vendorBrandTab()` / `buildVendorBrandGroups()`:

- **4 tab:** Vendor Negotiation - Funding Recovery - At-risk Mitigation - Brand Growth.
- **vendorClassify(v):**
  - Vendor Negotiation when score is low or service reliability is weak.
  - Funding Recovery when funding % is below target for GMV exposure.
  - At-risk Mitigation when vendor at-risk value is high.
  - Brand Growth when brand has high GMROI/growth/share productivity.
- **Tabel action per tab:** Vendor/Brand - GMV - Score - OTIF - Fill - Funding - At-risk - GMROI/Growth - Recommendation.
- **Export:** `exportVendorBrandTab(k)` for selected tab and `exportVendorBrandAll()` for full plan -> CSV.
- **Submit:** Best Action -> `submitERP('vendorBrand')` -> workflow SoA approval, supplier negotiation, funding claim, trade agreement review, or assortment update.
- **Data di workbook:** A8 Vendor & Brand + Vendor Scorecard + Brand Performance + Main Vendor + Trade Agreement + ENGINE.

Recommended vendor action logic:

```
if high GMV and low score:
  recommendation = "Negotiate service recovery plan"
elif high funding opportunity and low funding %:
  recommendation = "Open supplier funding recovery"
elif high at-risk exposure:
  recommendation = "Mitigate risk, review replenishment and markdown"
elif high score and high GMV:
  recommendation = "Grow partnership"
else:
  recommendation = "Monitor"
```

Recommended brand action logic:

```
if high GMROI and growth:
  recommendation = "Expand brand range / space"
elif high GMV but low growth:
  recommendation = "Defend share, refresh activation"
elif low GMROI and low share:
  recommendation = "Review assortment or funding"
else:
  recommendation = "Hold portfolio"
```

---

### 8. Filter mechanism

#### 8a. Filter global (top bar)

| Kontrol | id | Efek pada A8 |
|---|---|---|
| All Verticals | f-le | activeSKUs() per vertical; rebuild vendor, brand, and scorecard rollups |
| All Categories | f-cat | filter vendor/brand metrics to selected category |
| All Stores | f-store | limited effect for chain-net vendor/brand score, but can filter store-level exposure if using ENGINE_STORE |
| Horizon (4/8/12/16 wk) | f-hz | affects GMV/funding run-rate and vendor action horizon |
| Search | f-sku | search SKU, vendor, brand, item, or category text |
| Refresh | - | doRefresh() |
| Scope chip | scopechip | ringkasan + clearScope() |

#### 8b. Filter interaktif per-chart

- Klik **bar vendor** -> `state.vendor`.
- Klik **bar brand** -> `state.brand`.
- Klik **bar vertical/legal entity** -> `state.le`.
- Klik **bar at-risk vendor** -> risk-focused vendor scope.
- Klik **baris Vendor scorecard preview** -> `vendorScope(id)`.
- Klik **baris Brand performance preview** -> `brandScope(id)`.
- **Vendor/brand action tabs** -> `vendorBrandTab()` changes action view, not global scope.
- **Sales View** (Daily...Yearly) -> `setPeriod()`.

#### 8c. Tooltip/reasoning

Tiap KPI, chart, and table cell displays formula (data-tt/data-fx), for example:

- `Weekly GMV = ADS x 7 x Price`.
- `Funding Rp = Weekly GMV x Fund %`.
- `Vendor Score = OTIF 35% + Fill 30% + Lead adherence 20% + defect-adjusted 15%`.
- `Brand Share % = Brand GMV / Total GMV`.

---

### 9. What-If - bagaimana perhitungannya (A8)

#### 9a. Lever (state.sim) -> sheet Constants B16-B21

| Lever (label A8) | Range | Sel Constants | Variabel engine | Efek di Vendor & Brand |
|---|---:|---|---|---|
| demand (Demand uplift) | -30...+40% | B16 | ADS x (1+demand/100) | raises Weekly GMV, margin, funding by vendor/brand |
| promo (Promo depth) | 0...50% | B17 | promo-SKU ADS uplift | raises vendor/brand GMV where promo SKUs apply and affects funding leverage |
| md (Markdown depth) | 0...60% | B18 | markdown offset | changes at-risk mitigation and brand markdown exposure |
| inbound (Open PO) | -40...+60% | B19 | OpenPO x (1+inbound/100) | affects availability, at-risk value, and vendor exposure |
| lead (Vendor lead) | -2...+6 days | B20 | ROP/Max lead | changes replenishment pressure and vendor lead performance scenario |
| safety (Safety stock) | -2...+5 days | B21 | ROP safety | changes stock exposure and at-risk vendor mix |

#### 9b. Mesin hitung

- `curOv()/state.simApply`: when active, levers drive A8 KPI cards, charts, scorecard prioritization, and vendor/brand recommendations.
- Direct effects:
  - Demand/promo levers change ENGINE Weekly GMV, Margin, Funding and brand/vendor share.
  - Markdown/inbound levers affect at-risk exposure by vendor and brand.
  - Lead/safety levers can affect vendor-driven availability and exposure, though Vendor Scorecard service metrics are static unless scenario overrides are added.

#### 9c. Panel What-If Simulator (simRowHTML + runSimA('a8'))

- **Chart:** #ch-simagent - **paired index bars** (Baseline=100 vs Scenario).
- **Metrik A8 dibandingkan** (METF.a8): Weekly GMV - Avg OTIF - Supplier funding - Top-vendor %.
- **Metrics strip** (#sim-metrics): GMV, OTIF, FUNDING, CONCENTRATION, AT-RISK, with delta vs baseline.
- Baseline `K8(baseOv())` vs scenario `K8(state.sim)`.

#### 9d. Compare Scenarios (#ch-compare)

- **Tipe:** **Multi-line overlay** (Baseline + <=4 saved scenarios); `saveScenario('a8')`, `exportScenarios()`.
- **Data di workbook:** What-If Simulator and What-If Per Agent. A8 uses the same Constants levers plus vendor/brand rollups from ENGINE.

#### 9e. Central What-If page (referensi)

Baris A8 di central scenario matrix should compare:

- **Weekly GMV** (higher is better).
- **Supplier funding** (higher is better, subject to claim quality).
- **Avg OTIF / score** (higher is better).
- **At-risk exposure** (lower is better / inverse).
- **Top-vendor concentration** (contextual: high concentration may be risk or strategic scale).

---

### 10. Ringkasan pemetaan chart -> sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---|---|---|---|
| KPI Weekly GMV | Sparkline area | A8 Vendor & Brand; ENGINE | ENGINE!S |
| KPI Avg OTIF % | Sparkline line | A8 Vendor & Brand; Main Vendor | Main Vendor!J; weighted by GMV |
| KPI Supplier funding | Sparkline area | A8 Vendor & Brand; ENGINE | ENGINE!U |
| KPI Top-vendor % | Sparkline line | A8 Vendor & Brand; ENGINE | largest vendor GMV / total GMV |
| KPI Vendors | Sparkline bars | A8 Vendor & Brand; Vendor Scorecard | distinct vendors |
| KPI Brands | Sparkline bars | A8 Vendor & Brand; Brand Performance | distinct brands |
| Main vendor score vs GMV exposure | Bubble scatter | Vendor Scorecard + A8 Charts | score, GMV, at-risk |
| GMV by vendor | Horizontal bar | A8 Charts | GMV by vendor; ENGINE!Q/S |
| GMV by brand | Horizontal bar | A8 Charts | GMV by brand; ENGINE!R/S |
| Vendor scorecard preview | Table | Vendor Scorecard + Main Vendor | OTIF, Fill, Lead adh, Defect, Score |
| Brand performance preview | Table | Brand Performance + ENGINE | GMV, Margin, Growth, GMROI, Share |
| GMV by vertical | Vertical bar | A8 Charts | GMV by vertical; A8 rollup |
| At-risk exposure by vendor | Vertical bar | A8 Charts + Vendor Scorecard | ENGINE!M by vendor |
| Vendor/brand action tabs | Tabbed table | A8 rollups + Scorecard + Brand Performance + Trade Agreement | negotiation / funding / risk / growth |
| What-If Simulator | Paired index bars | Constants + What-If Simulator | B16-B21 levers |
| Compare Scenarios | Multi-line | What-If Per Agent | saved scenario deltas |

---

### 11. Catatan kritis (bukan sekadar deskriptif)

- **Vendor Scorecard service metrics are static master data.** OTIF, Fill, Defect, and Lead adherence are pulled from Main Vendor and do not move with What-If unless a scenario override is added.
- **A8 combines commercial and operational measures.** Weekly GMV and funding come from ENGINE transaction economics, while OTIF/fill/defect come from supplier master. Label this clearly to avoid reconciling unrelated grains.
- **Top-vendor % is vertical-level concentration.** The vertical KPI is not the same as chain-wide top vendor share. It should be computed within the current scope.
- **Brand Performance has 12 chain-wide brands, while vertical rollup shows 6-7 brands.** This is because some verticals do not contain every brand. Use scope-specific distinct counts in UI.
- **Supplier funding is modeled funding, not cash collected.** Funding Rp comes from Weekly GMV x Fund %, and should be tied to trade agreements, claims, accruals, or vendor settlement in production.
- **Vendor G needs careful interpretation.** Vendor G is top by GMV and at-risk exposure, but has lower OTIF than several vendors. It may be strategic scale plus operational risk, not simply a poor vendor.
- **Vendor E has highest composite score but not highest GMV.** Best Action should consider both score and exposure, otherwise high-performing but smaller vendors may be underutilized.
- **Brand growth and GMROI can conflict.** Nimbus leads GMV/share, while Kirana leads GMROI. Brand decisions should balance scale, profitability, and growth rather than ranking on one metric.
- **Trade Agreement is available for negotiation detail.** A8 should link service/funding issues to Trade Agreement terms, validity, min qty, lead time and designated vendor status before action submission.
