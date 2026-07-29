# QC Triage — AI Finance Forum

Analisis atas `QC_Testing_Tracker_AI_Finance_Forum_v2.0_20260728.xlsx` (62 temuan QC + 31 uji manual MT).

**Tanggal analisis:** 29 Juli 2026
**Basis verifikasi:** pembacaan kode pada repo lokal (`main` @ `76b3231`), bukan pengujian aplikasi berjalan.

---

## 0. Catatan penting sebelum membaca

**Tracker menguji build Azure per 28 Juli. Repo lokal sudah lebih maju dari build itu.** Beberapa temuan yang berstatus "Terbuka" di Excel ternyata **kodenya sudah ada** di repo. Contoh terverifikasi:

| No QC | Status di Excel | Kondisi sebenarnya di repo |
|---|---|---|
| QC-049 Panel penjelasan rumus | Terbuka, **Kritis** | **SUDAH ADA** — [infoRegistry.js](../../frontend/src/infoRegistry.js) (415 baris, port 1:1 dari mockup v9.4) + [InfoCard.jsx](../../frontend/src/components/InfoCard.jsx) + `openInfo()` di [Workboard.jsx:31](../../frontend/src/components/Workboard.jsx#L31) |
| QC-062 Chat render grafik/tabel | Selesai | **SUDAH ADA** — [html_renderer.py](../../backend/src/llm/html_renderer.py) emit `chart`+`table`, dirender [BlockRenderer.jsx](../../frontend/src/components/BlockRenderer.jsx) → [ChartRenderer.jsx](../../frontend/src/components/ChartRenderer.jsx) |

**Implikasi:** sebelum mulai fixing, **deploy ulang build terbaru ke Azure lalu uji ulang**. Sebagian temuan kemungkinan gugur sendiri tanpa perlu ngoding.

**Blocker eksternal:** `Dataset_AI_Finance_Forum_v1.xlsx` (dataset pengganti yang dirujuk sheet 04) **tidak ada di repo**. Ini menggantung 4 temuan terberat (QC-002, QC-003, QC-043, QC-044). Kejar file ini dulu.

---

## 1. Status fitur: sudah ada vs belum ada

### 1a. SUDAH ADA — tinggal verifikasi / tidak perlu ngoding

| No QC | Fitur | Bukti di kode |
|---|---|---|
| QC-049 | Panel penjelasan rumus (Reasoning) | `infoRegistry.js`, `InfoCard.jsx`, `findInfo()` |
| QC-062 | Chat menampilkan grafik + tabel | `html_renderer.py:70,94`, `ChartRenderer.jsx` (2140 baris) |
| QC-050 | Mode cerita terpandu | Ditutup sebagai **Bukan cacat** — tidak dikerjakan |
| QC-045 | Perilaku interaktif belum diuji | Bukan cacat aplikasi, sudah dieksekusi lewat sheet 02B |

### 1b. SEBAGIAN ADA — pondasi sudah jadi, tinggal dilengkapi

| No QC | Fitur | Yang sudah ada | Yang kurang |
|---|---|---|---|
| QC-054 | Sparkline KPI | Komponen `KpiSparkline` ([Workboard.jsx:386](../../frontend/src/components/Workboard.jsx#L386)) + Treasury emit `trend` ([treasury/dashboard.py:111](../../backend/src/llm/agents/finance/treasury/dashboard.py#L111)) | Finance, Leakage, Collection belum emit `trend` |
| QC-053 | Pemilih cakupan simulator | Finance punya `scope_options: ["all","fx"]` ([finance/dashboard.py:474](../../backend/src/llm/agents/finance/finance/dashboard.py#L474)) + state `scope` di Workboard | 3 agent lain belum punya `scope_options` |
| QC-055 | Tingkat keyakinan aksi | Kolom `confidence_label` ada di DB ([models.py:557](../../backend/src/db/models.py#L557)) | Tidak diekspos di `actions/service.py`, `router.py`, maupun UI |
| QC-056 | Tampilan rantai eksekusi | [RouteRenderer.jsx](../../frontend/src/components/RouteRenderer.jsx) render daftar rute | Statis — tidak ada animasi / jejak eksekusi bertahap |
| QC-059 | Tombol reset | Slider reset ke 0 jalan (MT-008 lulus), `resetAndRepopulateAlerts()` ada | Tidak ada tombol reset global (tampilan + simulator + chat) satu klik |

### 1c. BELUM ADA SAMA SEKALI

| No QC | Fitur | Verifikasi |
|---|---|---|
| QC-043 | Filter (22 filter) | Tidak ada satu pun parameter filter di seluruh endpoint |
| QC-044 | Volume dataset | Tidak ada tabel/kolom `legal_entity`, `store`, `item`, `category` di [models.py](../../backend/src/db/models.py) |
| QC-035 | Label periode pada grafik | Tidak ada field `period`/`as_of` di payload dashboard manapun |
| QC-051 | Simpan / muat / bandingkan skenario | Hanya 4 endpoint `recalculate`, tanpa persistence |
| QC-052 | Preset simulator | Payload simulator hanya `inputs` + `baseline` |
| QC-057 | Umpan notifikasi aktivitas | Lonceng di `AlertsPanel` isinya **alert** (temuan), bukan aktivitas agent |
| QC-058 | Pengalih Bahasa Indonesia | Tidak ada i18n. Prompt malah mengunci: `"Your responses should be in English only"` ([common.json:182](../../backend/src/llm/agents/common/config/common.json#L182)) |
| QC-060 | Hitung dengan parameter sendiri | Chat dan `recalculate` tidak tersambung |
| QC-061 | Kartu next best action di dashboard | `Workboard.jsx` tidak merender aksi sama sekali |

### 1d. MASIH RUSAK — kode ada tapi salah

Terverifikasi masih bermasalah di repo:

- **QC-039** kata `illustrative` masih bertebaran: [finance/dashboard.py:48,337,477](../../backend/src/llm/agents/finance/finance/dashboard.py#L337), [leakage/dashboard.py:42,338,405](../../backend/src/llm/agents/finance/leakage/dashboard.py#L338), [treasury/cashflow/service.py:367,388](../../backend/src/llm/agents/finance/treasury/cashflow/service.py#L367)
- **QC-020** kunci agent masih bentrok: registry pakai `finance.collection` ([modules.py:16](../../backend/src/llm/agents/modules.py#L16)) tapi payload pakai `"agent": "collections"` ([collection/dashboard.py:264](../../backend/src/llm/agents/finance/collection/dashboard.py#L264))
- **QC-015/032** baseline Leakage masih hardcode (`overbill_amount=400`, `other_blocked=500`, `at_risk=7845`) di [leakage/dashboard.py:30-32](../../backend/src/llm/agents/finance/leakage/dashboard.py#L30)
- **QC-006** endpoint `/conversations` mengembalikan seluruh riwayat tanpa filter apa pun ([finance_agents_html.py:414](../../backend/src/api/finance_agents_html.py#L414))

---

## 2. Clustering berdasarkan tingkat kesulitan

### 🟢 GAMPANG — 24 item

Ganti label, ganti string, benerin pembulatan, satu-dua baris. Tidak menyentuh model data. **Estimasi: 2–3 hari untuk seluruh cluster.**

| No | Temuan | Kenapa gampang |
|---|---|---|
| MT-018 | `Object of type Decimal is not JSON serializable` | **Bug crash — kerjakan paling pertama.** Cukup coercion `Decimal → float` di serializer. Ini mematikan skenario cross-agent yang justru jualan utama demo |
| QC-039 | Hapus kata "illustrative" | Hapus string di 8 lokasi (jangan sentuh yang di prompt config — itu instruksi ke LLM, bukan tampilan) |
| QC-006 | Bersihkan 190 percakapan uji | `DELETE` baris, atau filter query di `/conversations` |
| QC-041 | Judul alert W5 padahal data W6 | Variabel template tertukar |
| QC-009 | Dua target margin EBITDA | Ganti hardcode `15%` → `15.7%` |
| QC-013 | Label batang "Current 95%" | Ganti nama jadi "95% untuk semua", atau samakan asumsi ke 7.557,5 |
| QC-014 | KPI 22 flags vs tabel 10 baris | Tambah keterangan "menampilkan 10 dari 22" |
| QC-018 | Label porsi overdue top-2 | Rename label |
| QC-025 | Label eksposur FX | Rename + balik logika tampilan |
| QC-030 | Label "Overdue AR" untuk 2 pelanggan | Rename label |
| QC-031 | Angka setahun vs per siklus | Tambah label "(disetahunkan)" |
| QC-032 | 900 mn dengan 3 nama | Satukan penamaan |
| QC-012 | Dua angka mirip (-1.880 vs -1.881) | Bedakan pembulatan/label |
| QC-027 | Margin dibulatkan ke bawah | `truncate` → `round half up` |
| QC-028 | Gauge DSO progres 120% | Balik arah gauge |
| QC-029 | Format angka tidak konsisten | Bikin satu helper formatter, pakai di semua tempat |
| QC-033 | Urutan pasangan grafik berlawanan | Samakan urutan config |
| QC-034 | Batang nol di sebelah batang bernilai | Ganti jenis grafik / label eksplisit |
| QC-036 | Grafik samping duplikat grafik utama | Ganti isi slot samping |
| QC-038 | Kolom bucket menempatkan semua ke bucket tertua | Rename kolom jadi "Bucket tertua" |
| QC-024 | Leakage buka di grafik kosong | Ganti `default_view` (workaround; akar masalah = QC-001) |
| QC-042 | Starter prompt semua single-agent | Tambah 2 prompt cross-agent di config JSON |
| QC-049 | Panel penjelasan | **Sudah ada** — tinggal cek cakupan ~40 entri lengkap |
| QC-059 | Tombol reset global | Reset state React + panggil endpoint yang sudah ada |

### 🟡 SEDANG — 31 item

Butuh perhitungan ulang, refactor lintas file, atau fitur baru berukuran terbatas. **Estimasi: 2–3 minggu.**

**Kelompok A — Teks dampak aksi harus dihitung, bukan diketik** (gate #3 di sheet 06B)
| No | Temuan |
|---|---|
| QC-004 | Penundaan pembayaran menggerakkan headroom ke arah salah |
| QC-005 | Headroom dicampur dengan saldo kas |
| QC-016 | Dampak DSO tidak cocok rekomendasinya |
| QC-017 | Aksi gabungan hanya hitung sebagian |
| QC-019 | Credit line berpatokan minggu salah |

> Kelima ini satu akar: teks `impact` ditulis manual di spec. Fix-nya sekali jalan — bikin evaluator yang menurunkan `impact` dari forecast/baseline, lalu render dari situ. Kerjakan sebagai **satu paket**, bukan lima tiket terpisah.

**Kelompok B — Satu angka, satu arti** (gate #6)
| No | Temuan |
|---|---|
| QC-007 | High-risk KPI (2.500) vs grafik tier (5.000) |
| QC-008 | "Top 5" punya 3 definisi berbeda |
| QC-011 | Varians COGS: 2.930 vs 1.880 |
| QC-015 | Split invoice 1.950 di luar total 7.845 |
| QC-040 | Belum jelas forecast sebelum/sesudah penundaan pelanggan |

**Kelompok C — Kualitas logika**
| No | Temuan |
|---|---|
| QC-001 | Kategori Leakage nol semua — mapping kolom amount batch 17 |
| QC-020 | Kunci nama agent tidak konsisten antar endpoint |
| QC-021 | 47 action card duplikatif → rapikan ke 3–5 per agent |
| QC-023 | 47 alert menceritakan ~8 hal → dedup |
| QC-026 | Recovery rate abaikan umur piutang |
| QC-046 | Skor vendor = jumlah flag × 20, abaikan nilai & severity |
| QC-048 | Mockup vs aplikasi beda angka |

**Kelompok D — Fitur baru berukuran sedang**
| No | Temuan | Catatan |
|---|---|---|
| QC-035 | Label periode di setiap grafik | Tambah field ke payload + render di judul |
| QC-051 | Simpan / muat / bandingkan skenario | Butuh tabel baru + UI |
| QC-052 | Preset simulator | 3–4 preset bernama per agent |
| QC-053 | Pemilih cakupan | Pola sudah ada di Finance, tinggal replikasi |
| QC-054 | Sparkline KPI | Komponen sudah ada, tinggal 3 agent emit `trend` |
| QC-055 | Tingkat keyakinan aksi | Kolom DB sudah ada, tinggal ekspos |
| QC-056 | Animasi rantai eksekusi | `RouteRenderer` sudah ada, tambah tahapan |
| QC-057 | Umpan aktivitas agent | Endpoint + panel baru, terpisah dari alert |
| QC-061 | Next best action di dashboard | Data aksi sudah ada, tinggal render di Workboard |

**Kelompok E — Kegagalan uji manual**
| No | Temuan |
|---|---|
| MT-010 | DSO ke 53,5 (harusnya kembali bersih ke 57,36) |
| MT-014 | Approve tidak bisa dibatalkan |
| MT-015 | Agent Action tidak muncul di Action History; `simulation_summary` null |
| MT-023 | Respons lambat (>8 detik) |
| MT-025 | Fitur export/download belum ada |

### 🔴 SUSAH — 10 item

Menyentuh arsitektur data, skema DB, atau integrasi lintas agent. **Estimasi: 4–6 minggu, dan sebagian mustahil tanpa dataset pengganti.**

| No | Temuan | Kenapa susah |
|---|---|---|
| QC-002 | Empat agent di atas 4 batch tidak berhubungan (batch 19/17/11/2) | **Akar dari hampir semua masalah angka.** Butuh single ledger + re-seed + repoint 4 agent |
| QC-003 | Basis pendapatan Collection 15× Finance | Turunan QC-002 — tidak bisa diperbaiki terpisah |
| QC-044 | Volume data jauh di bawah permintaan | Butuh dimensi baru (`legal_entity`, `store`, `item`, `category`) — **belum ada di skema sama sekali**. Butuh migrasi + ETL 25.588 baris sales, 2.016 AR, 630 AP |
| QC-043 | 22 filter tidak ada | Bergantung penuh pada QC-044. Menyentuh setiap endpoint + setiap komponen UI |
| QC-047 | Tuas Treasury tidak terhubung buku Collection | Butuh model simulasi bersama lintas agent. Ini justru **pembeda utama demo**, jadi tetap prioritas |
| QC-022 | Dampak aksi bertumpuk tanpa pengaman double counting | Butuh netting portofolio — model matematis baru |
| QC-010 | Varians harga ~10× lebih kecil dari klaim | Perlu rekonsiliasi ke model dasar. Belum jelas mana yang benar |
| QC-037 | Grafik kas tidak bisa jelaskan kenapa W5 rendah | Butuh 288 baris cash line (hanya ada seri saldo). Bergantung dataset pengganti |
| QC-058 | Pengalih Bahasa Indonesia | i18n penuh: UI strings + payload + **output LLM**. Prompt saat ini justru mengunci English |
| QC-060 | Hitung dengan parameter CFO sendiri | Butuh jembatan chat ↔ simulator + penampil langkah perhitungan |

---

## 3. Rekomendasi urutan pengerjaan

Bukan berdasarkan nomor QC, tapi berdasarkan **rasio dampak/effort**:

**Tahap 0 — sebelum ngoding apa pun** (1 hari)
1. Deploy build terbaru ke Azure, jalankan ulang sheet 02B. Coret temuan yang sudah gugur.
2. Kejar `Dataset_AI_Finance_Forum_v1.xlsx`. Tanpa file ini, cluster 🔴 tidak bisa jalan.

**Tahap 1 — quick wins** (2–3 hari)
Seluruh cluster 🟢. **MT-018 (Decimal JSON) dulu** — itu bug crash. Setelah tahap ini, 5 dari 14 gate di sheet 06B tuntas (gate #4, #5, dan sebagian #6, #7).

**Tahap 2 — dua paket sedang berdampak besar** (1 minggu)
- Kelompok A (teks dampak aksi dihitung) → menutup gate #3
- Kelompok B (satu angka satu arti) → menutup gate #6

Kedua gate ini paling mungkin ketahuan CFO di panggung, dan effort-nya jauh di bawah cluster 🔴.

**Tahap 3 — dataset & arsitektur** (3–4 minggu)
QC-044 → QC-002 → QC-003 → QC-001 → QC-043. Urutan ini wajib berantai; membalik urutannya berarti kerja dua kali.

**Tahap 4 — sisanya**
Fitur sedang kelompok D, lalu QC-047 dan QC-022.

**Saran ditunda ke setelah demo:** QC-058 (i18n), QC-060 (hitung parameter sendiri), QC-037. Ketiganya mahal dan tidak menghalangi cerita demo 4 menit.

---

## 4. Ringkasan angka

| Cluster | Jumlah | Estimasi |
|---|---|---|
| 🟢 Gampang | 24 | 2–3 hari |
| 🟡 Sedang | 31 | 2–3 minggu |
| 🔴 Susah | 10 | 4–6 minggu |
| ✅ Sudah ada / ditutup | 4 | — |

> Total baris di atas melebihi 62 karena 5 kegagalan uji manual (MT) dimasukkan sebagai item kerja tersendiri, dan 4 item "sudah ada" beririsan dengan nomor QC yang di Excel masih berstatus Terbuka.

**Temuan terpenting dari analisis ini:** dari 8 temuan berlabel **Kritis** di Excel, **1 sudah selesai** (QC-049), **1 ditutup** (QC-050), **1 gampang** (QC-006), dan **5 sisanya** (QC-001 s/d QC-005) semuanya berakar pada satu masalah yang sama — dataset terpisah dan teks dampak yang diketik manual. Jadi 8 "kritis" itu praktisnya **2 paket kerja**, bukan 8.
