# PRD / Catatan Perubahan — Peningkatan UI/UX Ledgerline Finance Forum

| | |
|---|---|
| **Judul** | Peningkatan UI/UX chat, dashboard KPI, dan sistem desain |
| **Produk** | Ledgerline Finance Forum (AI Finance Forum Backend) |
| **Branch** | `feat/subagent` |
| **Tanggal** | 25 Juli 2026 |
| **Persona utama** | CFO / tim finance eksekutif |
| **Status** | Selesai diimplementasikan & di-build; verifikasi manual visual disarankan |
| **Ruang lingkup** | Frontend (React + Vite) + 1 perubahan backend (payload dashboard) |

---

## 1. Ringkasan Eksekutif

Dokumen ini merangkum seluruh perubahan UI/UX yang dikerjakan dalam satu sesi terhadap aplikasi chat + dashboard Ledgerline. Tujuan besarnya satu: **membuat produk lebih ramah dan bisa langsung dipahami oleh seorang CFO** — "posisi keuangan saya bagaimana, apa yang berisiko, saya harus melakukan apa".

Perubahan dikelompokkan menjadi 11 fitur, plus satu **fondasi sistem desain (design token)** yang menjadi dasar konsistensi warna di seluruh aplikasi.

Prinsip yang dipegang di sepanjang pengerjaan:
- **Jujur pada data.** Tidak ada angka atau tren yang dikarang. Kalau data historis tidak ada, fitur yang membutuhkannya tidak dipaksakan.
- **Warna itu bermakna, bukan hiasan.** Biru = informasi/rekomendasi, hijau = bagus, merah = bahaya, amber = hati-hati.
- **Konsisten lewat token,** supaya perubahan tema/brand ke depan menjadi murah.

---

## 2. Daftar Isi

1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif)
2. [Daftar Isi](#2-daftar-isi)
3. [Fondasi: Sistem Design Token (Fase 0)](#3-fondasi-sistem-design-token-fase-0)
4. [Fitur 1 — Saran Prompt Gaya Copilot](#4-fitur-1--saran-prompt-gaya-copilot)
5. [Fitur 2 — Panel Chat Bisa Di-resize](#5-fitur-2--panel-chat-bisa-di-resize)
6. [Fitur 3 — Scrollbar Otomatis Sembunyi](#6-fitur-3--scrollbar-otomatis-sembunyi)
7. [Fitur 4 — Textarea Auto-grow](#7-fitur-4--textarea-auto-grow)
8. [Fitur 5 — Notifikasi/Alert Model Triase](#8-fitur-5--notifikasialert-model-triase)
9. [Fitur 6 — Klik KPI Dapat Insight dari Agent](#9-fitur-6--klik-kpi-dapat-insight-dari-agent)
10. [Fitur 7 — Tampilan Tool Call Baru](#10-fitur-7--tampilan-tool-call-baru)
11. [Fitur 8 — Aksen Warna Blok Jawaban AI](#11-fitur-8--aksen-warna-blok-jawaban-ai)
12. [Fitur 9 — Aksen Warna Inline (Berbasis Frasa)](#12-fitur-9--aksen-warna-inline-berbasis-frasa)
13. [Fitur 10 — KPI Status RAG + Progress + Sparkline (Fase 1)](#13-fitur-10--kpi-status-rag--progress--sparkline-fase-1)
14. [Ringkasan File yang Diubah](#14-ringkasan-file-yang-diubah)
15. [Keterbatasan & Pekerjaan Lanjutan](#15-keterbatasan--pekerjaan-lanjutan)
16. [Cara Build & Menjalankan](#16-cara-build--menjalankan)
17. [Panduan Menyetel (Tuning)](#17-panduan-menyetel-tuning)

---

## 3. Fondasi: Sistem Design Token (Fase 0)

### Masalah
File `frontend/src/styles.css` sudah lebih dari 2.700 baris, hanya punya satu tema, dan bercampur antara variabel CSS (`--primary`, `--ink`) dengan ratusan kode warna hex yang ditulis langsung (`#5b5fc7`, `#26344e`, dll). Akibatnya setiap perubahan tampilan jadi mahal dan gampang tidak konsisten.

### Apa yang berubah
Dibangun **token desain berlapis** di bagian `:root` file `styles.css`:

- **Layer 1 — primitive:** ramp warna mentah — `--gray-0..900`, `--blue-50..700`, `--green-*`, `--red-*`, `--amber-*`.
- **Layer 2 — semantic:** makna dari warna — `--surface`, `--ink`, `--line`, `--primary`, dan **accent status**:
  - `--accent-info` (biru) — informasi/rekomendasi
  - `--accent-success` (hijau) — bagus
  - `--accent-danger` (merah) — bahaya/peringatan
  - `--accent-warning` (amber) — hati-hati
  - Masing-masing punya turunan `-soft`, `-border`, `-strong`.
- **Skala pendukung:** spacing (`--space-1..10`), radius (`--radius-sm/md/lg/pill`), tipografi (`--text-xs..xl`), motion (`--ease-standard`, `--dur-fast/base`), dan shadow (`--shadow-sm/md/lg`).

### Poin penting
**Tidak ada regresi visual.** Semua nama variabel lama (`--primary`, `--danger`, `--success`, dst) dipertahankan sebagai **alias** ke token baru dengan nilai warna yang persis sama. Tampilan lama tetap sama, tapi sekarang ada pondasi yang rapi.

### Manfaat ke depan
Dark mode, penggantian brand, atau penyesuaian kepadatan (density) nantinya cukup mengganti nilai token — bukan berburu hex satu per satu.

### File
- `frontend/src/styles.css` (blok `:root`)

---

## 4. Fitur 1 — Saran Prompt Gaya Copilot

### Masalah
Saran prompt sebelumnya berupa tombol lebar penuh yang bertumpuk ke bawah, memakan ruang dan terasa berat.

### Apa yang berubah
Diubah menjadi **chip pill kompak** yang menyusun horizontal (wrap), masing-masing dengan **ikon sparkle** yang berputar halus saat hover. Judulnya adaptif: "Suggested prompts" (awal) / "Suggested follow-ups" (setelah ada percakapan).

### Cara pakai
Klik chip → teksnya masuk ke kotak ketik dan kotak langsung fokus, tinggal Enter atau diedit dulu.

### File
- `frontend/src/App.jsx` (markup chip + komponen `SparkleIcon`)
- `frontend/src/styles.css` (`.prompt-chip`, `.prompt-chip-spark`, dst)

---

## 5. Fitur 2 — Panel Chat Bisa Di-resize

### Masalah
Lebar panel chat tetap; dashboard dan chat saling berebut ruang tanpa bisa disesuaikan pengguna.

### Apa yang berubah
Ditambahkan **pegangan geser (drag handle)** vertikal antara dashboard dan panel chat. Pengguna bisa menarik untuk mengecilkan/membesarkan chat (rentang **320–760 px**). Lebar **disimpan di localStorage**, jadi tetap sama walau halaman di-refresh.

### Aksesibilitas
Pegangan bisa difokus dengan keyboard; **panah kiri/kanan** untuk menyesuaikan (Shift = langkah besar). Otomatis disembunyikan di layar sempit (mode responsif).

### Detail teknis
Grid `app-shell` diubah menjadi 4 kolom dengan kolom chat memakai variabel `--chat-width`. Nilai lebar dikontrol state React dan disimpan lewat key `ledgerline.chatWidth`.

### File
- `frontend/src/App.jsx` (state `chatWidth`, fungsi `startResize`/`handleResizeKey`, elemen handle)
- `frontend/src/styles.css` (`.chat-resize-handle`, grid `.app-shell`)

---

## 6. Fitur 3 — Scrollbar Otomatis Sembunyi

### Masalah
Scrollbar selalu tampil dan mengganggu tampilan bersih.

### Apa yang berubah
Scrollbar di **area pesan (transcript)** dan **kotak ketik** kini **tersembunyi secara default** dan **muncul hanya saat sedang di-scroll** (memudar sendiri ± 0,9 detik setelah berhenti) atau saat kursor hover di area tersebut. Lebar track tetap "dipesan" sehingga konten tidak bergeser saat bar muncul/hilang.

### Detail teknis
Kelas `is-scrolling` ditoggle lewat event `scroll` di JavaScript; styling memakai `scrollbar-color` (Firefox) dan `::-webkit-scrollbar` (Chrome/Edge).

### File
- `frontend/src/App.jsx` (effect toggle `is-scrolling`)
- `frontend/src/styles.css` (aturan scrollbar `.transcript`, `.composer textarea`)

---

## 7. Fitur 4 — Textarea Auto-grow

### Masalah
Saat saran diklik dan teksnya panjang, kotak ketik memotong teks dan memunculkan panah scroll bawaan browser yang jelek.

### Apa yang berubah
Kotak ketik kini **otomatis menyesuaikan tinggi** mengikuti isi (sampai maksimum ± 168 px, baru muncul scrollbar). Panah resize bawaan dihapus (`resize: none`). Reset ke tinggi minimal saat ganti agent atau clear chat.

### File
- `frontend/src/App.jsx` (`composerRef` + effect auto-grow)
- `frontend/src/styles.css` (`.composer textarea`)

---

## 8. Fitur 5 — Notifikasi/Alert Model Triase

### Masalah
Notifikasi alert tampil sebagai daftar yang mengembang penuh di atas dashboard, mendorong KPI eksekutif ke bawah dan terasa sangat mengganggu.

### Apa yang berubah
Diterapkan **model triase** — tidak semua alert diperlakukan sama:

- **Lonceng 🔔 + badge jumlah** di toolbar. Semua alert "pindah rumah" ke sini. Klik lonceng → **popover** berisi daftar alert. Dashboard jadi lega.
- **Status monitoring** (sedang berjalan / selesai / error) menjadi **toast di pojok kanan bawah yang hilang sendiri** (4 detik untuk selesai, 7 detik untuk error) — tidak lagi memblok dashboard.
- Popover bisa ditutup dengan **Esc** atau klik di luar.

### Catatan kejujuran
Rencana awal menyertakan "banner tipis khusus alert critical". Ternyata di data saat ini **alert tidak punya field severity** (semua di-hardcode "High" di renderer). Kalau dipaksakan, banner "critical" akan muncul untuk **setiap** alert dan kembali membuat sesak. Maka keputusan yang diambil: **semua alert ke lonceng, status ke toast, tanpa banner permanen** — ini paling menuntaskan keluhan. Hook warnanya sudah siap bila severity asli ditambahkan nanti.

### File
- `frontend/src/components/AlertsPanel.jsx` (lonceng, badge, popover, toast; komponen `BellIcon`)
- `frontend/src/styles.css` (`.alerts-bell`, `.alerts-popover`, `.monitoring-toast`, dst)

---

## 9. Fitur 6 — Klik KPI Dapat Insight dari Agent

### Masalah
Kartu KPI di atas (mis. "EBITDA MARGIN 9.2% target 15%") hanya berfungsi mengganti view chart. CFO tidak dapat penjelasan **mengapa** angkanya seperti itu.

### Apa yang berubah
Klik kartu KPI kini **meminta agent (yang berjalan dengan subagents) untuk menginterpretasi KPI tersebut**: mengapa berada di level ini, apa pendorongnya, dan tindakan apa yang perlu dipertimbangkan. Jawaban muncul streaming di panel chat lengkap dengan tabel/chart dan saran lanjutan.

Kartu juga mendapat penanda **"✨ Insight"** yang muncul saat hover, agar jelas kartu bisa diklik untuk itu.

### Detail teknis
**Tanpa perubahan backend.** Memakai ulang pipeline chat `/api/html/chat` yang sudah ada. Fungsi `submitText()` di `App.jsx` dipisah agar bisa dipanggil secara programatik, lalu `askKpiInsight()` menyusun prompt dari data KPI (`buildKpiInsightPrompt`).

Alur terverifikasi lewat API: `status → tool_call → tool_result → assistant_response → suggestions → done`.

### Catatan
Setiap klik KPI = satu panggilan LLM sungguhan (ada biaya & latensi wajar).

### File
- `frontend/src/App.jsx` (`submitText`, `askKpiInsight`, `buildKpiInsightPrompt`, prop `onAskInsight`)
- `frontend/src/components/Workboard.jsx` (handler klik KPI, komponen `SparkIcon`)

---

## 10. Fitur 7 — Tampilan Tool Call Baru

### Masalah
Langkah "tool call" saat agent bekerja ditampilkan sebagai **dump JSON mentah** di dalam `<pre>` — sulit dibaca dan membuat chat berantakan.

### Apa yang berubah
Dirombak menjadi **kartu langkah-kerja yang manusiawi**:

- Ikon + kalimat kerja ramah per tool ("🔎 Queried the data", "📊 Analyzed performance", "🧮 Ran a scenario", dst) menggantikan nama teknis mentah.
- Chip status: **Working** (dengan spinner) / **Done** (✓).
- Tertutup secara default. Saat dibuka: **input ditampilkan sebagai pill** (`Key: value`) dan **hasil diringkas dalam bahasa manusia** ("Returned 12 rows").
- Data mentah tetap tersedia, tapi disembunyikan di balik tombol **"View raw data"**.

### File
- `frontend/src/components/ToolCard.jsx` (ditulis ulang sepenuhnya)
- `frontend/src/styles.css` (`.tool-step` dan turunannya)

---

## 11. Fitur 8 — Aksen Warna Blok Jawaban AI

### Masalah
Jawaban AI tampil netral; CFO harus membaca teliti untuk menangkap intinya.

### Apa yang berubah
Aksen warna **berbasis struktur** — menempel pada kelas HTML nyata yang di-emit renderer backend (`src/llm/html_renderer.py`), bukan tebakan:

| Elemen | Warna | Kondisi |
|---|---|---|
| Jawaban AI (default) | 🔵 rail biru di kiri | tiap jawaban assistant |
| Blok **rekomendasi** | 🔵 biru (border + tint + judul) | kelas `recommendation-block` |
| Confidence **High** | 🟢 hijau | `confidence-high` |
| Confidence **Medium** | 🟡 amber | `confidence-medium` |
| Confidence **Low** | 🔴 merah | `confidence-low` |
| Pesan **error** | 🔴 rail merah | turn error |

Terverifikasi: agent memang mengeluarkan `recommendation-block`, `confidence-high`, dan `confidence-medium` pada respons uji.

### File
- `frontend/src/styles.css` (`.recommendation-block`, `.confidence-*`, rail `.message.assistant`)

---

## 12. Fitur 9 — Aksen Warna Inline (Berbasis Frasa)

### Masalah
Aksen di Fitur 8 hanya menyentuh blok terstruktur. Diinginkan warna juga **merata ke teks jawaban** — misal kata yang merujuk bahaya jadi merah, yang bagus jadi hijau.

### Apa yang berubah
Ditambahkan **pewarnaan inline berbasis frasa** di seluruh teks jawaban AI:

- 🔴 **Merah** — `high risk`, `at risk`, `overdue`, `below target`, `shortfall`, `leakage`, `fraud`, `breach`, `declining`, dll.
- 🟢 **Hijau** — `on track`, `above target`, `high confidence`, `healthy`, `recovered`, `mitigated`, `ahead of plan`, dll.
- 🟡 **Amber** — `moderate`, `near target`, `medium confidence`, `marginal`, dll.

### Keputusan desain penting
Pewarnaan **berbasis frasa, bukan kata tunggal**, karena polaritas bergantung konteks. Kata "high" sendiri ambigu: **"high risk"** (bahaya) vs **"high margin"** (bagus). Kalau diwarnai per kata, "high margin" ikut merah dan malah menyesatkan CFO.

Terverifikasi lewat uji matcher:
```
"...high margin but ... high risk and is overdue"
  → "high risk" → merah, "overdue" → merah   ("high margin" DIABAIKAN)
"on track and above target with high confidence"
  → semuanya hijau
```

Styling dibuat subtle (warna + tebal, tanpa background) agar tetap enak dibaca. Pesan pengguna **tidak** diwarnai (agar jelas mana input, mana jawaban). Berlaku di teks bubble maupun blok HTML dari backend.

### File
- `frontend/src/semanticAccent.jsx` (**file baru** — kamus frasa + fungsi `accentPlain` / `accentHtml`)
- `frontend/src/components/ChatMessage.jsx` (menerapkan `accentPlain` pada teks AI)
- `frontend/src/components/BlockRenderer.jsx` (menerapkan `accentHtml` pada blok HTML)
- `frontend/src/styles.css` (`.sem-danger`, `.sem-good`, `.sem-warn`)

---

## 13. Fitur 10 — KPI Status RAG + Progress + Sparkline (Fase 1)

### Masalah
Kartu KPI hanya menampilkan angka. CFO tidak bisa langsung menilai status (sehat/bahaya) atau posisinya terhadap target dalam sekali pandang.

### Apa yang berubah

**a. Status RAG (merah/amber/hijau)**
Setiap kartu KPI kini punya **rail warna di kiri + titik status**: 🟢 good, 🟡 warn, 🔴 bad. Dihitung di backend dari arah "bagus" yang sudah benar per-KPI (flag `alert`), plus band tiga-tingkat eksplisit untuk EBITDA margin.
Terverifikasi: EBITDA margin → **bad** (9.2% jauh di bawah 15%), KPI lain → **good**.

**b. Progress ke target**
Bar tipis di bawah nilai untuk KPI yang punya target. Terverifikasi: margin **progress 0.61** (9.2 dari 15) — langsung terlihat "baru 61% menuju target". Warnanya ikut status.

**c. Sparkline (grafik mini tren)**
Komponen SVG kecil (garis + area + titik akhir), warna ikut status.
**Catatan kejujuran penting:** sparkline butuh **data historis time-series**, sementara snapshot backend umumnya hanya titik saat ini. Maka **tren tidak dikarang**. Sparkline hanya menyala di tempat yang punya seri asli: **Week 5 cash (Treasury)** — memakai 13 titik closing cash mingguan yang nyata. Kartu lain menampilkan progress bar, bukan sparkline palsu.

### Detail teknis
Payload KPI diperkaya di backend: field `status`, `value_num`, `target_num`, `progress`, dan `trend`. Diproses lewat helper `_enrich_kpis()` yang dipanggil terpusat di `build_dashboard()`.

### File
- `src/llm/dashboard_payload.py` (**satu-satunya perubahan backend** — `_enrich_kpis`, `_parse_num`, `_parse_target`; status margin finance; trend Week-5 treasury)
- `frontend/src/components/Workboard.jsx` (status/dot/progress/sparkline + komponen `KpiSparkline`)
- `frontend/src/styles.css` (`.kpi-tile.status-*`, `.kpi-progress`, `.kpi-spark`)

---

## 14. Ringkasan File yang Diubah

### Frontend
| File | Perubahan |
|---|---|
| `frontend/src/App.jsx` | Chip saran, resize panel, auto-hide scrollbar, textarea auto-grow, `submitText`/`askKpiInsight` |
| `frontend/src/components/Workboard.jsx` | Klik KPI → insight, status RAG, progress, sparkline |
| `frontend/src/components/AlertsPanel.jsx` | Lonceng + badge + popover, toast monitoring |
| `frontend/src/components/ToolCard.jsx` | Ditulis ulang — kartu langkah-kerja |
| `frontend/src/components/ChatMessage.jsx` | Aksen inline pada teks AI |
| `frontend/src/components/BlockRenderer.jsx` | Aksen inline pada blok HTML |
| `frontend/src/semanticAccent.jsx` | **Baru** — mesin aksen berbasis frasa |
| `frontend/src/styles.css` | Design token + seluruh styling fitur di atas |

### Backend
| File | Perubahan |
|---|---|
| `src/llm/dashboard_payload.py` | Perkaya payload KPI (status/target/progress/trend) |

---

## 15. Keterbatasan & Pekerjaan Lanjutan

- **Sistem token belum "bersih total".** Pondasi token sudah lengkap dan fitur baru memakainya, tetapi masih banyak hex lama di ~2.700 baris CSS. Migrasi penuh adalah pekerjaan mekanis besar yang sengaja tidak dihajar sekaligus (risiko regresi) — bisa dilanjutkan bertahap dengan aman.
- **Sparkline belum merata.** Hanya Treasury (Week 5) yang punya data seri asli. Agar menyala di semua KPI diperlukan **penyimpanan histori KPI antar-waktu** di database + endpoint pengambil serinya (kandidat Fase 2). Komponennya sudah siap: begitu ada field `trend`, kartu langsung menampilkan sparkline.
- **Aksen inline bersifat heuristik** (kamus frasa), bukan pemahaman makna sebenarnya. Akurat untuk istilah finansial umum, tapi kalimat yang berputar bisa terlewat/salah warna sesekali. Versi paling robust: agent/LLM **menandai sendiri** span berisiko/positif saat generate (perubahan backend/prompt, Fase 2).
- **Severity alert belum nyata.** Warna merah pada notifikasi saat ini hanya lewat confidence-low + error. Callout peringatan eksplisit butuh tipe blok baru di renderer backend (Fase 2).
- **Band amber KPI** belum terlihat di data saat ini karena kebetulan tidak ada nilai yang jatuh di rentang warn — warnanya sudah siap.
- **Verifikasi visual manual** disarankan: build, payload, dan logika sudah diverifikasi lewat API/uji unit sederhana, tetapi rendering warna/interaksi sebaiknya dilihat langsung di browser.

---

## 16. Cara Build & Menjalankan

**Backend** (dari root proyek):
```powershell
python -m uvicorn main:app --port 8000
```
> Jalankan tanpa `--reload` untuk menghindari `WinError 10013` (port ditahan worker lama). File `.env` perlu berisi kredensial DATABASE_URL dan AZURE_OPENAI_* yang valid.

**Frontend** (produksi, satu file):
```powershell
cd frontend
npm install
npm run build
```
Menghasilkan `frontend/dist/index.html` yang disajikan FastAPI di `GET /`.

Buka **http://127.0.0.1:8000/** lalu **hard refresh** (Ctrl+Shift+R) agar cache lama tertimpa.

> Catatan: sesudah mengubah file Python (mis. `dashboard_payload.py`), backend perlu **direstart manual** karena dijalankan tanpa `--reload`.

---

## 17. Panduan Menyetel (Tuning)

| Ingin mengubah | Ubah di |
|---|---|
| Warna brand / status | Token di `:root` — `frontend/src/styles.css` |
| Rentang lebar panel chat | Konstanta `CHAT_WIDTH_MIN/MAX/DEFAULT` — `frontend/src/App.jsx` |
| Kamus frasa aksen (tambah istilah) | Array `RULES` — `frontend/src/semanticAccent.jsx` |
| Ambang status RAG EBITDA margin | Blok `"status"` KPI margin — `src/llm/dashboard_payload.py` |
| Durasi toast monitoring | Timeout di `AlertsPanel.jsx` (4000 / 7000 ms) |
| Prompt insight KPI | `buildKpiInsightPrompt()` — `frontend/src/App.jsx` |

---

*Dokumen ini dibuat berdasarkan perubahan nyata pada branch `feat/subagent`. Untuk arsitektur agent, lihat `AGENTS.md`; untuk gambaran proyek, lihat `README.md`.*
