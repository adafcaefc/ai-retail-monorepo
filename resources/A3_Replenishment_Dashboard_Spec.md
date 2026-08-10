# Agent 3 · Replenishment — Dashboard Documentation

**Source file:** `AI_360_Retail_Suite_v8.2_General_9Agents 20260806.html`
**Backing workbook:** `AI_360_Retail_Dataset_v8.2_General_20260806.xlsx`
**Page function in code:** `pgA3()` → renders via `agentShell('a3', kpis, mainHTML)`
**Compute kernel:** `K3(ov)` over `activeSKUs().map(s => invMetrics(s, ov))`

> Catatan penting: dashboard **tidak membaca sel Excel live**. Ia menjalankan satu *shared engine* (`invMetrics()` / `K3()`) yang **direplikasi 1:1 dari formula workbook**. Kolom "Data di sheet" menunjukkan **di mana angka yang sama tersimpan/dihitung** (`ENGINE`, `Replenishment Detail`, `A3 Replenishment`, `Trade Agreement`, dll.), bukan live-link.

---

## 1. Struktur halaman (urutan render)

`agentShell('a3', …)` menyusun:

1. **Scenario banner** (kalau lever What-If aktif)
2. **Inbox banner** (handoff dari Agent 1/2)
3. **6 KPI cards**
4. **Main chart** — "Requirement vs inbound supply" (`#ch-main`)
5. **Custom `mainHTML`:** 2 chart (order value by route, order value by store) + tabel Purchase Order preview
6. **Dimension charts** (kategori / toko / cluster / lead-time buckets / legal entity)
7. **What-If Simulator + Compare Scenarios**
8. **Suggested Best Action** — release PO ke ERP (3 route) via SoA approval
9. **Chat rail** (Ask AI / Challenge mode)

---

## 2. Inti perhitungan Agent 3 (`K3`)

```
need        = SKU dengan Position < ROP
orderUnits  = Σ max(0, Max − Position)                 // up-to-Max policy
orderValue  = Σ max(0, Max − Position) × price
inbound     = Σ Open PO units
fill        = (total − need) ÷ total × 100             // % SKU sehat
avgCover    = mean(Position ÷ ADS)
route(m)    = fresh → 'Direct'
              catId ∈ {BEV, HOU} → 'Flow-Through'
              else → 'Cross-Dock'
routes{}    = Σ orderValue per route
```

Order dalam **purchase unit** (UOM): `buy = CEILING(order_sales ÷ pack factor)`; nilai = `buy × pack × price`.

**Data di workbook:** ROP `ENGINE!G`, Max `ENGINE!H`, Position `ENGINE!F`, Order units `ENGINE!O`, Order value `ENGINE!P`, Open PO `ENGINE!V`, pack/UOM `SKU_Master.X/Y`; baris requisisi lengkap ada di **`Replenishment Detail`**. Rollup per-vertical di **`A3 Replenishment`**.

---

## 3. KPI Cards (6 buah)

Dihitung `K3(ov)` pada scope aktif.

| # | KPI | Nilai | Tipe visual | Formula (card `fx`) | Data di workbook |
|---|-----|-------|-------------|---------------------|------------------|
| 1 | SKUs to reorder | `k.need.length` | Sparkline **bars** | `count(Position < ROP)` | `Replenishment Detail!J` (Reorder? = YES) |
| 2 | Order units | `fmt(k.orderUnits)` | Sparkline **bars** | `Σ max(0, Max − Position)` | `A3 Replenishment` (sales units); `ENGINE!O` |
| 3 | Order value | `fmtRp(k.orderValue)` | Sparkline **area** | `Σ (Max − Position) × unit price` | `Replenishment Detail!P` (Amount); `ENGINE!P` |
| 4 | Inbound (Open PO) | `fmt(k.inbound)` | Sparkline **line** | `Σ Open PO units in scope` | `ENGINE!V` (Open PO); `Replenishment Detail!F` |
| 5 | Fill rate | `k.fill%` | Sparkline **line** | `SKUs(Position ≥ ROP) ÷ total` | turunan dari `ENGINE!F,G` |
| 6 | Avg days cover | `k.avgCover` d | Sparkline **line** | `mean(Position ÷ ADS)` | `ENGINE!I` (DoS) |

---

## 4. Main Chart — "Requirement vs inbound supply" (`#ch-main`)

- **Fungsi:** `mainChartCard('a3')` + cabang `aid==='a3'` di `renderMain()`.
- **Tipe chart:** **Multi-line** (`multiLine`) — 2 seri:
  - *Requirement* (merah) = `full × 1.02`
  - *Inbound + on-hand cover* (hijau, dash) — bergelombang per periode
- **Split** di `N−1`; period-aware (Daily…Yearly). Formula konsep: `gap = requirement − cover → PO`.
- **Metrics strip** (`#main-stats`): REORDER (Position<ROP), ORDER QTY (Σ Max−Position), PO VALUE, FILL.
- **Data di workbook:** ADS/Position/Open PO dari `ENGINE`/`ENGINE_STORE`; deret `genSeriesP()` (basis `Time Series 24mo`).

---

## 5. Custom `mainHTML` (dua chart + tabel)

### 5a. "Order value by route" (`#ch-a3`)
- **Tipe:** **Vertical bar** (`barChart`, dengan value labels) — Direct / Flow-Through / Cross-Dock.
- **Formula:** `Σ (Max−Position) × price by route`.
- **Route policy (tooltip):** Direct = fresh store-direct lead 2d · Flow-Through = DC pick&pass lead 4d · Cross-Dock = DC consolidation lead 4–5d.
- **Data di workbook:** `ENGINE!P` (Order value) di-split by `route(m)`; DC/route dari `SKU_Master.dc`, fresh flag `SKU_Master.F`.

### 5b. "Order value by store" (`#ch-a3b`)
- **Tipe:** **Horizontal bar** (`hbarChart`), real per-toko (`realStore('a3', st)`), sortir desc.
- **Formula:** `Σ per-store order value (Σ SKU at store)`.
- **Data di workbook:** `ENGINE_STORE` per `Stores`; toko terpilih disorot ungu.

### 5c. Tabel "Purchase order preview · Purchase Order (PO)"
- **Tipe:** tabel scroll; semua baris `need`, diurut by nilai baris.
- **Kolom:** SKU · Route · Vendor · DC · Position · ROP · Max · **Order (sales)** · UOM · **Order (buy)** · Line value.
- **Formula per kolom:**
  - `q (sales) = Max − Position`
  - `buy = CEILING(q ÷ pack)`; `ordered_sales = buy × pack`
  - `UOM: 1 uomBuy = pack × uomSales`
  - `Line value = ordered_sales × price`
- **Data di workbook:** `Replenishment Detail` (Item, On-hand, Open PO, ROP, Max, Order qty sales/buy, Designated vendor, Unit price TA, Amount) + `SKU_Master.X/Y` (UOM/pack). Klik baris → `skuScope(id)`.

---

## 6. Dimension charts (5 buah) — `dimRowHTML('a3')` / `renderDims('a3')`

Measure A3: `Σ (Max−Position) × price where Position < ROP` (**order value**, Rp).

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|-------|-------|------|-----------------|------------------|
| `#ch-dim-cat` | Order value by category | **Vertical bar** (klik → filter) | order value per kategori | `ENGINE!P` group Cat → `A3 Charts` |
| `#ch-dim-store` | Order value by store | **Horizontal bar** (klik → filter) | `realStore('a3')` per toko | `ENGINE_STORE` per `Stores` |
| `#ch-dim-clu` | Order value by cluster | **Vertical bar** (+labels) | order value group cluster | `Stores.Cluster` × `ENGINE_STORE` |
| `#ch-dim-sea` | Delivery lead-time buckets | **Vertical bar** | order qty per lead: 1–2 / 3–4 / 5+ hari | `SKU_Master.lead` + `ENGINE` |
| `#ch-dim-le` | By legal entity | **Vertical bar** (+labels, klik → filter) | roll-up store→LE→chain | `Verticals` + roll-up `ENGINE_STORE` |

Catatan roll-up: kategori/toko/cluster/LE semuanya tie-out ke satu total order value (gross store-level).

---

## 7. Suggested Best Action — Purchase Order 3-route (fitur khas A3)

Berbeda dari agent lain, plan preview A3 punya **tab rute** (`po-routebar`) via `poTab()` / `buildPOgroups()`:

- **3 tab:** Direct Store Delivery (+2d) · Flow-Through (+4d) · Cross-Docking (+5d).
- **`poClassify(s)`:** `fresh → direct`; `catId∈{BEV,HOU} → flow`; else `cross`.
- **Tabel PO per rute:** SKU · Category · Order Qty · On-Hand · Open PO · Position · ROP · Line value · Source(vendor/DC).
- **Export:** `exportPOroute(k)` (satu rute) & `exportPOall()` (PO penuh) → CSV.
- **Submit:** Best Action → `submitERP('po')` → workflow SoA (lihat §9).
- **Data di workbook:** `Replenishment Detail` (multi-vendor split, Trade-Agreement price) + `Trade Agreement` (harga per item×vendor).

---

## 8. Filter mechanism

### 8a. Filter global (top bar)
| Kontrol | id | Efek pada A3 |
|---------|----|--------------|
| All Verticals | `f-le` | `activeSKUs()`/`activeStores()` per vertical; rebuild Category & Store |
| All Categories | `f-cat` | saring SKU per kategori |
| All Stores | `f-store` | saring toko (order value real per toko ikut berubah) |
| Horizon (4/8/12/16 wk) | `f-hz` | memperpanjang proyeksi requirement/cover |
| Search | `f-sku` | filter teks nama/id SKU |
| Refresh | — | `doRefresh()` |
| Scope chip | `scopechip` | ringkasan + `clearScope()` |

### 8b. Filter interaktif per-chart
- Klik **bar kategori** → `state.cat`.
- Klik **bar toko** (`#ch-dim-store` / `#ch-a3b`) → `state.store`.
- Klik **bar legal entity** → `state.le`.
- Klik **baris PO preview / tabel** → `skuScope(id)`.
- **PO route tabs** → `poTab()` mengganti rute yang ditampilkan (bukan filter scope, tapi view PO).
- **Sales View** (Daily…Yearly) → `setPeriod()`.

### 8c. Tooltip/reasoning
Tiap sel menampilkan formula (`data-tt`/`data-fx`): mis. `qty = Max − Position`, `buy = CEIL(order sales ÷ pack)`, `Line value = qty × price`.

---

## 9. What-If — bagaimana perhitungannya (A3)

### 9a. Lever (`state.sim`) → sheet `Constants` B16–B21
| Lever (label A3) | Range | Sel `Constants` | Variabel engine | Efek di Replenishment |
|------------------|-------|-----------------|-----------------|------------------------|
| `demand` (Demand uplift) | −30…+40% | `B16` | `ADS ×(1+demand/100)` → ROP & Max naik | order need lebih besar |
| `promo` (Promo demand) | 0…50% | `B17` | promo-SKU ADS naik | menambah buy plan |
| `md` (Markdown offset) | 0…60% | `B18` | sell-through at-risk | menekan reorder need |
| `inbound` (Open PO) | −40…+60% | `B19` | `OpenPO ×(1+inbound/100)` | mengurangi net order |
| `lead` (Vendor lead) | −2…+6 hari | `B20` | `ROP/Max = ADS×(Lead+Δ+…)` | menaikkan Max & ROP → PO lebih besar |
| `safety` (Safety stock) | −2…+5 hari | `B21` | `ROP += safety` | menaikkan order-up-to |

### 9b. Mesin hitung
- `curOv()`/`state.simApply`: bila aktif, lever menyetir **semua** KPI/chart/tabel A3.
- Efek langsung:
  - `Position = ROUND(On-Hand + OpenPO×(1+inbound/100))`
  - `ROP = ROUND(ADS×(max(1,Lead+lead)+max(0,Safety+safety)))`
  - `Max = ROUND(ADS×(Lead+Safety+lever+4))`
  - `orderUnits = Σ max(0, Max−Position)`; `orderValue` mengikuti.

### 9c. Panel What-If Simulator (`simRowHTML` + `runSimA('a3')`)
- **Chart:** `#ch-simagent` — **paired index bars** (Baseline=100 vs Scenario).
- **Metrik A3 dibandingkan** (`METF.a3`): Reorder SKUs · Order units · PO value · Fill %.
- **Metrics strip** (`#sim-metrics`): ORDER QTY, PO VALUE, FILL, COVER — dengan delta vs baseline.
- Baseline `K3(baseOv())` vs skenario `K3(state.sim)`.

### 9d. Compare Scenarios (`#ch-compare`)
- **Tipe:** **Multi-line overlay** (Baseline + ≤4 skenario); `saveScenario('a3')`, `exportScenarios()`.
- **Data di workbook:** paralel **`What-If Simulator`** & **`What-If · Per Agent`**.

### 9e. Central What-If page (referensi)
Baris A3 di matriks (`runScenario()`): **PO value** (arah baik = turun/inverse) dan **Fill rate** (arah baik = naik).

---

## 10. Ringkasan pemetaan chart → sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---------------------|------|----------------------|-------------------|
| KPI SKUs to reorder | Sparkline bars | `Replenishment Detail!J` ← `ENGINE!F,G` | `Position<ROP` |
| KPI Order units | Sparkline bars | `A3 Replenishment` ← `ENGINE!O` | `Σ Max−Position` |
| KPI Order value | Sparkline area | `Replenishment Detail!P` ← `ENGINE!P` | `Σ(Max−Pos)×price` |
| KPI Inbound | Sparkline line | `ENGINE!V` / `Replenishment Detail!F` | Open PO units |
| KPI Fill rate | Sparkline line | turunan `ENGINE!F,G` | `Pos≥ROP ÷ total` |
| KPI Avg days cover | Sparkline line | `ENGINE!I` | `Position÷ADS` |
| Main requirement vs inbound | Multi-line | `ENGINE`/`ENGINE_STORE` + `Time Series 24mo` | gap→PO |
| Order value by route | Vertical bar | `ENGINE!P` split route | `SKU_Master.dc/F` |
| Order value by store | Horizontal bar | `ENGINE_STORE` per `Stores` | realStore |
| PO preview (tabel) | Tabel | `Replenishment Detail` + `SKU_Master.X/Y` | UOM/pack, TA price |
| Order value by category | Vertical bar | `ENGINE!P` group Cat | `A3 Charts` |
| Order value by cluster | Vertical bar | `Stores.Cluster`×`ENGINE_STORE` | — |
| Lead-time buckets | Vertical bar | `SKU_Master.lead` + `ENGINE` | 1–2 / 3–4 / 5+ hari |
| By legal entity | Vertical bar | `Verticals` + roll-up | store→LE→chain |
| PO route tabs (Best Action) | Tabbed tabel | `Replenishment Detail` + `Trade Agreement` | Direct/Flow/Cross |
| What-If Simulator | Paired index bars | `Constants` B16–B21 + `What-If Simulator` | levers |
| Compare Scenarios | Multi-line | `What-If · Per Agent` | skenario tersimpan |

---

## 11. Catatan kritis (bukan sekadar deskriptif)

1. **`route()` memakai kode kategori yang tidak ada di data ini.** Kondisi Flow-Through = `catId ∈ {'BEV','HOU'}`, padahal Cat ID di workbook berbentuk `GRC-C08`, `GMR-C14`, dst. Akibatnya **cabang Flow-Through nyaris tak pernah terpicu** — hampir semua non-fresh jatuh ke Cross-Dock. Chart "Order value by route" jadi bias. Perlu di-map ke Cat ID nyata.
2. **Dua definisi routing berdampingan.** `K3.route()` (untuk chart) memakai `{BEV,HOU}`, sedangkan `poClassify()` (untuk tab PO & Best Action) memakai aturan yang sama tapi terpisah — keduanya harus dijaga sinkron; saat ini mudah drift.
3. **Requirement/cover di main chart bersifat sintetis.** Seri `req = full×1.02` dan `inbound` bergelombang (`i%2?0.88:1.08`) adalah pola ilustratif, bukan jadwal inbound nyata dari PO. Jangan dibaca sebagai ETA sesungguhnya.
4. **Order value gross vs chain-net.** Dimension charts store/cluster/LE menjumlah order value per toko (gross); headline PO value memakai agregasi chain-net `invMetrics`. Selisih wajar tapi harus dikomunikasikan.
5. **Rounding UOM menambah unit.** `buy = CEIL(q ÷ pack)` lalu `ordered_sales = buy × pack` sering **melebihi** `Max − Position` (mis. contoh GRC-092: 3.920 → 327 karton = 3.924). Line value dihitung atas ordered_sales, jadi sedikit lebih besar dari kebutuhan murni — benar secara MOQ, tapi perlu disadari saat rekonsiliasi nilai.
6. **Fill rate memakai definisi biner sederhana.** `fill = SKUs(Position≥ROP) ÷ total`, bukan service level berbobot demand. Untuk KPI operasional ini cukup, tapi jangan disamakan dengan "service level" di Agent 2/Exec (yang pakai bobot berbeda).
