# Ledgerline Finance Forum — Frontend

Antarmuka chat + dashboard untuk Ledgerline Finance Forum. Dibangun dengan **React 19 + Vite**, dan di-*build* menjadi **satu file** `dist/index.html` (via `vite-plugin-singlefile`) yang disajikan langsung oleh backend FastAPI di `GET /`.

> Untuk rincian lengkap perubahan UI/UX terbaru (latar, keputusan desain, keterbatasan), lihat **[../docs/PRD-Perubahan-UI-UX.md](../docs/PRD-Perubahan-UI-UX.md)**.

---

## Menjalankan

**Mode dev (hot reload):**
```bash
npm install
npm run dev        # http://127.0.0.1:5173, proxy /api -> :8000
```

**Mode produksi (satu file, disajikan backend):**
```bash
npm run build      # menghasilkan dist/index.html
```
Lalu buka **http://127.0.0.1:8000/** (backend harus jalan) dan **hard refresh** (Ctrl+Shift+R).

Backend berjalan terpisah:
```bash
python -m uvicorn main:app --port 8000   # dari root proyek, tanpa --reload
```

---

## Struktur

```
src/
  App.jsx                     Shell 3 kolom: sidebar · Workboard · panel chat
  main.jsx                    Root + MonitoringProvider
  styles.css                  Design token (:root) + seluruh styling
  semanticAccent.jsx          Pewarnaan inline jawaban AI (berbasis frasa)
  api/
    chatStream.js             Streaming chat (SSE)
    dashboard.js              Ambil payload dashboard
    alerts.js                 Alert, actions, monitoring agents
  components/
    Workboard.jsx             KPI (status RAG/progress/sparkline), chart, simulator
    ChatMessage.jsx           Bubble jawaban + blok
    BlockRenderer.jsx         Render blok (html/chart/simulation)
    ChartRenderer.jsx         Chart
    SimulationRenderer.jsx    Hasil simulasi
    ToolCard.jsx              Kartu langkah-kerja tool call
    AlertsPanel.jsx           Lonceng + badge + popover + toast monitoring
    ProblemToasts.jsx         Toast "masalah baru" (pojok kanan atas)
  monitoring/
    MonitoringProvider.jsx    Orkestrasi monitoring + kumpulkan masalah baru
```

---

## Konsep Kunci

### 1. Design token (`styles.css` → `:root`)
Warna, spacing, radius, tipografi, motion, dan shadow didefinisikan sebagai token berlapis: **primitive** (`--blue-500`) → **semantic** (`--accent-info`). **Jangan tulis hex langsung** di aturan komponen — selalu pakai token. Nama variabel lama dipertahankan sebagai alias.

Aksen status yang dipakai di seluruh aplikasi:
- `--accent-info` (biru) = informasi/rekomendasi
- `--accent-success` (hijau) = bagus
- `--accent-danger` (merah) = bahaya
- `--accent-warning` (amber) = hati-hati

### 2. Aksen warna jawaban AI
Dua lapis, sama-sama memakai token di atas:
- **Struktural** — blok dari backend diberi warna berdasarkan kelasnya (`recommendation-block` → biru, `confidence-high/medium/low` → hijau/amber/merah).
- **Inline** (`semanticAccent.jsx`) — frasa di dalam teks diwarnai berdasarkan **makna, bukan kata tunggal** ("high risk" → merah, "high margin" → dibiarkan). Kamus frasa ada di array `RULES`.

### 3. KPI interaktif (`Workboard.jsx`)
Tiap kartu KPI: **rail status RAG** + **progress ke target** + **sparkline** (jika ada data seri asli). Klik kartu → agent diminta **menginterpretasi** KPI itu, jawaban muncul di panel chat. Payload KPI diperkaya di backend (`src/llm/dashboard_payload.py`).

### 4. Notifikasi masalah (`MonitoringProvider.jsx` + `ProblemToasts.jsx`)
Setelah monitoring selesai, alert **baru** (dedupe berbasis isi via localStorage) muncul sebagai toast di pojok kanan atas. Sisanya tetap di lonceng 🔔.

---

## Penyetelan Cepat

| Ingin mengubah | Ubah di |
|---|---|
| Warna brand / status | Token `:root` — `styles.css` |
| Rentang lebar panel chat | `CHAT_WIDTH_MIN/MAX/DEFAULT` — `App.jsx` |
| Kamus frasa aksen | `RULES` — `semanticAccent.jsx` |
| Jumlah / durasi toast masalah | `MAX_PROBLEM_TOASTS` (`MonitoringProvider.jsx`) · timeout (`ProblemToasts.jsx`) |
| Prompt insight KPI | `buildKpiInsightPrompt()` — `App.jsx` |

---

## Catatan

- Setelah build, backend menyajikan `dist/index.html`. Perubahan file `.py` di backend perlu **restart manual** (dijalankan tanpa `--reload`).
- Konvensi warna bersifat semantik — pertahankan makna (biru/hijau/merah/amber) saat menambah komponen baru agar konsisten.
