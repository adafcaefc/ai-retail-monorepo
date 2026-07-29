# Status Pengerjaan UI Uplift

Ringkasan uplift UI frontend: apa yang diminta, apa yang diperbaiki, dan
bagaimana cara memverifikasinya.

**Tanggal:** 28 Juli 2026
**Branch:** `main` (belum di-commit)
**Build:** `npm run build` di `frontend/` — lulus, tidak ada error.

---

## Ringkasan

| # | Permintaan | Status |
|---|---|---|
| 1 | Sidebar kiri bisa open/close | ✅ Selesai |
| 2 | Logo EY di pojok kiri header | ✅ Selesai |
| 3 | Warna abu-abu EY untuk header & sidebar | ✅ Selesai |
| 4 | Skeleton loading (analyzing, re-simulate, agent list) | ✅ Selesai |
| 5 | Sidebar kiri & kanan ditempel (tidak floating) | ✅ Selesai |
| 6 | Chat assistant dikembalikan terang | ✅ Selesai |
| 7 | Donut "Imported COGS share" tidak lagi tertutup label | ✅ Selesai |
| 8 | Header digabung jadi satu | ✅ Selesai |
| 9 | Bug tumpang tindih saat zoom in | ✅ Selesai |
| 10 | Warna toolbar di header disesuaikan | ✅ Selesai |

Semua permintaan selesai.

---

## 1. Sidebar kiri bisa dibuka/ditutup

- Tombol hamburger di pojok kiri header.
- Saat ditutup, kolom grid-nya **dilepas total** (bukan sekadar `width: 0`),
  jadi dashboard memakai lebar penuh tanpa menyisakan gap.
- Pilihan tersimpan di `localStorage` (`ledgerline.sidebarOpen`).

Berkas: `frontend/src/App.jsx`, `frontend/src/components/AppTopbar.jsx`

## 2. Logo EY

- Memakai file asli **tanpa diubah, di-crop, atau digambar ulang**.
- Sumber: `Pictures/Screenshots/Screenshot 2026-07-28 150337.png`
  → disalin ke `frontend/src/assets/ey-logo.png` (84×90, background `#28282f`).
- Di-inline Vite sebagai data-URI, jadi build single-file tetap utuh.
- Padding bawaan gambar (~18% kiri, ~13% kanan) dikompensasi lewat CSS
  (`margin-left: -9px; margin-right: -7px`) — **file gambarnya tidak disentuh**.

Berkas: `frontend/src/components/EyLogo.jsx`

## 3. Warna EY

- Warna diambil langsung dari PNG logo: `#28282f`.
- Blok brand di header dan sidebar kiri memakai warna yang sama persis, jadi
  keduanya terbaca sebagai satu kolom gelap menerus dan tepi tile logo tidak
  kelihatan.
- Aksen kuning EY `#FFE600`.

Token: `--ey-black`, `--ey-gray`, `--ey-gray-raised`, `--ey-gray-hover`,
`--ey-yellow` di `frontend/src/styles.css`.

## 4. Skeleton loading (bukan spinner)

Berkas baru: `frontend/src/components/Skeleton.jsx`

Dipakai di:

- Dashboard loading → `DashboardSkeleton` (KPI + panel + what-if bar)
- Re-simulate → `WhatIfStatsSkeleton` + `WhatIfGaugeSkeleton`
- Agent list saat folder dibuka → `AgentListSkeleton`
- Chat "analyzing" → `ThinkingSkeleton`
- Alerts / Subagents / Audit History → `ListSkeleton`

Tombol *Calculate simulation* memakai sapuan shimmer, bukan ring spinner.
CSS spinner lama yang sudah tidak terpakai dihapus.

## 5. Sidebar ditempel, bukan floating

- `.app-body` sekarang `gap: 0; padding: 0`.
- Panel: `border-radius: 0`, tanpa `box-shadow`; dipisah garis rambut
  (`border-right` / `border-left`).

## 6. Chat assistant kembali terang

Seluruh override gelap `.chat-panel` dihapus. Chat drawer kembali ke palet
terang seperti semula; hanya sidebar kiri yang gelap.

## 7. Donut "Imported COGS share"

**Akar masalah:** label Recharts ditempatkan **di luar** radius pie, jadi di
kartu samping yang pendek label itu keluar dari kartu dan menutupi elemen di
bawahnya. Guard `size.mode !== "compact"` juga tidak pernah aktif karena
varian `compact` mengembalikan `mode: "fill"`.

**Perbaikan:**
- Nama slice pindah ke **legend** di bawah chart.
- Persentase digambar **di dalam** slice (`PieSliceLabel`), jadi secara
  konstruksi tidak mungkin keluar kartu.
- Slice < 8% dilewati agar tidak berdesakan.

Diverifikasi: donut merender `62%`, `24%`, `14%` di dalam ring + legend
`COGS / Opex / Other`.

Berkas: `frontend/src/components/ChartRenderer.jsx`

## 8. Header digabung jadi satu

- Judul "Ledgerline Finance Forum" **dihapus**, diganti judul board sesuai
  agent aktif: `<Agent> dashboard` / `<Agent> performance board`.
- Toolbar (Agent Action, Recalculate, Subagents, Audit History, lonceng,
  Ask `<Agent>`) **dipindah ke header atas**. Baris header kedua di dalam
  dashboard dihapus sepenuhnya.
- Warna header tetap terang; hanya blok EY di kiri yang gelap.
- Blok EY selebar rail sidebar, jadi header dan sidebar sejajar.
- Tinggi tombol toolbar dinaikkan 28px → 34px (ergonomi klik).

Perubahan struktur:
- `AlertsPanel` dipindah dari `Workboard` ke `AppTopbar` (via `children`).
- `Workboard` sekarang murni merender data (grid 3 baris, bukan 4).

---

## 9. Tumpang tindih saat zoom in

Ada **dua bug terpisah**. Keduanya diverifikasi lewat pengukuran DOM, bukan
tebakan — dugaan awal ("jumlah track grid tidak cocok dengan jumlah anak")
ternyata salah.

### Bug 9a — container query tidak pernah aktif

`.workboard` mendeklarasikan dirinya sendiri sebagai container
(`container-type: inline-size; container-name: board`), lalu blok
`@container board (max-width: 860px)` mencoba menyetel
`.workboard { grid-template-rows: ... }`.

**Sebuah elemen tidak pernah cocok dengan container query-nya sendiri — hanya
keturunannya yang bisa.** Jadi aturan itu diam-diam tidak berefek sama sekali,
sementara aturan lain di blok yang sama (`.workboard-mid`, `.side-col`, dst)
tetap jalan karena mereka keturunan.

Pengukuran sebelum perbaikan pada 960×540:

```
gridTemplateRows = 230px 240px 518px          <- track tengah terkunci 240px
mid children: focus-card(h=250)  side-col(h=250)   <- butuh 250+10+250 = 510px
=> meluber 270px menimpa .whatif-bar
```

Diperparah oleh perbaikan saya sebelumnya: `minmax(240px, 1fr)` mengganti
lantai otomatis grid dengan angka mati 240px, yang jauh lebih pendek dari
tinggi isi sebenarnya begitu panel menumpuk.

**Perbaikan:**

```css
.workboard {
  grid-template-rows: auto minmax(min-content, 1fr) auto;
}
```

`min-content` mengembalikan lantai yang mengikuti tinggi isi nyata di setiap
breakpoint, sementara `1fr` tetap menyerap sisa ruang saat ada. Aturan mati di
dalam blok `@container` dihapus dan diberi komentar penjelasan supaya jebakan
yang sama tidak terulang.

Sesudah perbaikan: `gridTemplateRows = 230px 690px 518px` (690 = 250 + 10 +
430, persis tinggi isinya).

### Bug 9b — urutan media query terbalik

`@media (max-width: 1200px)` berada **setelah** blok `max-width: 760px` di
dalam berkas. Pada lebar 700px keduanya cocok, dan karena spesifisitasnya sama,
yang belakangan menang. Akibatnya rail tetap 180px (layout desktop) sementara
`.agent-list` sudah memakai grid strip 4 kolom (293px) → meluber 113px.

**Perbaikan:** beri batas atas eksplisit —
`@media (max-width: 1200px) and (min-width: 761px)`.

Sesudah perbaikan pada 700×600: `app-body cols = 680px` (satu kolom),
`agent-list cols = 158.5px ×4` — pas.

Selain itu `.chat-header` diberi padding/gap yang bisa mengecil (`clamp()`) dan
`min-width: 0` pada sisi judul, agar tombol aksinya tidak mendorong header
keluar drawer.

### Hasil uji

Uji otomatis mendeteksi irisan bounding box antar kartu, elemen yang meluber
dari kontainernya, dan scroll horizontal halaman.
**26 kombinasi lulus semua** (13 ukuran × chat buka/tutup):

```
1920x1080  1600x900  1440x900  1280x720  1097x617  1024x768  960x540
853x480    768x432   700x600   640x480   560x700   420x760
```

---

## 10. Warna toolbar header

Toolbar memakai palet EY, bukan biru bawaan. Kuning disimpan untuk **satu**
aksi saja supaya tetap bermakna.

| Elemen | Sebelum | Sesudah |
|---|---|---|
| `Agent Action` | pill biru | pill kuning `#FFE600` + teks `#28282f` |
| `Ask <Agent>` | pill biru | pill gelap `#28282f` + teks putih; jadi kuning saat chat aktif |
| Recalculate / Subagents / Audit History | outline abu | outline abu, hover → tepi kuning + latar `#fffbe0` |
| Badge `Subagents` | ungu `#5b5fc7` | gelap `#28282f` + teks putih |
| Kicker `Finance dashboard` | biru | abu-abu muted, huruf kapital kecil |

Kontras `#28282f` di atas `#FFE600` ≈ 11:1 (lolos WCAG AAA).

Semua aturan diberi prefiks `.topbar-main` supaya warnanya tidak bocor ke
tombol serupa di dalam modal atau panel chat.

---

## Bug lain yang ditemukan & diperbaiki di sepanjang jalan

| Bug | Sebab | Perbaikan |
|---|---|---|
| Panel chart **menimpa** what-if simulator pada layout normal | Baris grid `minmax(0, 1fr)` mengecil jadi 0px | lihat item 9a |
| Bubble chat & tool card **keluar** panel sampai 165px | Track grid `auto` memakai lebar min-content baris terlebar | `minmax(0, 1fr)` + `min-width: 0` pada `li` |
| Chart gepeng saat drawer chat dibuka | Media query pakai lebar *viewport*, bukan lebar *board* | `@container` query pada `.workboard` |
| Judul chat mendorong transkrip ke bawah | `h1` tanpa batas baris | `-webkit-line-clamp: 2` |

---

## Cara verifikasi

Backend asli (PostgreSQL + FastAPI) tidak diperlukan untuk memeriksa UI.

```bash
cd frontend
npm run build      # harus lulus tanpa error
npm run dev        # atau jalankan dev server dengan backend asli
```

Yang perlu dicek manual:

1. Zoom browser 100% → 200% → pastikan tidak ada kartu yang saling menimpa;
   dashboard boleh discroll, tapi tidak boleh terpotong.
2. Buka/tutup drawer chat pada tiap level zoom.
3. Buka/tutup sidebar lewat tombol hamburger.
4. Klik *Calculate simulation* → skeleton muncul, bukan spinner.
5. Buka/tutup folder agent di sidebar → skeleton baris agent muncul sebentar.
6. Cek donut "Imported COGS share" / "Cost mix" → persentase di dalam ring,
   nama di legend, tidak ada teks yang keluar kartu.

---

## Berkas yang berubah

**Baru**

```
frontend/src/assets/ey-logo.png
frontend/src/components/AppTopbar.jsx
frontend/src/components/EyLogo.jsx
frontend/src/components/Skeleton.jsx
```

**Dimodifikasi**

```
frontend/src/App.jsx
frontend/src/components/AlertsPanel.jsx
frontend/src/components/ChartRenderer.jsx
frontend/src/components/ChatMessage.jsx
frontend/src/components/Workboard.jsx
frontend/src/styles.css
```

Belum ada yang di-commit.

---

## Catatan

- Verifikasi visual memakai **backend tiruan**, bukan API asli — PostgreSQL /
  FastAPI tidak jalan di sesi ini. Angka pada screenshot uji adalah data dummy.
- Terpisah dari pekerjaan ini: backend di `localhost:8000` sempat terlihat
  membalas 500/503 untuk `/api/html/conversations`,
  `/api/html/dashboard/finance.finance`, dan `/api/alerts`. Perubahan UI ini
  tidak menyentuh backend.
