# Agent 1 · Demand Forecasting — Dashboard Documentation

**Source file:** `AI_360_Retail_Suite_v8.2_General_9Agents 20260806.html`
**Backing workbook:** `AI_360_Retail_Dataset_v8.2_General_20260806.xlsx`
**Page function in code:** `pgA1()` → renders via `agentShell('a1', kpis, mainHTML)`

> Catatan penting: dashboard HTML ini **tidak membaca sel Excel secara live**. Ia menjalankan satu *shared engine* JavaScript (`invMetrics()` / `K1()`) yang **direplikasi 1:1 dari formula workbook**. Jadi kolom "Data di sheet" di bawah menunjukkan **di mana angka yang sama tersimpan/dihitung** di workbook (`ENGINE_STORE`, `ENGINE`, `A1 Demand Forecasting`, dll.), bukan sebuah live-link.

---

## 1. Struktur halaman (urutan render)

`agentShell('a1', …)` menyusun halaman dengan urutan:

1. **Scenario banner** (muncul kalau lever What-If aktif)
2. **Inbox banner** (kalau ada handoff dari agent lain)
3. **6 KPI cards**
4. **Main chart** (Sales View, period-aware) — `#ch-main`
5. **Custom `mainHTML`** (2 chart + tabel SKU)
6. **Dimension charts** (kategori / toko / cluster / seasonality / legal entity)
7. **What-If Simulator + Compare Scenarios**
8. **Suggested Best Action** (forecast basket → Agent 3)
9. **Chat rail** (Ask AI / Challenge mode) di kanan

---

## 2. KPI Cards (6 buah)

Semua KPI dihitung oleh `K1(ov)` di atas `activeSKUs()` dalam scope filter aktif.

| # | KPI | Nilai | Tipe visual | Formula (di card `fx`) | Data di workbook |
|---|-----|-------|-------------|------------------------|------------------|
| 1 | Forecast (next 7d) | `fmt(k.fore7)` unit | Sparkline **area** | `Σ ADS × DOW × Seasonality × TriggerAdj, d=1..7` | `A1 Demand Forecasting!B` = `SUMIFS(ENGINE_STORE!U:U, vertical)`, di mana `ENGINE_STORE!U = J(ADS) × Constants!B10 (7.45)` |
| 2 | Forecast accuracy | `k.accuracy%` | Sparkline **line** | `100% − MAPE`; `MAPE = 6.8 + rand·3.4 + (horizon−8)·0.22` | `A1 Demand Forecasting!C` (Accuracy %) |
| 3 | Demand trend | `pct(k.trend)` | Sparkline **line** | `(avg Fcst next7 ÷ avg Act last7) − 1` | `A1 Demand Forecasting!D` (Trend %) |
| 4 | Stockout-risk SKUs | `k.risk` | Sparkline **bars** | `count(OnHand+OpenPO < ADS×(Lead+Safety))` = `count(Position < ROP)` | `A1 Demand Forecasting!E`; per-baris di `ENGINE!F<G` atau `ENGINE_STORE!M<N` |
| 5 | Predicted to trend | `k.trending` | Sparkline **bars** | `count( viral/seasonal uplift > +15% )` = `count(viral OR growth>1.25)` | `A1 Demand Forecasting!F` (Trending SKUs); flag `SKU_Master` (Viral/Growth) |
| 6 | Seasonality index | `k.seasIdx` | Sparkline **line** | `SeasonalityFactor(month) × 100` | `A1 Demand Forecasting!G`; kurva di `Verticals` (seas) / `SKU_Master!AA` |

KPI #2 punya klik-drill khusus → `drillAccuracy()` (chart backtest per minggu, lihat §7).

---

## 3. Main Chart — "Demand forecast — actual vs AI" (`#ch-main`)

- **Fungsi:** `mainChartCard('a1')` + `renderMain('a1')`
- **Tipe chart:** **Line + confidence band** (`lineBand(ser.hist, ser.fc)`), garis biru = aktual, garis ungu putus-putus = forecast, area ungu = band ±12%.
- **Period-aware (Sales View):** tombol segment `Daily / Weekly / Monthly / Quarterly / Yearly` via `setPeriod()` → `genSeriesP()` mengubah granularity & panjang deret.
- **Metrics di bawah chart** (`#main-stats`): NEXT 7D, ACCURACY, TREND, PEAK (Saturday ×1.35).
- **Formula seri:** `Σ ADS × DOW × Seasonality × TriggerAdj`.
- **Data di workbook:**
  - Aktual historis 12–24 periode → sheet **`Time Series 24mo`** (tren penjualan per vertical).
  - Basis harian → `ENGINE_STORE!J` (ADS) × `Constants` (DOW sum 7.45), dibumbui kurva `Verticals.seas`.
  - Forecast horizon → proyeksi dari base yang sama, panjang mengikuti selector **Horizon** (4/8/12/16 minggu).

---

## 4. Custom `mainHTML` (dua chart + satu tabel)

### 4a. "Demand forecast · actual vs AI" (`#ch-a1`)
- **Tipe:** **Line + confidence band** (`lineBand`) — 12 minggu aktual + forecast ke horizon, dengan legend Actual / AI forecast / Range.
- **Sumber:** `weeklySeries()` — sama engine dengan main chart.
- **Data di workbook:** `Time Series 24mo` (aktual) + `ENGINE_STORE!U` (forecast 7d basis).

### 4b. "Predicted to trend" (`#ch-a1b`)
- **Tipe:** **Horizontal bar** (`hbarChart`), top-7 SKU dengan sinyal naik.
- **Formula:** `uplift = growth + viral signal` → `(growth−1)×100 + (viral?18:0)`.
- **Data di workbook:** `SKU_Master` kolom **Growth** & **Viral**; nilai ADS dari `ENGINE`/`ENGINE_STORE`.

### 4c. Tabel "Forecast detail per SKU"
- **Tipe:** tabel scroll, semua SKU dalam scope, sortir by forecast 7 hari.
- **Kolom:** SKU · Category · ADS · Forecast (per period aktif) · Trend · Signal · Supply State.
- **Formula per kolom:**
  - `ADS = base × seasonality × store size`
  - `Forecast = ADS × days(period)` (daily=1, weekly=7, monthly=30, quarterly=91, yearly=365, ×1.007)
  - `Supply State` = klasifikasi Stockout/Low/Expiry/Overstock/Slow/Healthy
- **Data di workbook:** `ENGINE` (per-SKU: ADS `E`, State `J`) + `SKU_Master` (Growth, Viral, Category). Klik baris → `skuScope(id)` (drill filter).

---

## 5. Dimension charts (5 buah) — `dimRowHTML('a1')` / `renderDims('a1')`

Semua memakai measure A1: `Σ ADS × 7-day DOW` (cocok dengan KPI Forecast 7d). Satuan = **unit**.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|-------|-------|------|-----------------|------------------|
| `#ch-dim-cat` | Forecast by category | **Vertical bar** (klik → filter kategori) | `Σ ADS × DOWSUM` per kategori | `ENGINE_STORE` di-group by `Cat` (via `SKU_Master.CatId`) → paralel `A1 Charts` |
| `#ch-dim-store` | Forecast by store | **Horizontal bar** (klik → filter toko) | `Σ ADS × DOWSUM` real per toko (`realStore`) | `ENGINE_STORE!J` di-group by `Store` (`Stores` sheet) |
| `#ch-dim-clu` | Forecast by cluster | **Vertical bar** (+ value labels) | idem, group by cluster | `Stores.Cluster` × `ENGINE_STORE` |
| `#ch-dim-sea` | Seasonality curve (12 mo) | **Vertical bar** (bulan berjalan disorot) | `SeasonalityFactor(month) × 100` | `Verticals.seas[]` (kurva per vertical) / `Constants` (Month index) |
| `#ch-dim-le` | By legal entity | **Vertical bar** (+ labels, klik → filter vertical) | roll-up store → LE → chain | `Verticals` + roll-up `ENGINE_STORE` |

Catatan roll-up: `#ch-dim-le` menegaskan identitas **store → Legal Entity → chain** (kategori, toko, cluster, LE semuanya tie-out ke satu total).

---

## 6. Filter mechanism

### 6a. Filter global (top bar) — memengaruhi SEMUA chart di halaman
| Kontrol | id | Efek pada A1 |
|---------|----|--------------|
| All Verticals (Legal Entity) | `f-le` | `activeSKUs()`/`activeStores()` disaring per vertical; rebuild opsi Category & Store |
| All Categories | `f-cat` | saring `activeSKUs()` per kategori (kategori bersifat per-vertical) |
| All Stores | `f-store` | saring `activeStores()` per toko |
| Horizon (4/8/12/16 wk) | `f-hz` | `onHorizon()` → panjang forecast + **menurunkan akurasi** (`MAPE += (horizon−8)×0.22`) |
| Search SKU/store/agent | `f-sku` | `onSearch()` → filter teks pada nama/id SKU |
| Refresh | — | `doRefresh()` re-render dari engine |
| Scope chip | `scopechip` | ringkasan scope + tombol clear (`clearScope()`) |

Mekanisme internal: `activeSKUs()` merangkai filter `le → cat → search`; `activeStores()` merangkai `le → store`. Setiap perubahan memanggil `render()`.

### 6b. Filter interaktif per-chart (drill-down)
- Klik **bar kategori** → `state.cat` di-set → seluruh suite refilter.
- Klik **bar toko** → `state.store` di-set.
- Klik **bar legal entity** → `state.le` di-set.
- Klik **baris tabel SKU** → `skuScope(id)` (search = id).
- **Sales View segment** (Daily…Yearly) → `setPeriod()` mengubah granularity semua chart period-aware, **selaras lintas agent** (shared `state.period`).

### 6c. Tooltip / reasoning
Setiap angka & bar punya tooltip (`data-tt` + `data-fx`) atau auto-reason (`reasonFor()` + lexicon `REASONS`) yang menampilkan formula. Ini bukan filter, tapi bagian dari transparansi.

---

## 7. What-If — bagaimana perhitungannya (A1)

### 7a. Lever (sama dgn halaman What-If pusat; `state.sim`)
Disimpan di workbook **`Constants`** (blok "WHAT-IF LEVERS", sel `B16`–`B21`):

| Lever (kode) | Range | Sel `Constants` | Variabel engine | Efek di Demand Forecasting |
|--------------|-------|-----------------|-----------------|-----------------------------|
| `demand` (Demand shift) | −30…+40% | `B16` | `ADS × (1 + demand/100)` | menggeser seluruh kurva forecast, ROP, stockout |
| `promo` (Promo intensity) | 0…50% | `B17` | promo-SKU `ADS ×= 1 + (promo/100)×1.3×(1−cann)` | menaikkan demand SKU promo |
| `md` (Markdown depth) | 0…60% | `B18` | sell-through at-risk | efek tidak langsung ke demand A1 |
| `inbound` (Extra inbound) | −40…+60% | `B19` | `OpenPO × (1+inbound/100)` | posisi & stockout, bukan forecast murni |
| `lead` (Vendor lead time) | −2…+6 hari | `B20` | `ROP = ADS×(Lead+Δ+Safety)` | jumlah SKU di bawah ROP |
| `safety` (Safety stock) | −2…+5 hari | `B21` | `ROP += safety` | jumlah stockout |

### 7b. Mesin hitung
- `curOv()` mengembalikan `state.sim` bila **liveSim()** true (ada lever ≠ baseline). Kalau toggle "Levers drive whole page" aktif (`state.simApply`), lever menyetir **semua** KPI/chart/tabel A1, bukan hanya panel simulator.
- Formula inti forecast dalam skenario:
  - **ADS skenario:** `base × seasonality × store_size × (1 + demand/100)` — untuk SKU promo ditambah `× [1 + (promo/100)×1.3×(1−cannibalization)]`.
  - **Forecast 7d:** `Σ_{d=0..6} ADS × DOW[d]` (DOW = `[0.85,0.90,0.95,1.00,1.15,1.35,1.25]`).
  - **Accuracy:** `100 − MAPE`, dengan `MAPE = 6.8 + rand×3.4 + (horizon−8)×0.22` (horizon lebih panjang ⇒ akurasi turun).
  - **Trend:** `(fore7/7) ÷ (last7/7) − 1`.

### 7c. Panel What-If Simulator di halaman A1 (`simRowHTML` + `runSimA('a1')`)
- **Chart:** `#ch-simagent` — **paired vertical bars** (index): tiap metrik ditampilkan Baseline = 100 vs Scenario = `scenario ÷ baseline × 100`.
- **Metrik A1 yang dibandingkan** (`METF.a1`): Forecast 7d · Stockout SKUs · Accuracy % · Trending.
- **Metrics strip** (`#sim-metrics`): FORECAST 7D, STOCKOUT, TREND, ACCURACY dengan delta (+/−) vs baseline.
- Baseline dihitung `K1(baseOv())`, skenario `K1(state.sim)`; `baseOv()` = `{demand:0,promo:15,md:25,inbound:0,lead:0,safety:0}`.

### 7d. Compare Scenarios (`#ch-compare`)
- **Tipe:** **Multi-line overlay** (`multiLine`) — Baseline + hingga 4 skenario tersimpan.
- **Save/Load:** `saveScenario('a1')` menyimpan `state.sim` + deret forecast; skenario **dibagikan lintas semua agent**.
- **Export:** `exportScenarios()` → `scenarios.csv`.
- **Data di workbook:** paralel dengan sheet **`What-If Simulator`** (baseline vs live) & **`What-If · Per Agent`** (delta skenario +20% demand per vertical).

---

## 8. Ringkasan pemetaan chart → sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---------------------|------|----------------------|-------------------|
| KPI Forecast 7d | Sparkline area | `A1 Demand Forecasting` ← `ENGINE_STORE` | `U = J(ADS) × Constants!B10` |
| KPI Accuracy / Trend / Stockout / Trending / Seasonality | Sparkline | `A1 Demand Forecasting` | `C,D,E,F,G` |
| Main "actual vs AI" | Line + band | `Time Series 24mo` + `ENGINE_STORE` | histori 24 bln + ADS |
| ch-a1 forecast | Line + band | `Time Series 24mo` + `ENGINE_STORE` | idem |
| ch-a1b predicted-to-trend | Horizontal bar | `SKU_Master` + `ENGINE` | Growth, Viral, ADS |
| Forecast detail per SKU | Tabel | `ENGINE` + `SKU_Master` | ADS(E), State(J), Growth, Viral |
| Forecast by category | Vertical bar | `ENGINE_STORE` group Cat | `A1 Charts` |
| Forecast by store | Horizontal bar | `ENGINE_STORE` group Store | `Stores` |
| Forecast by cluster | Vertical bar | `ENGINE_STORE` + `Stores.Cluster` | — |
| Seasonality curve 12 mo | Vertical bar | `Verticals.seas` / `Constants` | Month index |
| By legal entity | Vertical bar | `Verticals` + roll-up | store→LE→chain |
| What-If Simulator | Paired index bars | `Constants` (B16–B21) + `What-If Simulator` | levers |
| Compare Scenarios | Multi-line | `What-If · Per Agent` | skenario tersimpan |

---

## 9. Catatan kritis (bukan sekadar deskriptif)

1. **"Actual" bukan data historis riil.** Deret aktual di-*generate* oleh `weeklySeries()`/`genSeriesP()` dengan noise pseudo-random (`rng(hashScope())`), lalu disandingkan dengan `Time Series 24mo`. Jadi chart "actual vs AI" adalah **ilustrasi**, bukan backtest sungguhan atas data transaksi.
2. **Accuracy mengandung komponen acak.** `MAPE = 6.8 + rand×3.4 + …`. Angka akurasi akan bergeser antar render meski scope sama — perlu diklarifikasi ke stakeholder agar tidak dianggap metrik terukur.
3. **Beberapa lever tidak menyetir demand secara langsung.** `md`, `inbound`, `lead`, `safety` lebih memengaruhi Position/ROP/stockout ketimbang kurva forecast; hanya `demand` dan `promo` yang benar-benar menggeser demand A1. Label per-agent (`WHATIF_LABELS.a1`) menamainya sebagai "Demand shift/Promo intensity/…", yang bisa menyesatkan bila diartikan semua menggerakkan forecast.
4. **Forecast 7d = ADS × 7.45**, sedangkan tabel per-SKU memakai `ADS × 7 × 1.007`. Ada **dua konstanta minggu** (7.45 vs 7.05) di kode; hasil KPI dan tabel bisa sedikit tidak konsisten. Worth di-align.
5. **Gross vs chain-net.** Angka level toko bersifat *gross* (menjumlah kantong lokal tiap toko) sehingga lebih tinggi dari headline chain-net. Ini disengaja, tapi harus dikomunikasikan agar total antar view tidak dikira error.
