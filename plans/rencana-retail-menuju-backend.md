# Rencana Agent Retail: dari Workbook ke Backend Sungguhan

Dokumen ini menjawab lima pertanyaan yang sering muncul soal tiga modul Retail,
lalu memberi urutan kerja yang bisa langsung dijalankan sambil menunggu data
dari D365.

Ditulis 11 Agustus 2026. Semua angka di sini hasil pengecekan langsung ke kode
dan database, bukan perkiraan.

---

## Ringkasan dalam satu menit

Kita punya tiga modul Retail. **Dua tampilannya sudah jadi, tapi belum ada satu
pun yang punya backend.** Semua angka yang tampil sekarang datang dari file di
dalam frontend, bukan dari database.

Keputusan yang sudah diambil:

1. **Data sementara dari workbook masuk ke PostgreSQL**, bukan disimpan sebagai
   file JSON di frontend. Ini satu-satunya jalur yang nanti membuat chat agent
   bisa hidup — karena tool agent membaca PostgreSQL, dan file JSON di frontend
   tidak terlihat olehnya sama sekali.
2. **Dashboard dulu, chat belakangan.** Buat kedua board jalan di atas API
   sungguhan lebih dulu, baru nyalakan chat.

---

## Kondisi saat ini

| Bagian | Keadaan |
|---|---|
| Schema `retail` di database | **17 tabel sudah ada, semuanya masih 0 baris** |
| Frontend Inventory Risk | Selesai — 11 KPI, panel Suggested Best Action, pecahan state per toko |
| Frontend Demand Forecasting | Selesai — tapi **semua angkanya karangan**, ditulis tangan di kode |
| Replenishment | Masih cangkang kosong |
| Backend builder | Satu stub 22 baris dipakai bertiga, isinya kosong |
| Route dashboard | Terima 3 parameter, sisanya **dibuang diam-diam** |
| Test | frontend 97, backend 348 — semua hijau |

Artinya: `create_retail_schema.py` sudah pernah dijalankan, tapi script
pengisinya belum.

### Satu hal yang perlu dijaga kejujurannya

Workbook **tidak punya riwayat penjualan harian per SKU.** Yang ada cuma
`time_series_24mo` — 192 baris omzet bulanan per vertical.

Konsekuensinya:

- **Inventory Risk dan Replenishment bisa 100% nyata** dari workbook.
- **Kurva forecast Demand tidak bisa.**

Jadi ketergantungan pada D365 itu **hanya satu hal spesifik**, bukan "data
forecast" secara umum — karena enam KPI Demand justru sudah ada persis di sheet
`a1_demand_forecasting`.

---

## Jawaban lima pertanyaan

### 1. Schema mana yang di-query masing-masing modul?

**Demand Forecasting: tidak query apa pun.** Tidak ada schema di belakangnya.
Semua angka ditulis tangan di `mockDataset.js` dan `mockCalculations.js`.

**Inventory Risk: ya, tapi tidak langsung.** Alurnya:

```
workbook Excel
  → extract_workbook_schema.py
  → schema_with_data.json
  → build_inventory_risk_fixture.py   (rekonsiliasi dulu, baru tulis)
  → fixture.json                       ← ini yang dibaca browser
```

JSON itu dibaca **saat build**, bukan saat aplikasi berjalan. Yang dikirim ke
browser adalah hasil olahannya.

**Keduanya belum menyentuh PostgreSQL sama sekali.**

### 2. Vector database itu apa, dan apakah kita butuh?

Vector database menyimpan *embedding* — teks atau gambar diubah jadi deretan
angka, lalu dicari berdasarkan **kemiripan makna**, bukan kecocokan persis.
Contoh gunanya: "carikan dokumen yang mirip dengan pertanyaan ini".

**Proyek ini tidak membutuhkannya.**

Pertanyaan yang dijawab agent kita bersifat angka dan terstruktur. *"SKU mana
yang posisinya di bawah ROP di GRC"* itu predikat SQL — jawabannya pasti, bisa
dihitung ulang, dan bisa dilacak ke selnya di workbook.

Vector database menjawab secara **perkiraan**. Memakainya di sini justru
menghapus sifat yang selama ini kita jaga: setiap angka bisa dipertanggung-
jawabkan asalnya.

Vector database baru masuk akal kalau nanti ada **teks tak terstruktur** —
kontrak vendor, catatan insiden, dokumen kebijakan. Itu di luar lingkup
sekarang.

### 3. Langkah efektif sambil menunggu D365?

Isi `retail.*` di PostgreSQL dari workbook, lalu bangun backend di atasnya.
Detailnya ada di Fase 1–4 di bawah.

Kuncinya: schema `retail` sengaja dibuat memakai nama field yang sama dengan
D365 (`Position`, `ROP`, `DaysCover`, `Signal`). Jadi saat D365 datang, **yang
berubah hanya isi tabelnya** — schema, builder, kontrak, dan UI tidak tersentuh.

### 4. Setelah dua agent selesai, apakah agent bisa dieksekusi?

**Belum. Dashboard bukan agent.**

Yang kita punya nanti adalah papan data. Agent yang bisa "dieksekusi" (bisa
diajak chat) butuh empat hal lagi — lihat Fase 6.

Yang paling penting: **tool agent membaca PostgreSQL.** Itu sebabnya Fase 1
bukan sekadar optimasi, tapi syarat mutlak. Fixture JSON di frontend tidak
akan pernah terlihat oleh agent.

### 5. Replenishment bisa jalan kapan?

Setelah Fase 1 dan 2, dan sebaiknya setelah Inventory Risk membuktikan polanya.

Kabar baiknya: **Replenishment justru paling tidak terblokir.** Datanya paling
lengkap dari ketiganya, dan tidak menunggu D365 sama sekali.

---

## Fase 1 — Isi `retail.*` dari workbook

**1. Jalankan seeder yang sudah ada**

`scripts/seed_retail_dims_from_json.py` mengisi lima tabel dimensi:
`dim_vertical`, `dim_vendor`, `dim_store`, `dim_item`, `dim_calendar`.

Script-nya sudah ditulis tapi belum pernah diuji ke database nyata — siapkan
waktu untuk memperbaiki, bukan menulis ulang.

**2. Buat loader yang hilang: `scripts/seed_retail_facts_from_json.py`**

Ikuti kebiasaan yang sudah dipakai `build_inventory_risk_fixture.py`:
rekonsiliasi dulu, batalkan kalau tidak cocok, hasilnya deterministik.

| Tabel tujuan | Sumber | Catatan |
|---|---|---|
| `fact_inventory_daily` | `engine_store` (16.000 baris) | `on_hand`→`on_hand_qty`, `open_po`→`open_po_qty`, `position`→`position_qty`, `rop`→`rop_qty`, `dos`→`days_cover`, `state`→`state` |
| `fact_price_daily` | `sku_master.price` × toko | Satu tanggal snapshot yang sama |
| `fact_sales_daily` | **tidak bisa diisi** | Lihat peringatan di bawah |

**3. Commit kedua script itu**

Sekarang keduanya masih untracked — kerjaan itu belum punya jaring pengaman.

> ### ⚠️ Jangan mengarang isi `fact_sales_daily`
>
> Menciptakan riwayat harian palsu berarti menaruh angka karangan di tabel yang
> nanti diisi riwayat asli dari D365 — **tanpa penanda apa pun yang memisahkan
> keduanya**. Enam bulan lagi tidak akan ada yang bisa membedakan.
>
> Biarkan kosong. Kurva Demand tetap mock di frontend dan tetap diberi label
> jujur sampai D365 mengirim riwayatnya.

---

## Fase 2 — Satu route untuk dua agent

Perubahan kecil, **satu orang saja yang mengerjakan**, dan semua fase
berikutnya menunggu ini.

Masalahnya: route `GET /dashboard/{agent}` cuma menerima 3 parameter dan
meneruskannya berdasarkan urutan. Parameter lain seperti `store_id` atau
`state` **dibuang diam-diam** — tidak ada error, balasannya tetap 200, tapi
datanya tidak tersaring.

Kenapa tidak boleh dikerjakan dua orang: kalau satu menambah parameter di slot
ke-4 dan yang lain juga, git akan menggabungkannya tanpa protes — dan slot yang
sama jadi punya dua arti. Hasilnya bukan konflik, tapi **data salah yang diam**.

Yang dikerjakan:

- Ubah `get_agent_dashboard` di [`finance_agents_html.py:518`](../backend/src/api/finance_agents_html.py#L518)
  supaya mengoper **satu objek scope** ke `build_dashboard(scope)`. Tiap agent
  ambil key yang dia pahami, abaikan sisanya.
- Sesuaikan empat builder Finance yang sudah ada ke tanda tangan baru.
- **Pisahkan** `retail/retail/dashboard.py` jadi builder per agent — sekarang
  ketiga descriptor menunjuk stub yang sama.

Sisi frontend tidak perlu diubah: `fetchDashboard` sudah mengirim key apa pun
yang diberikan padanya.

---

## Fase 3 — Builder Inventory Risk (tidak butuh D365)

Modul ini bisa 100% nyata setelah Fase 1.

- Pindahkan logika `build_inventory_risk_fixture.py` ke
  `retail/inventory_risk/dashboard.py`, membaca `retail.*` alih-alih JSON.
- **Jadikan builder itu satu-satunya pemilik aturan.** Setelah itu script
  fixture memanggil builder, bukan menulis ulang ambang `Position < ROP`,
  `DoS > 15`, dan `growth < 1.0 && DoS > 10`.

  > Satu aturan yang ditulis di dua tempat adalah aturan yang cepat atau lambat
  > akan berbeda diam-diam. Sejauh ini kita berhasil menghindarinya — jangan
  > buat salinan ketiga.

- **Nyalakan filter Store.** Alasan filter itu mati sekarang adalah grid 16.000
  baris terlalu besar untuk dikirim ke browser — dan itu tidak berlaku lagi di
  sisi server. Setelah backend menghormati `store_id`, ubah
  `SUPPORTS_STORE_SCOPE` jadi `true` di `data/selectors.js`.
- Acuan kontrak: `inventory-risk-backend-handoff.md` (perbaiki dulu bagian yang
  usang — lihat daftar di bawah).
- Cara pindah: ubah `DATA_SOURCE` jadi `"api"` di `data/dashboardData.js`.
  **Tidak ada komponen yang perlu disentuh.**

---

## Fase 4 — Builder Demand Forecasting (sebagian terblokir)

**Yang sudah bisa dikerjakan sekarang:**

Enam KPI Demand ternyata **sudah ada di workbook**, cocok satu per satu:

| KPI di frontend | Kolom di `a1_demand_forecasting` |
|---|---|
| `forecast_next_7d` | `forecast_7d` |
| `forecast_accuracy` | `accuracy_pct` |
| `demand_trend` | `trend_pct` |
| `stockout_risk_skus` | `stockout_risk_skus` |
| `predicted_to_trend` | `trending_skus` |
| `seasonality_index` | `seasonality_idx` |

Jadi enam KPI itu tidak perlu dikarang lagi.

**Samakan dimensi lebih dulu.** Demand mengarang 4 legal entity (`GRC`, `FSH`,
`HBA`, `HME`), padahal dataset punya 8 — dan `HBA` serta `HME` **tidak ada**.
Bentuk kategori dan toko juga berbeda.

Ini bukan soal label. Nilai dimensi itu **kunci penghubung antar data**. Kalau
nanti mau bikin fitur lintas-agent ("SKU ini sedang naik daun **dan** berisiko
kehabisan stok"), dua board itu cuma bisa disambung kalau kodenya identik.

**Ada satu KPI yang dipakai berdua.** `stockout_risk_skus` muncul di kedua
sheet dengan nilai yang persis sama. Inventory membacanya dari data nyata,
Demand mengarangnya — jadi **dijamin berbeda di layar**. Keduanya harus membaca
sumber yang sama.

**Yang masih terblokir:** kurva forecast dan pita confidence. Biarkan mock,
biarkan `is_mock: true`.

---

## Fase 5 — Replenishment

Mulai setelah Inventory Risk membuktikan polanya. Datanya paling kaya:

| Tabel | Baris | Isinya |
|---|---:|---|
| `replenishment_detail` | 800 | jumlah reorder, konversi UoM, vendor tertunjuk, vendor termurah, penghematan |
| `trade_agreements` | 2.400 | tingkat harga per vendor/item, lead time, masa berlaku |
| `vendors` | 8 | lead time, MOQ, OTIF, fill rate, defect rate |
| `a3_replenishment` | 8 | ringkasan KPI per vertical, untuk rekonsiliasi |
| `uom_po_summary` | 8 | ringkasan konversi UoM |

Ikuti urutan Inventory Risk persis: fixture builder dengan rekonsiliasi ke
`a3_replenishment`, lalu contract, selectors, komponen, baru backend builder.

---

## Fase 6 — Chat agent (setelah dashboard)

Menurut `AGENTS.md`, agent yang bisa diajak chat butuh empat hal di luar yang
sudah ada:

1. `config/retail_<nama>_chat.json` dan `config/retail_<nama>_monitoring.json`
2. `tools/<nama>_data.py` berisi `TOOLS`, yang **query ke PostgreSQL** — inilah
   sebabnya Fase 1 jadi syarat mutlak
3. Field descriptor diisi: `chat_agent`, `db_domain`, `snapshot_tool`,
   `schema_tool`, `allowed_tables`, `tools`, dan `dashboard_only=False`
4. `retail.*` ditambahkan ke daftar izin di
   `agents/common/tools/freeform_query.py`

---

## Dokumen handoff sudah disegarkan

`inventory-risk-backend-handoff.md` sempat tertinggal dari perubahan frontend
terakhir. Sudah diperbaiki bersamaan dengan dokumen ini, jadi **aman dipakai
sebagai acuan membangun backend**:

| Bagian | Yang diperbarui |
|---|---|
| Pembuka | 15 → **18** field top-level, sembilan → **sebelas** KPI |
| §2.3 | `overstock_excess_value` dan `expiry_value`, plus peringatan soal dua makna "overstock" |
| §2.6 | tiga hitungan segmen per toko, plus alasan `stockout_count` ≠ `stockout_risk_count` |
| §2.8 | subbagian baru untuk `best_actions` |
| §8 | enam identitas rekonsiliasi baru, semua sudah diuji ke data |
| §14 | baris Suggested actions dibetulkan |
| §15 | checklist mengikuti sebelas KPI |
| `inventory-risk-api-example.json` | di-regenerate dari selector — 18 field, 11 KPI, `best_actions` |

Catatan jujur: angka "15 top-level fields" itu **salah sejak dokumen pertama
kali ditulis** — saat itu sudah 17, bukan 15. Bukan akibat perubahan frontend.

### Soal `schema_version` yang tetap `1`

Payload bertambah satu field dan dua KPI, tapi versinya sengaja tidak dinaikkan.

Alasannya: setiap penambahan bersifat **aditif dan punya nilai default**.
Normalizer mengubah `best_actions` yang hilang jadi `[]` dan KPI yang hilang
jadi `0`. Jadi backend yang dibangun dari versi dokumen lama tetap tampil —
panelnya kosong, bukan crash.

Aturannya sudah ditulis eksplisit di dokumen handoff: **versi 1 berarti "field
ini atau sebagiannya".** Yang menuntut versi 2 adalah **penghapusan field atau
perubahan tipe** — menambah field tidak.

---

## Cara memverifikasi tiap fase

Setiap fase punya pemeriksaannya sendiri. Tidak ada satu pun yang cukup
diverifikasi dengan "tampilannya muncul".

**Fase 1** — setelah seeding, jumlah baris harus cocok:
`dim_item` = 800, `dim_store` = 160, `fact_inventory_daily` = 16.000. Lalu
agregat per vertical dari `fact_inventory_daily` harus sama persis dengan sheet
`a2_inventory_risk` — pemeriksaan 48 nilai yang sama seperti yang sudah
dilakukan `build_inventory_risk_fixture.py`.

**Fase 2** — panggil
`GET /api/html/dashboard/retail.inventory_risk?store_id=S001` dan pastikan
payload-nya **berubah**. Hari ini tidak berubah, dan tidak ada error. Tambahkan
test backend yang gagal kalau parameter tak dikenal dibuang tanpa error.

**Fase 3** — pemeriksaan terkuat sudah tersedia: menyaring ke satu vertical
harus menghasilkan baris `reference_by_vertical` vertical itu **persis**. Uji
juga semua persamaan di §8 dokumen handoff terhadap respons API, di empat scope
yang sama seperti fixture — tanpa filter, satu entity, satu state, dan
kombinasi yang cocok nol baris.

**Saat cutover** — ubah `DATA_SOURCE` jadi `"api"` dan pastikan board tetap
tampil **tanpa satu pun komponen diubah**. Kalau ada komponen yang perlu
disunting, berarti kontraknya belum terpenuhi.

**Seluruh suite** — `npx vitest run` (97) dan
`../.venv/Scripts/python.exe -m pytest tests -q` (348) tetap hijau, ditambah
`npx vite build` yang berhasil.

---

## Bacaan terkait

- [`inventory-risk-backend-handoff.md`](./inventory-risk-backend-handoff.md) — kontrak lengkap Inventory Risk
- [`demand-forecasting-backend-handoff.md`](./demand-forecasting-backend-handoff.md) — kontrak lengkap Demand Forecasting
- [`retail-dashboards-status-and-next-steps.md`](./retail-dashboards-status-and-next-steps.md) — status ketiga modul dan dasar datanya
- [`../AGENTS.md`](../AGENTS.md) — arsitektur agent, tools, dan cara menambah agent baru



Temuan yang perlu lo tahu
1. Sheet A1 cuma punya satu rumus. Lima dari enam KPI-nya (Accuracy, Trend, Stockout-risk, Trending, Seasonality) adalah angka yang diketik tangan ke sel. Cuma Forecast 7d yang dihitung.

2. time_series_24mo bukan riwayat. Tahun kedua identik byte-per-byte dengan tahun pertama di kedelapan vertical. Pertumbuhan YoY-nya nol secara konstruksi. Jadi papan A1 tidak menggambar garis "actual" — tidak ada aktual untuk digambar.

3. Dua nilai pesanan di A3, beda ~20%. Sheet A3 pakai harga jual (Rp 4,46 M untuk Grocery), Replenishment Detail pakai harga beli (Rp 3,60 M). Keduanya benar. Papan menampilkan dua-duanya karena menyetujui PO senilai harga jual itu salah.

4. Rp 4,45 miliar bisa dihemat dengan pindah ke vendor termurah per baris — angka nyata dari saving_vs_designated, ditampilkan per vendor supaya bisa ditindak.

Yang masih dummy — daftar yang lo minta
Yang hilang	Kenapa	Yang saya lakukan
Riwayat penjualan SKU×toko×hari	Tidak ada di manapun	Tidak ada garis aktual sama sekali
Akurasi 92,4%	Diketik, sama untuk 8 vertical	Diteruskan apa adanya, kartu bertuliskan "Workbook constant"
Trend %	Diketik, dan deretnya bertrend nol	Diteruskan, dipakai di kurva, berlabel
Seasonality idx	Diketik 114 vs turunan 108,3	Dua-duanya hidup — KPI pakai yang diketik, chart pakai yang diturunkan
Lever markdown	Tidak ada sukunya di formula manapun	Slider tampil tapi mati, dengan penjelasan
Empat hal yang perlu keputusan lo
1. Bundle naik 368 → 523 KB gzip. Tiga fixture terpisah = 214 KB data, dan 800 SKU yang sama tersimpan tiga kali. Ini konsekuensi pilihan "fixture terpisah" — bisa dipangkas ~130 KB dengan satu berkas dimensi bersama kalau ukuran jadi masalah.

2. Kartu Slow-moving berubah 62 → 51. Spec A2 memberi dua definisi berbeda di dua kolom bersebelahan; yang lama membuat kartu membantah chart di bawahnya.

3. Slider promo/markdown A1 berubah dari 15/25 ke 0/0. Angka 15/25 itu setelan skenario yang diterbitkan workbook, bukan baseline-nya — papan lama membuka di simulasi sambil mengaku menampilkan workbook.

4. Formula Manager sekarang menampilkan 22 formula, bukan 19. Tiga tambahan (DoS, Inventory value, Expiry units) adalah kolom ENGINE nyata; worked example-nya saya bangkitkan dari workbook, bukan diketik.

Yang belum saya kerjakan
A3 main chart (spec §4 "Requirement vs inbound supply") dan What-If A3 (§9) belum dibuat — polanya sudah ada dari A2, tinggal disalin. Backend builder untuk ketiganya juga belum; itu Fase 4 di rencana.

Risiko
Tidak ada yang merusak. Empat berkas yang saya hapus (mockDataset.js dkk) sudah ter-commit sebelumnya jadi bisa dikembalikan dengan git checkout. Tidak ada tulisan ke database, tidak ada yang dikirim ke luar, belum ada commit.

Ledger lengkapnya — setiap angka di ketiga papan, dengan alamat selnya — ada di docs/RETAIL_FORMULA_SOURCES.md.
