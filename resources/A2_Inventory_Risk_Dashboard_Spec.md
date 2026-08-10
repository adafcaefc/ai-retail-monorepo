# Agent 2 · Inventory Risk — Dashboard Documentation

**Source file:** `AI_360_Retail_Suite_v8.2_General_9Agents 20260806.html`
**Backing workbook:** `AI_360_Retail_Dataset_v8.2_General_20260806.xlsx`
**Page function in code:** `pgA2()` → renders via `agentShell('a2', kpis, mainHTML)`
**Compute kernel:** `K2(ov)` over `activeSKUs().map(s => invMetrics(s, ov))`

> Catatan penting: dashboard **tidak membaca sel Excel live**. Ia menjalankan satu *shared engine* (`invMetrics()` / `K2()`) yang **direplikasi 1:1 dari formula workbook**. Kolom "Data di sheet" menunjukkan **di mana angka yang sama tersimpan/dihitung** (`ENGINE`, `ENGINE_STORE`, `A2 Inventory Risk`, dll.), bukan live-link.

---

## 1. Struktur halaman (urutan render)

`agentShell('a2', …)` menyusun:

1. **Scenario banner** (kalau lever What-If aktif)
2. **Inbox banner** (handoff dari Agent 1, dll.)
3. **6 KPI cards**
4. **Main chart** — "Projected on-hand vs demand" (`#ch-main`)
5. **Custom `mainHTML`:** 2 chart (at-risk by state, inventory by category) + tabel Risk Register
6. **Dimension charts** (kategori / toko / cluster / expiry-timeline / legal entity)
7. **What-If Simulator + Compare Scenarios**
8. **Suggested Best Action** (route stockout → Agent 3, expiry/overstock → Agent 5)
9. **Chat rail** (Ask AI / Challenge mode)

---

## 2. Definisi state (inti Agent 2)

Klasifikasi per-SKU (`aggMetrics`) — dasar hampir semua angka A2:

```
Position = ROUND(On-Hand + Open PO)
DoS      = Position ÷ ADS
ROP      = ROUND(ADS × (Lead + Safety))
Max      = ROUND(ADS × (Lead + Safety + 4))

Stockout   : Position < 0.6 × ROP
Low        : Position < ROP
Expiry     : perishable AND DoS > shelf-life
Overstock  : non-perish AND DoS > 15
Slow-mover : growth < 1.0 AND DoS > 10
Healthy    : otherwise
```

**Data di workbook:** `ENGINE!J` (State, chain-net) dan `ENGINE_STORE!Q` (State per toko); logika identik dengan sheet **`Formulas`** baris "State".

---

## 3. KPI Cards (6 buah)

Dihitung `K2(ov)` pada scope aktif.

| # | KPI | Nilai | Tipe visual | Formula (card `fx`) | Data di workbook |
|---|-----|-------|-------------|---------------------|------------------|
| 1 | Stockout-risk SKUs | `k.stockout` | Sparkline **bars** | `count(Position < ROP)` (Stockout+Low) | `A2 Inventory Risk!B` = `SUMPRODUCT((ENGINE!B=vert)×(ENGINE!F<ENGINE!G))` |
| 2 | Overstock SKUs | `k.overstock` (+`fmtRp(overstockVal)`) | Sparkline **area** | `count(DoS>15)`; excess `Σ(Position−Max)×price` | `A2 Inventory Risk!C` = `COUNTIFS(ENGINE!J,"Overstock")` |
| 3 | Expiry-risk units | `fmt(k.expiryUnits)` (+`expiryVal`) | Sparkline **bars** | `Σ max(0, Position − ADS × shelf-life)` | `A2 Inventory Risk!D` = `SUMIFS(ENGINE!N, vert)`; per-SKU `ENGINE!N` |
| 4 | Slow-moving SKUs | `k.slow` | Sparkline **line** | `count(growth<1.0 AND DoS>10)` | `ENGINE!J = "Slow-mover"` |
| 5 | Avg days of supply | `k.avgDOS` d | Sparkline **line** | `mean(Position ÷ ADS)` | `A2 Inventory Risk!G` (Avg DoS); per-SKU `ENGINE!I` |
| 6 | Inventory value | `fmtRp(k.invValue)` | Sparkline **area** | `Σ Position × price` | `A2 Inventory Risk!E` = `SUMIFS(ENGINE!L, vert)`; per-SKU `ENGINE!L` |

Drill khusus: KPI #1 → `drillRisk()` (at-risk by state, lihat §7 & §8).
Nilai turunan lain dalam `K2`: `atRiskVal = Σ value where state≠Healthy` (→ `A2 Inventory Risk!F` = `SUMIFS(ENGINE!M, vert)`), `overstockVal = Σ excess`, `healthy = count(Healthy)`.

---

## 4. Main Chart — "Projected on-hand vs demand" (`#ch-main`)

- **Fungsi:** `mainChartCard('a2')` + cabang `aid==='a2'` di `renderMain()`.
- **Tipe chart:** **Multi-line** (`multiLine`) — 2 seri:
  - *Projected on-hand* (biru) — siklus replenishment: `on-hand(t+1) = on-hand − demand + inbound`, dengan penurunan tiap periode ke-4.
  - *Demand* (ungu, dash) — deret `genSeriesP()`.
- **Split line** di `N−1` memisahkan histori vs proyeksi; **period-aware** (Daily…Yearly).
- **Metrics strip** (`#main-stats`): POSITION (On-Hand+Open PO), INBOUND (Open PO), AVG DoS, AT RISK.
- **Data di workbook:** Position/On-hand/Open PO dari `ENGINE!F/…`, `ENGINE_STORE!K,L,M`; demand basis `ENGINE_STORE!J` (ADS); pola musiman `Verticals.seas`.

---

## 5. Custom `mainHTML` (dua chart + tabel)

### 5a. "At-risk value by state" (`#ch-a2`)
- **Tipe:** **Stacked horizontal bar** (`hbarChart` dgn `segs`), satu batang per state (Stockout/Low/Expiry/Overstock/Slow-mover), tiap segmen = kontribusi kategori.
- **Formula:** `Σ Position × price where state = X`.
- **Data di workbook:** `ENGINE!L` (Inv value) & `ENGINE!M` (At-risk) di-group by `ENGINE!J` (State) × kategori; paralel **`A2 Charts`**.

### 5b. "Inventory value by category" (`#ch-a2b`)
- **Tipe:** **Donut** (`donut`), share nilai inventory per kategori.
- **Formula:** `Σ Position × price by category`.
- **Data di workbook:** `ENGINE!L` group by `Cat` (`SKU_Master.CatId`).

### 5c. Tabel "Inventory risk register"
- **Tipe:** tabel scroll; semua SKU, diurut severity (Stockout→Low→Expiry→Overstock→Slow→Healthy) lalu value.
- **Kolom:** SKU · State · On-Hand · Open PO · Position · ROP · DoS · Value · **Action → Next Agent**.
- **Formula per kolom:**
  - `Position = On-Hand + Open PO`
  - `ROP = ADS × (Lead + Safety)`
  - `DoS = Position ÷ ADS`
  - `Value = Position × price`
  - Routing: Stockout/Low → **"→ 3 Replenish"**, selainnya → **"→ 5 Markdown"**
- **Data di workbook:** `ENGINE` kolom On-hand/Open PO(`V`)/Position(`F`)/ROP(`G`)/DoS(`I`)/State(`J`)/Value(`L`). Klik baris → `skuScope(id)`.

---

## 6. Dimension charts (5 buah) — `dimRowHTML('a2')` / `renderDims('a2')`

Measure A2: `Σ Position × price where state ≠ Healthy` (**at-risk value**, satuan Rp). Perhatikan: chart per-toko punya perlakuan khusus (count SKU), bukan Rp.

| Chart | Judul | Tipe | Formula measure | Data di workbook |
|-------|-------|------|-----------------|------------------|
| `#ch-dim-cat` | At-risk value by category | **Vertical bar** (klik → filter) | `Σ Position×price, ≠Healthy` per kategori | `ENGINE!M` group Cat → `A2 Charts` |
| `#ch-dim-store` | Stockout-risk by store | **Stacked horizontal bar** (Stockout+Low) | `storeRisk2(st)` → count `Position<ROP` per toko | `ENGINE_STORE!M<N` per `Stores` |
| `#ch-dim-clu` | At-risk value by cluster | **Vertical bar** (+labels) | at-risk value group by cluster | `Stores.Cluster` × `ENGINE_STORE` |
| `#ch-dim-sea` | Expiry timeline & watchlist | **Vertical bar** (bucket shelf-life) + **watchlist** | fresh units per sisa shelf-life: ≤1 / 2–3 / 4–7 / >7 hari | `SKU_Master.Expiry` + `ENGINE.unitsExpiry` |
| `#ch-dim-le` | By legal entity | **Vertical bar** (+labels, klik → filter) | roll-up store→LE→chain | `Verticals` + roll-up `ENGINE_STORE` |

- **Expiry watchlist** (`#dim-sea-extra`): daftar 4 SKU dengan `unitsExpiry>0`, diurut shelf-life terpendek (tag "Nd").
- **Gross note:** measure per-toko/kategori/cluster/LE bersifat *gross* (menjumlah kantong risiko lokal) → lebih tinggi dari headline **chain-net** (yang saling-hapus surplus vs shortage antar toko).

---

## 7. Filter mechanism

### 7a. Filter global (top bar) — memengaruhi SEMUA visual
| Kontrol | id | Efek pada A2 |
|---------|----|--------------|
| All Verticals | `f-le` | `activeSKUs()`/`activeStores()` per vertical; rebuild Category & Store |
| All Categories | `f-cat` | saring SKU per kategori |
| All Stores | `f-store` | saring toko (Position/On-hand ikut per toko) |
| Horizon (4/8/12/16 wk) | `f-hz` | memperpanjang proyeksi main chart; State dihitung dari posisi saat ini |
| Search | `f-sku` | filter teks nama/id SKU |
| Refresh | — | `doRefresh()` re-render |
| Scope chip | `scopechip` | ringkasan + clear (`clearScope()`) |

Internal: `activeSKUs()` = rantai `le→cat→search`; `activeStores()` = `le→store`.

### 7b. Filter interaktif per-chart (drill-down)
- Klik **bar kategori** (`#ch-dim-cat`) → set `state.cat`.
- Klik **bar toko** (`#ch-dim-store`) → set `state.store`.
- Klik **bar legal entity** (`#ch-dim-le`) → set `state.le`.
- Klik **baris Risk Register** → `skuScope(id)`.
- **Sales View** (Daily…Yearly) → `setPeriod()` mengubah granularity main chart & seri, selaras lintas agent.

### 7c. Tooltip/reasoning
Setiap sel numerik menampilkan formula (`data-tt`/`data-fx` atau `reasonFor()` lexicon), mis. `Position = On-Hand + Open PO`, `DoS = Position ÷ ADS`.

---

## 8. What-If — bagaimana perhitungannya (A2)

### 8a. Lever (`state.sim`, sama dgn What-If pusat) → sheet `Constants` B16–B21
| Lever (label A2) | Range | Sel `Constants` | Variabel engine | Efek di Inventory Risk |
|------------------|-------|-----------------|-----------------|-------------------------|
| `demand` (Demand surge) | −30…+40% | `B16` | `ADS ×(1+demand/100)` | DoS turun, stockout naik |
| `promo` (Promo pull) | 0…50% | `B17` | promo-SKU ADS naik | depletion lebih cepat |
| `md` (Markdown clear) | 0…60% | `B18` | sell-through at-risk | mengurangi overstock/expiry |
| `inbound` (Inbound cover) | −40…+60% | `B19` | `OpenPO ×(1+inbound/100)` | isi Position → ubah stockout/overstock |
| `lead` (Lead time) | −2…+6 hari | `B20` | `ROP = ADS×(Lead+Δ+Safety)` | dorong ROP naik → stockout naik |
| `safety` (Safety days) | −2…+5 hari | `B21` | `ROP += safety` | stockout turun, modal naik |

### 8b. Mesin hitung
- `curOv()` mengembalikan `state.sim` bila `liveSim()` true; toggle "Levers drive whole page" (`state.simApply`) membuat lever menyetir **semua** KPI/chart/tabel A2.
- Efek langsung di `aggMetrics`:
  - `Position = ROUND(On-Hand + Open PO×(1+inbound/100))`
  - `ROP = ROUND(ADS × (max(1,Lead+lead) + max(0,Safety+safety)))`
  - State direklasifikasi ⇒ **stockout/overstock/expiry/slow** semua bergeser.

### 8c. Panel What-If Simulator (`simRowHTML` + `runSimA('a2')`)
- **Chart:** `#ch-simagent` — **paired index bars** (Baseline=100 vs Scenario=`scenario÷baseline×100`).
- **Metrik A2 dibandingkan** (`METF.a2`): Stockout · Expiry units · Overstock · At-risk value.
- **Metrics strip** (`#sim-metrics`): STOCKOUT, Δ EXPIRY, CAPITAL (invValue), DoS — dengan delta vs baseline.
- Baseline `K2(baseOv())` vs skenario `K2(state.sim)`; `baseOv()={demand:0,promo:15,md:25,inbound:0,lead:0,safety:0}`.

### 8d. Compare Scenarios (`#ch-compare`)
- **Tipe:** **Multi-line overlay** (Baseline + ≤4 skenario); `saveScenario('a2')`, `exportScenarios()`.
- **Data di workbook:** paralel **`What-If Simulator`** & **`What-If · Per Agent`**.

### 8e. Central What-If page (referensi lintas-agent)
Baris A2 di matriks (`runScenario()`): **At-risk value** dan **Avg days of supply** — arah "baik" = turun (inverse), ditandai hijau bila delta negatif.

---

## 9. Ringkasan pemetaan chart → sheet

| Visual di dashboard | Tipe | Sheet workbook utama | Kolom/param kunci |
|---------------------|------|----------------------|-------------------|
| KPI Stockout-risk | Sparkline bars | `A2 Inventory Risk!B` ← `ENGINE!F,G` | `Position<ROP` |
| KPI Overstock (+excess) | Sparkline area | `A2 Inventory Risk!C` ← `ENGINE!J` | `DoS>15`, `Σ(Pos−Max)×price` |
| KPI Expiry units (+val) | Sparkline bars | `A2 Inventory Risk!D` ← `ENGINE!N` | `Σ max(0,Pos−ADS×shelf)` |
| KPI Slow-mover | Sparkline line | `ENGINE!J="Slow-mover"` | growth<1 & DoS>10 |
| KPI Avg DoS | Sparkline line | `A2 Inventory Risk!G` ← `ENGINE!I` | `Position÷ADS` |
| KPI Inventory value | Sparkline area | `A2 Inventory Risk!E` ← `ENGINE!L` | `Position×price` |
| Main on-hand vs demand | Multi-line | `ENGINE_STORE!K,L,M` + `Verticals.seas` | replenishment cycle |
| At-risk by state | Stacked hbar | `ENGINE!L,M` group State×Cat | `A2 Charts` |
| Inventory value by category | Donut | `ENGINE!L` group Cat | share % |
| Risk register | Tabel | `ENGINE` (F,G,I,J,L,V) + `SKU_Master` | severity sort |
| At-risk by category | Vertical bar | `ENGINE!M` group Cat | `A2 Charts` |
| Stockout-risk by store | Stacked hbar | `ENGINE_STORE!M<N` + `Stores` | count SO/Low |
| At-risk by cluster | Vertical bar | `Stores.Cluster` × `ENGINE_STORE` | — |
| Expiry timeline + watchlist | Vertical bar + list | `SKU_Master.Expiry` + `ENGINE.unitsExpiry` | shelf-life buckets |
| By legal entity | Vertical bar | `Verticals` + roll-up | store→LE→chain |
| What-If Simulator | Paired index bars | `Constants` B16–B21 + `What-If Simulator` | levers |
| Compare Scenarios | Multi-line | `What-If · Per Agent` | skenario tersimpan |

---

## 10. Catatan kritis (bukan sekadar deskriptif)

1. **Gross vs chain-net bisa menyesatkan.** KPI headline memakai **chain-net** `invMetrics` (agregasi lintas toko), sedangkan dimension charts (store/cluster/LE) memakai **gross per-toko**. Totalnya sengaja beda; wajib dikomunikasikan agar tidak dikira error rekonsiliasi.
2. **At-risk value ≠ jumlah unit berisiko.** `atRiskVal = Σ Position × price` untuk **semua** state non-Healthy (termasuk seluruh posisi SKU Low/Overstock), bukan hanya unit yang benar-benar terancam. Ini melebih-lebihkan "exposure" dibanding metrik unit (`expiryUnits`, `excess`). Perlu label yang jelas.
3. **Overstock excess vs overstock value.** Card #2 menampilkan `overstockVal = Σ(Position−Max)×price` (hanya kelebihan di atas Max), sedangkan tabel/at-risk memakai nilai posisi penuh. Dua definisi "overstock" hidup berdampingan — mudah membingungkan pembaca.
4. **Threshold adalah konstanta kebijakan.** `DoS>15` (overstock) dan `DoS>10` (slow) di-hardcode, bukan parameter musiman. Di musim sepi bisa terlalu ketat; sebaiknya diangkat ke `Constants` agar bisa disetel.
5. **`stockFactor(s)` deterministik dari ID.** On-hand memakai `stockFactor = 0.4 + ((id×37)%100)/58` — pseudo-random berbasis nomor SKU, bukan stok riil. Jadi "On-Hand" bersifat ilustratif; jangan dianggap saldo aktual.
6. **Expiry watchlist vs KPI expiry bisa tak sinkron.** Chart timeline memakai fallback `unitsExpiry || round(position×0.10)` untuk bucket, sementara KPI/`ENGINE!N` memakai `max(0,Position−ADS×shelf)`. Dua rumus unit-expiry berbeda dalam satu halaman — worth di-align.
