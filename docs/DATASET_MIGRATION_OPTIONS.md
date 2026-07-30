# Perombakan Dataset — Opsi & Pertimbangan

**Status:** bahan keputusan, belum ada kode yang dikerjakan
**Tanggal:** 30 Juli 2026
**Konteks:** menentukan apakah skema database dan dataset dirombak total, sebagian, atau tidak sama sekali

---

## 1. Empat sumber referensi

| # | Sumber | Lokasi | Peran |
|---|---|---|---|
| 1 | Workbook lama (03A–03D) | `exisitingdb/` | dataset yang **sedang** dipakai |
| 2 | Database existing | Azure PostgreSQL | hasil impor workbook lama |
| 3 | Tech Priorities | `AI_Finance_Forum_Technical_Priorities_Bilingual_2026-07-29.xlsx..xlsx` | 62 temuan QC + 15 formula check gagal |
| 4 | Mockup v10.1 | `03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html` | **business requirement terbaru** |
| 5 | Dataset baru | `Dataset_AI_Finance_Forum_V1.0_20260728.xlsx` | calon pengganti |

### 1.1 Workbook lama — `exisitingdb/`

Empat file, dibuat terpisah, satu per agent.

| File | Sheet | Mengisi | Batch |
|---|---|---|---|
| `03A_Financial Performance…xlsx` | 10 | `financial_performance.*` | 19 |
| `03B_Cash Flow…xlsx` | 12 | `cashflow.*` | 2 |
| `03C_Collections Credit…xlsx` | 9 | `collections.*` | 11 |
| `03D_Payment Leakage Fraud…xlsx` | 9 | `payment_leakage.*` | 17 |

Perusahaan: **PT Future Manufacturing Tbk** (disebut di 03A dan 03B).
Setiap storyline menulis *"Same company as the other agents"* — konsistensi memang niatnya, tapi tidak pernah diikat.

**Masalah struktural:** periodenya berbeda-beda dan tidak pernah dinyatakan.

| Workbook | Periode | Bukti |
|---|---|---|
| 03A | 1 bulan (Agustus 2026) | judul sheet `02 P&L Actual vs Budget (Aug…)` |
| 03B | 13 minggu ke depan | `Horizon (weeks) = 13` |
| 03C | 1 tahun | `Annual credit sales = 700.000` |
| 03D | 2 minggu (sampel) | `Sample period (weeks) = 2` |

QC-003 melaporkan *"Collection 15× Finance"*. Itu membandingkan angka **sebulan** (46.510) dengan angka **setahun** (700.000). Selisih riilnya 1,25×, bukan 15×. Tetap salah — penjualan kredit tidak boleh melebihi total penjualan — tapi akar masalahnya **periode yang tidak dinyatakan**, bukan dua perusahaan berbeda.

### 1.2 Database existing

| Skema | Tabel | Kolom |
|---|---|---|
| `financial_performance` | 11 | 124 |
| `collections` | 7 | 103 |
| `cashflow` | 7 | 103 |
| `payment_leakage` | 7 | 98 |
| **Subtotal (terdampak)** | **32** | **428** |
| `chat` | 4 | 26 |
| `audit` | 1 | 13 |

Kode yang bergantung: **11 file Python, 59 baris referensi**.

Tidak ada dimensi **entitas** maupun **periode**. Pembeda satu-satunya `import_batch_id`, dan keempat agent memakai batch berbeda yang tidak berhubungan.

### 1.3 Tech Priorities

62 temuan · 34 High · 39 demo blocker · 15 formula check gagal.
Target tanggal: 31 Jul – 13 Agu 2026.

Per 30 Juli, 15 temuan sudah diperbaiki (branch `bug-fix-trial`, commit `53daa2c` + `f448e66`).

### 1.4 Mockup v10.1 — business requirement terbaru

Perusahaan berganti: **Grup Nusantara**, 3 badan hukum.

```
ID01  PT Nusantara Manufaktur Indonesia
SG01  Nusantara Trading Pte Ltd
MY01  Nusantara Malaysia Sdn Bhd
```

Struktur data internal (`var DS`): 752 baris, 12 bulan (Okt 2025 – Sep 2026), 5 segmen, filter Entitas × Periode × Segmen.

Metode EBITDA bridge-nya menjawab QC-010 yang selama ini menggantung:

```js
price = -disc          // efek harga = diskon yang diberikan, dari kolom nyata
cost  = gm - (bgm + vol + mix + price)   // residual eksplisit
```

### 1.5 Dataset baru — `Dataset_AI_Finance_Forum_V1.0`

Star schema, 29 sheet, ±30.000 baris fakta.

| Kelompok | Sheet | Baris |
|---|---|---|
| Dimensi | `10_DIM_Legal_Entity` … `15_DIM_Vendor` | 6 tabel |
| Fakta | `20_FACT_Sales` | **25.593** |
| | `30_FACT_AR_Invoices` | 2.021 |
| | `31_FACT_AP_Invoices` | 635 |
| | `21_FACT_Budget` / `22_FACT_Opex` | 761 / 320 |
| | `40–42_FACT_Cashflow*` / `FX_Exposure` | 294 / 18 / 10 |
| Turunan | `51–57_Finance_*`, `60`, `61` | 8 tabel |
| **Kontrol** | **`90_Reconciliation`** | **14 check, semua PASS** |
| **Kriteria** | **`50_Agent_KPIs`** | **26 angka + derivasinya** |
| **Spesifikasi** | **`91_Filter_Requirements`** | **22 filter** |

Tiga sheet terakhir itu yang membuat dataset ini berbeda kelas: **ia membawa alat validasinya sendiri.**

> `90_Reconciliation`: *"Every check below recalculates from the fact tables. If a check fails, the dataset is broken, not the app."*

README-nya bahkan menyebut bug kita sebagai alasan keberadaannya:

> *"Collection assumes annual credit sales of IDR 700,000 mn while Finance reports revenue of IDR 46,510 mn. This dataset replaces all four batches with one ledger."*

---

## 2. Perbandingan angka

| Metrik | Sekarang | Dataset baru |
|---|---|---|
| Revenue | 46.510 (1 bulan) | **614.632** (12 bulan) |
| EBITDA % | 9,2% | **8,7%** (budget 15,5%) |
| AR | 110.000 | **104.961** |
| DSO | 57,4 hari | **62,3 hari** |
| Cash freed at target | 19.863 | **25.816** |
| Leakage at risk | 7.845 | **9.795** |
| Kas terendah | 6.997,5 (W5) | **5.788,9**, 2 minggu di bawah buffer |
| Hedge disarankan | 2.000.000 USD | **1.800.000 USD** (kebijakan 60%) |

**Praktis semua angka di 62 temuan QC berubah.**

---

## 3. Opsi

### Opsi A — Rombak total sekarang

Bangun skema bintang baru, semua agent membaca dari satu ledger, filter end-to-end.

**Pros**
- Menutup **8 temuan sekaligus secara struktural**: QC-002, 003, 010, 011, 035, 043, 044, 047 — bukan ditambal, tapi masalahnya hilang
- `90_Reconciliation` membuktikan datanya konsisten sebelum kode disentuh
- `50_Agent_KPIs` jadi acceptance criteria siap pakai — 26 angka dengan derivasi
- Sejalan dengan mockup v10.1 (requirement terbaru)
- Ledger tunggal: pertanyaan CFO lintas agent tidak lagi runtuh

**Cons**
- 32 tabel + 11 file Python ditulis ulang
- **62 temuan QC perlu diuji ulang** — angka acuannya berubah semua
- 2 dari 15 perbaikan hari ini bertabrakan (lihat §5)
- Tidak ada data Action/Alert di dataset baru — 47 action card kehilangan sumber
- Tanggal demo belum pasti; kalau event pertengahan Agustus, ini berisiko tinggi

**Effort:** Besar. Blok A (skema+ingestion), B (filter end-to-end), C (4 builder), D (chat tools), E (action) — semuanya tersentuh.

---

### Opsi B — Pakai skema lama, isi dengan data baru

Petakan dataset baru ke 32 tabel yang sudah ada.

**Pros**
- Perubahan kode minimal
- Paling cepat sampai "jalan"

**Cons**
- **Menggagalkan tujuannya sendiri.** Skema lama tidak punya dimensi entitas/periode, jadi:
  - QC-043 (filter) **tidak mungkin** — tidak ada tempat menaruh filternya
  - QC-044 (volume) gagal — 30.000 baris harus diringkas jadi satu irisan, 99% data dibuang
  - Mockup v10.1 tidak bisa dikirim sama sekali
- Menciptakan masalah rekonsiliasi bentuk baru: dataset yang tadinya konsisten dipaksa masuk cetakan yang tidak konsisten

**Effort:** Kecil — tapi menghasilkan sesuatu yang tidak menyelesaikan masalah.
**Penilaian: tidak direkomendasikan.**

---

### Opsi C — Migrasi bertahap per agent *(rekomendasi)*

Skema bintang baru dibangun berdampingan. Agent dipindah satu per satu di belakang feature flag. Skema lama tetap hidup sampai agent terakhir pindah.

Urutan: **Finance → Leakage → Collection → Treasury**
(Finance dulu karena `FACT_Sales` adalah tulang punggung; tiga lainnya turunan darinya.)

**Pros**
- Demo **tidak pernah mati total** — kalau waktu habis, hentikan di agent mana pun, sisanya tetap jalan
- Tiap agent diverifikasi terhadap `50_Agent_KPIs` sebelum lanjut
- Temuan QC diuji ulang per agent, bukan 62 sekaligus
- Bisa dihentikan kalau tanggal event ternyata mepet

**Cons**
- Dua jalur data hidup bersamaan untuk sementara
- Perlu feature flag + disiplin membersihkannya
- Total kerja sedikit lebih besar dari Opsi A (ada biaya jembatan)
- Selama transisi, angka antar agent bisa berbeda — **harus** ditandai jelas di UI

**Effort:** Besar, tapi **terbagi dan bisa dihentikan**. Ini bedanya dengan Opsi A.

---

### Opsi D — Tidak merombak, perbaiki bug di data lama saja

**Pros**
- Risiko paling rendah, demo hari ini tetap jalan
- Tenaga terfokus ke 34 temuan High

**Cons**
- QC-002, 003, 043, 044, 035, 047 **permanen terbuka** — semuanya demo blocker
- Mockup v10.1 tidak bisa dikirim
- Dataset baru yang sudah dibuat tim data terbuang
- QC-010/011 tetap menggantung tanpa keputusan

**Effort:** Kecil.
**Kapan masuk akal:** kalau event kurang dari 2 minggu dan mockup v10.1 bukan komitmen ke klien.

---

## 4. Ringkasan opsi

| | A · Rombak total | B · Skema lama | C · Bertahap | D · Tidak rombak |
|---|---|---|---|---|
| Menutup QC-002/003/043/044 | ✅ | ❌ | ✅ | ❌ |
| Bisa kirim mockup v10.1 | ✅ | ❌ | ✅ | ❌ |
| Demo aman selama pengerjaan | ❌ | ⚠️ | ✅ | ✅ |
| Bisa dihentikan di tengah | ❌ | — | ✅ | — |
| Effort | Besar | Kecil | Besar, terbagi | Kecil |
| Risiko ke tanggal event | Tinggi | Sedang | **Terkendali** | Rendah |

---

## 5. Dua konflik yang harus diputuskan

**QC-015 — perbaikan hari ini harus dicabut.**
`90_Reconciliation` check #10 berbunyi *"Fixes the current bug where split-invoice exposure…"* dengan total **9.795**, artinya Split/threshold **masuk** hitungan at-risk. Tanggal 30 Juli saya justru **mengeluarkannya** (mengikuti `is_direct_loss=false` di data lama). Dataset baru memutuskan sebaliknya, dan dataset yang menang.

**QC-004/005 — sudah diperbaiki dari sisi data.**
Check #13: *"Fixes the current bug where headroom…"*.

### Perbaikan 30 Juli: mana yang selamat

| Selamat (logika/format, bebas dataset) | Perlu ditinjau |
|---|---|
| QC-007, 009, 013, 027, 028, 029, 033, 034, 036, 039, 046 | **QC-015** — keputusannya dibalik |
| 62 test tetap berlaku sebagai jaring pengaman | **QC-014** — `items_flagged` tidak ada di dataset baru |
| | **QC-001, 024** — tabelnya diganti seluruhnya |

---

## 6. Yang masih dibutuhkan

| # | Kebutuhan | Kenapa | Dari siapa |
|---|---|---|---|
| 1 | **Katalog tuas simulator** — tuas apa per agent, satuan, batas | Aksi harus **dihitung**, bukan ditulis. Menutup QC-016/004/017/022 | tim kita |
| 2 | **10–15 kombinasi filter + nilai benarnya** | `50_Agent_KPIs` hanya memberi total ALL. Tanpa nilai per irisan, agregasi filter tidak bisa dibuktikan benar | tim data |
| 3 | **Konfirmasi tanggal demo** | README dataset: snapshot 30 Sep 2026, kas mulai 1 Okt 2026. App & workbook lama: Agustus 2026. Menggeser seluruh angka Treasury | klien / PM |
| 4 | **Batas lever simulator** | Dataset baru hanya punya `43_FX_Assumptions` | tim data |

**Catatan tentang Action:** dataset baru **tidak punya** sheet Action/Recommendation/Alert. Tapi ini bukan penghalang — LLM bisa menghasilkan narasi aksinya. Yang tidak boleh diserahkan ke LLM adalah **angkanya**. Arsitektur yang benar sudah ada (`simulate_impact` di `monitoring_tools.py`), tapi saat ini model menulis **SQL bebas**, dan di situlah QC-016 lahir: angkanya dihitung jujur, tapi dari SQL yang salah. Solusinya mempersempit antarmuka jadi tuas bertipe, bukan mengganti model.

---

## 7. Rekomendasi

**Opsi C — migrasi bertahap**, dengan syarat kebutuhan #3 (tanggal demo) dijawab lebih dulu.

Alasannya bukan karena paling murah — bukan. Tapi karena ini satu-satunya opsi yang **bisa dihentikan di tengah tanpa merusak demo**. Dengan tanggal event yang belum pasti, kemampuan berhenti itu lebih berharga daripada selisih effort-nya.

Kalau ternyata event masih jauh (≥4 minggu), Opsi A lebih rapi: tidak ada biaya jembatan, tidak ada dua jalur data.

**Yang jangan dilakukan:** Opsi B. Ia terlihat hemat, tapi membuang 99% data baru dan tetap tidak bisa mengirim mockup v10.1.

---

## 8. Dampak ke fitur — apa saja yang ikut berubah

Mengganti dataset bukan cuma mengganti angka. Ini permukaan yang terdampak, dihitung dari payload yang berjalan hari ini:

| Agent | KPI | Chart | Tabel | Side | Lever | Sparkline |
|---|---:|---:|---:|---:|---:|---:|
| Finance | 5 | 4 | 1 | 2 | 5 | 0 |
| Treasury | 5 | 3 | 1 | 2 | 4 | 1 |
| Collection | 5 | 4 | 1 | 2 | 2 | 0 |
| Leakage | 5 | 3 | 2 | 2 | 3 | 0 |
| **Total** | **20** | **14** | **5** | **8** | **14** | **1** |

**47 elemen board menampilkan angka.** Semuanya berubah nilainya.

### 8.1 Wajib diperbarui — rusak kalau tidak

| Fitur | Kenapa | Bobot |
|---|---|---|
| 47 elemen board | seluruh angka acuan berganti | Besar |
| 14 lever simulator | baseline dan batas atas/bawah berubah (mis. `hold` maks = fraud 3.800 → 6.250) | Sedang |
| Panel penjelas rumus (`infoRegistry.js`) | rumusnya sendiri berubah — `price = −disc`, bukan lagi driver dari workbook | Sedang |
| 4 tool snapshot untuk chat | harus sadar filter, kalau tidak chat akan berbeda dari dashboard lagi | Sedang |
| Alert | ambang batasnya berbasis angka lama | Sedang |
| 62 test | nilai fixture-nya berubah semua | Kecil, tapi wajib |

### 8.2 Baru jadi mungkin — ini keuntungan yang sering terlewat

Beberapa temuan QC selama ini **mustahil dikerjakan bukan karena sulit, tapi karena datanya tidak ada.** Dataset baru membukanya:

| Fitur | QC | Kenapa dulu mustahil | Kenapa sekarang bisa |
|---|---|---|---|
| **Sparkline di KPI** | QC-054 | data cuma 1 bulan — tidak ada garis untuk digambar | 21 bulan. Sekarang 1 dari 20 KPI punya sparkline; bisa jadi 20 dari 20 |
| **Filter** | QC-043 | tidak ada dimensi entitas/periode | 22 filter, semuanya sudah ada kolom sumbernya |
| **Label periode** | QC-035 | tidak ada periode untuk ditulis | periode jadi dimensi |
| **Banding tahun lalu** | — | hanya ada Agustus 2026 | 2025 **sengaja** disertakan untuk YoY (kata README dataset) |
| **Drill-down** | — | 3 produk | 3 entitas → 24 store → 12 kategori → 120 item |
| **Vendor risk radar** | QC-046 | sedikit vendor | 30 vendor, ada `spend_category` dan `payment_terms` |

Ini penting untuk keputusan: **Opsi D (tidak merombak) berarti QC-054, QC-043, QC-035 permanen tertutup**, bukan tertunda. Tidak ada cara mengerjakannya di atas data 1 bulan.

### 8.3 Kehilangan sumber data

| Fitur | Kondisi |
|---|---|
| Action card (47 buah) | dataset baru **tidak punya** sheet Action/Recommendation |
| Alert | idem |
| Batas lever simulator | hanya ada `43_FX_Assumptions` (khusus FX) |

Ini yang harus disiapkan sendiri, bukan diminta ke tim data — lihat §6 catatan tentang Action.

### 8.4 Konsekuensi untuk urutan kerja

Karena 47 elemen board bergantung pada bentuk data, **filter harus dibangun lebih dulu, bukan belakangan.** Kalau dashboard ditulis ulang dengan asumsi "satu irisan tetap", lalu filter ditambahkan kemudian, keempat builder harus ditulis ulang dua kali.

Urutan yang benar: skema → filter → builder → chat → action.

---

## 9. Catatan untuk file QC

Setelah dataset diganti, sebagian besar dari 62 temuan **tidak bisa diuji ulang apa adanya** — objek yang diujinya sudah tidak ada. QC-014 misalnya: di dataset baru tidak ada `items_flagged` maupun 22 anomali. Temuan itu bukan lulus, bukan gagal — **tidak berlaku lagi**.

Saran:

1. Tambah kolom **"Diuji terhadap dataset mana"** (`lama` / `baru`). Tanpa ini, status Open/Fixed kehilangan makna.
2. Tandai 8 temuan di §3 Opsi A sebagai **"Tidak berlaku — hilang karena ganti dataset"**, bukan "Fixed". Beda sebab, beda pelajaran.
3. **QC-015 turunkan lagi ke Open**, catat bahwa arah keputusannya berubah.
4. Bekukan temuan baru sampai dataset baru terpasang. Menemukan bug di aplikasi yang datanya sedang dibongkar itu membuang tenaga.
