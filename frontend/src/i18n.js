// QC-058: Bahasa Indonesia toggle.
//
// The board's wording comes from two places: the React components, and the
// dashboard payload the agents build in Python. Rather than thread a locale
// through the backend, the payload is translated once when it arrives
// (`translatePayload`) and the components use `t()`.
//
// Lookup is by exact English string. Anything absent renders in English, which
// keeps a missing entry a visibly untranslated label rather than a blank one
// or a crash.
//
// A figure's magnitude is never touched by language — 53,685.5 and 53.685,5
// name the same EBITDA. What does move with the toggle is the separator
// convention (comma/period roles swap) and the "mn" -> "juta" unit word;
// see format.js. That happens on the number the payload already carries
// (`value_num`, `delta_num`), not through this dictionary.

export const LANGUAGES = [
  { id: "en", label: "EN", title: "English" },
  { id: "id", label: "ID", title: "Bahasa Indonesia" },
];

export const DEFAULT_LANGUAGE = "en";

// Component-authored wording.
const CHROME = {
  "What-if simulator": "Simulator what-if",
  Presets: "Preset",
  "All levers together": "Semua tuas sekaligus",
  Levers: "Tuas",
  "Calculate simulation": "Hitung simulasi",
  "Running scenario…": "Menjalankan skenario…",
  "Reset to baseline": "Kembali ke baseline",
  All: "Semua",
  "All lines": "Semua lini",
  "FX lines": "Lini FX",
  "No view data.": "Tidak ada data tampilan.",
  "No rows match the current filter.":
    "Tidak ada baris yang cocok dengan filter saat ini.",
  Others: "Lainnya",

  // Demand Forecasting dashboard.
  "Demand forecast filters": "Filter proyeksi permintaan",
  "All verticals": "Semua vertikal",
  Category: "Kategori",
  Store: "Toko",
  "All stores": "Semua toko",
  Horizon: "Horizon",
  "SKU search": "Pencarian SKU",
  "Search SKU or item": "Cari SKU atau barang",
  Search: "Cari",
  Refresh: "Muat ulang",
  "Refreshing…": "Memuat ulang…",
  Clear: "Hapus",
  Retry: "Coba lagi",
  "Synthetic data": "Data sintetis",
  "Live data": "Data langsung",
  Scope: "Cakupan",
  "All retail demand": "Semua permintaan retail",
  "Clear all": "Hapus semua",
  "Demand forecast summary": "Ringkasan proyeksi permintaan",
  "Forecast (next 7d)": "Proyeksi (7 hari berikutnya)",
  "Forecast accuracy": "Akurasi proyeksi",
  "Demand trend": "Tren permintaan",
  "Stockout-risk SKUs": "SKU berisiko kehabisan stok",
  "Predicted to trend": "Diprediksi menjadi tren",
  "Seasonality index": "Indeks musiman",
  units: "unit",
  "AI demand signal": "Sinyal permintaan AI",
  "8-week backtest": "Uji balik 8 minggu",
  "next 7d vs prior 7d": "7 hari berikutnya vs 7 hari sebelumnya",
  "position below ROP": "posisi di bawah ROP",
  "viral and growth signals": "sinyal viral dan pertumbuhan",
  "100 = average month": "100 = bulan rata-rata",
  "Demand outlook": "Prospek permintaan",
  "Demand forecast — actual vs AI": "Proyeksi permintaan — aktual vs AI",
  "Demand forecast · actual vs AI": "Proyeksi permintaan · aktual vs AI",
  "Forecast period": "Periode proyeksi",
  Daily: "Harian",
  Weekly: "Mingguan",
  Monthly: "Bulanan",
  Quarterly: "Triwulanan",
  Yearly: "Tahunan",
  Actual: "Aktual",
  "AI Forecast": "Proyeksi AI",
  Confidence: "Keyakinan",
  "Confidence band": "Rentang keyakinan",
  "Forecast starts": "Proyeksi dimulai",
  "Demand forecast overview chart": "Grafik ringkasan proyeksi permintaan",
  "Forecast confidence": "Keyakinan proyeksi",
  "Demand forecast confidence chart": "Grafik keyakinan proyeksi permintaan",
  "Emerging demand": "Permintaan yang berkembang",
  "Top items by expected demand uplift": "Barang teratas menurut perkiraan kenaikan permintaan",
  "Predicted-to-trend ranking chart": "Grafik peringkat prediksi tren",
  "Predicted uplift": "Perkiraan kenaikan",
  "units/day": "unit/hari",
  viral: "viral",
  growth: "pertumbuhan",
  seasonal: "musiman",
  promo: "promo",
  stable: "stabil",
  "SKU-level view": "Tampilan tingkat SKU",
  "Forecast detail": "Detail proyeksi",
  "Sorted by": "Diurutkan berdasarkan",
  "Sort by": "Urutkan berdasarkan",
  ascending: "menaik",
  descending: "menurun",
  "Sorted by forecast descending": "Diurutkan dari proyeksi tertinggi",
  matches: "hasil",
  SKU: "SKU",
  Forecast: "Proyeksi",
  Trend: "Tren",
  Signals: "Sinyal",
  "Supply state": "Status pasokan",
  Healthy: "Sehat",
  Low: "Rendah",
  Stockout: "Kehabisan stok",
  "No SKUs match the current scope.": "Tidak ada SKU yang cocok dengan cakupan saat ini.",
  "No trending items match the current scope.": "Tidak ada barang tren yang cocok dengan cakupan saat ini.",
  "Demand Forecasting dashboard": "Dasbor Proyeksi Permintaan",
  "Unable to load Demand Forecasting.": "Tidak dapat memuat Proyeksi Permintaan.",
  "Demand forecast dimensions": "Dimensi proyeksi permintaan",
  "Demand dimensions": "Dimensi permintaan",
  "Forecast by category": "Proyeksi per kategori",
  "Forecast by store": "Proyeksi per toko",
  "Forecast by cluster": "Proyeksi per cluster",
  "Next 7d forecast · Select a category to update the Demand scope": "Proyeksi 7 hari · Pilih kategori untuk memperbarui cakupan Demand",
  "Next 7d forecast · Highest forecast first": "Proyeksi 7 hari · Proyeksi tertinggi lebih dahulu",
  "Next 7d forecast · Top 20 · Select a category to update the Demand scope": "Proyeksi 7 hari · 20 teratas · Pilih kategori untuk memperbarui cakupan Demand",
  "Next 7d forecast · Top 20 highest forecast": "Proyeksi 7 hari · 20 proyeksi tertinggi",
  "Next 7d forecast · Flagship · Mall · Community · Express": "Proyeksi 7 hari · Flagship · Mall · Community · Express",
  "Next 7d forecast · Current Demand scope": "Proyeksi 7 hari · Cakupan Demand saat ini",
  "Seasonality curve (12 mo)": "Kurva musiman (12 bulan)",
  "By legal entity": "Per entitas hukum",
  "Forecast units": "Unit proyeksi",
  Stores: "Toko",
  stores: "toko",
  Cluster: "Cluster",
  Share: "Porsi",
  "Current mock month": "Bulan mock saat ini",
  "Chain Total": "Total chain",
  "Frontend scenario calculation": "Perhitungan skenario frontend",
  "What-If Simulator": "Simulator What-If",
  "Baseline versus scenario · browser calculation over dashboard data": "Baseline versus skenario · perhitungan browser atas data dashboard",
  Run: "Jalankan",
  "Running…": "Menjalankan…",
  Save: "Simpan",
  Load: "Muat",
  Reset: "Reset",
  "No saved scenarios yet": "Belum ada skenario tersimpan",
  "What-If scenario applied": "Skenario What-If diterapkan",
  "Clear applied scenario": "Hapus skenario yang diterapkan",
  "Levers drive whole page": "Lever menggerakkan seluruh halaman",
  "Demand shift": "Perubahan permintaan",
  "Promo intensity": "Intensitas promo",
  "Markdown depth": "Kedalaman markdown",
  "Extra inbound": "Inbound tambahan",
  "Vendor lead time": "Lead time vendor",
  "Safety stock": "Stok pengaman",
  "Baseline versus scenario chart": "Grafik baseline versus skenario",
  Baseline: "Baseline",
  Scenario: "Skenario",
  "Forecast 7d": "Proyeksi 7 hari",
  "Stockout SKUs": "SKU stockout",
  "Accuracy %": "Akurasi %",
  Trending: "Sedang tren",
  "Local scenario workspace": "Ruang kerja skenario lokal",
  "Compare Scenarios": "Bandingkan Skenario",
  "Baseline plus locally saved forecast overlays": "Baseline plus overlay proyeksi tersimpan lokal",
  saved: "tersimpan",
  compatible: "kompatibel",
  "hidden by current scope": "disembunyikan oleh cakupan saat ini",
  "No compatible scenarios for this scope": "Tidak ada skenario yang kompatibel untuk cakupan ini",
  "Saved scenarios remain available when their original scope, grain, and horizon are restored.": "Skenario tersimpan tersedia kembali saat cakupan, grain, dan horizon asal dipulihkan.",
  "Saved scenario comparison chart": "Grafik perbandingan skenario tersimpan",
  "Lever values": "Nilai lever",
  Saved: "Disimpan",
  Remove: "Hapus",
  "Run and save scenarios to overlay them against baseline.": "Jalankan dan simpan skenario untuk membandingkannya dengan baseline.",
  "Presentational recommendation": "Rekomendasi presentasional",
  "Suggested Best Action": "Saran Best Action",
  "Calculated from the current Demand scope · transactions disabled": "Dihitung dari cakupan Demand saat ini · transaksi dinonaktifkan",
  "Backend integration pending": "Integrasi backend tertunda",
  Primary: "Utama",
  Secondary: "Sekunder",
  "Preview forecast basket": "Pratinjau keranjang proyeksi",
  "Hide preview": "Tutup pratinjau",
  Signal: "Sinyal",
  Route: "Rute",
  "Generate forecast basket": "Buat keranjang proyeksi",
  "Unable to run scenario.": "Tidak dapat menjalankan skenario.",

  // Inventory Risk dashboard. Reuses the Demand filter wording above where the
  // control is the same one; only the risk-specific vocabulary is added here.
  "Inventory risk filters": "Filter risiko persediaan",
  "Inventory risk summary": "Ringkasan risiko persediaan",
  "Inventory Risk dashboard": "Dasbor Risiko Persediaan",
  "Unable to load Inventory Risk.": "Tidak dapat memuat Risiko Persediaan.",
  "All retail inventory": "Semua persediaan retail",
  "Workbook data": "Data workbook",
  "Store scope needs the per-store dataset, not yet available.":
    "Cakupan toko butuh dataset per toko, belum tersedia.",
  State: "Status",

  // The six inventory states. Kept as nouns, matching the register's chips.
  Expiry: "Kedaluwarsa",
  Overstock: "Kelebihan stok",
  "Slow-mover": "Perputaran lambat",

  // KPI tiles and their captions.
  "Overstock SKUs": "SKU kelebihan stok",
  "Expiry-risk units": "Unit berisiko kedaluwarsa",
  "Slow-moving SKUs": "SKU perputaran lambat",
  "Avg days of supply": "Rata-rata hari persediaan",
  "Inventory value": "Nilai persediaan",
  "At risk": "Berisiko",
  "Position below reorder point": "Posisi di bawah titik pemesanan",
  "Days of supply above 15": "Hari persediaan di atas 15",
  "Units beyond shelf-life cover": "Unit melebihi masa simpan",
  "Declining growth, high cover": "Pertumbuhan turun, cakupan tinggi",
  "Mean position ÷ ADS": "Rata-rata posisi ÷ ADS",
  excess: "kelebihan",
  "write-off risk": "risiko write-off",
  target: "target",
  "Click to show only the reorder zone": "Klik untuk menampilkan zona pemesanan saja",

  // Suggested best action.
  "Suggested best action": "Tindakan terbaik yang disarankan",
  "Routed to the owning agent": "Diteruskan ke agen pemiliknya",
  "Nothing needs action in the current scope.":
    "Tidak ada yang perlu ditindak pada cakupan saat ini.",
  "Other at risk": "Berisiko lainnya",

  // Charts.
  "At-risk value by state": "Nilai berisiko per status",
  "At-risk value by category": "Nilai berisiko per kategori",
  "At-risk value by cluster": "Nilai berisiko per klaster",
  "At-risk value by legal entity": "Nilai berisiko per entitas legal",
  "At-risk value": "Nilai berisiko",
  "Inventory value by category": "Nilai persediaan per kategori",
  "Stockout-risk by store": "Risiko kehabisan stok per toko",
  "Risk by dimension": "Risiko per dimensi",
  "Chain-net, full position value": "Neto rantai, nilai posisi penuh",
  "Other categories": "Kategori lain",
  Other: "Lainnya",
  Total: "Total",
  "Top 10": "10 teratas",
  Gross: "Bruto",
  "Gross · top 12": "Bruto · 12 teratas",
  "SKUs stocked": "SKU tersedia",

  // Expiry timeline.
  "Expiry timeline": "Lini masa kedaluwarsa",
  "Units at risk": "Unit berisiko",
  "No expiry exposure in the current scope.":
    "Tidak ada paparan kedaluwarsa pada cakupan saat ini.",
  "≤ 1 day": "≤ 1 hari",
  "2–3 days": "2–3 hari",
  "4–7 days": "4–7 hari",
  "> 7 days": "> 7 hari",

  // Risk register. The column tooltips carry the formula because "Position"
  // and "ROP" mean different things in different retail systems.
  "Inventory risk register": "Daftar risiko persediaan",
  SKUs: "SKU",
  "On-hand": "Stok di tangan",
  "Open PO": "PO terbuka",
  Position: "Posisi",
  ROP: "ROP",
  DoS: "Hari persediaan",
  Value: "Nilai",
  "Next agent": "Agen berikutnya",
  "On-hand = Position − Open PO": "Stok di tangan = Posisi − PO terbuka",
  "Open PO = ordered, not yet received":
    "PO terbuka = sudah dipesan, belum diterima",
  "Position = On-hand + Open PO": "Posisi = Stok di tangan + PO terbuka",
  "ROP = ADS × (Lead + Safety)": "ROP = ADS × (Lead + Safety)",
  "DoS = Position ÷ ADS": "Hari persediaan = Posisi ÷ ADS",
  "Value = Position × price": "Nilai = Posisi × harga",
  "3 Replenish": "3 Pengisian ulang",
  "5 Markdown": "5 Penurunan harga",
  Previous: "Sebelumnya",
  Next: "Berikutnya",
  Page: "Halaman",

  // Replenishment (Agent 3). Order value appears twice on purpose — at cost
  // and at retail — because the workbook states it twice and the two differ.
  "Replenishment dashboard": "Dasbor pengisian ulang",
  "Replenishment summary": "Ringkasan pengisian ulang",
  "Unable to load Replenishment.": "Gagal memuat Pengisian Ulang.",
  "Whole chain": "Seluruh rantai",
  Route: "Rute",
  "Only what needs ordering": "Hanya yang perlu dipesan",
  "SKUs to reorder": "SKU perlu dipesan",
  "Order units": "Unit pesanan",
  "sales units": "unit jual",
  "Order value at cost": "Nilai pesanan (harga beli)",
  "what the PO pays": "yang dibayar PO",
  "Order value at retail": "Nilai pesanan (harga jual)",
  "what it is worth": "nilai jualnya",
  "Fill rate": "Tingkat pemenuhan",
  cover: "cakupan",
  Recoverable: "Bisa dihemat",
  "by switching vendor": "dengan pindah vendor",
  "Order value by route": "Nilai pesanan per rute",
  "Order value by category": "Nilai pesanan per kategori",
  "Order value by store": "Nilai pesanan per toko",
  "Order value by cluster": "Nilai pesanan per klaster",
  "Order value by legal entity": "Nilai pesanan per entitas legal",
  "Close": "Tutup",
  "Prediction band width over the horizon": "Lebar rentang prediksi sepanjang horizon",
  "Forecast curve the trend compounds into": "Kurva proyeksi tempat tren terakumulasi",
  "Growth index, trending SKUs": "Indeks pertumbuhan, SKU sedang tren",
  "Days of cover, lines to reorder": "Hari cover, baris yang perlu dipesan",
  "Days of cover, all lines": "Hari cover, semua baris",
  "Units by category, largest first": "Unit per kategori, terbesar dahulu",
  "Cost by category, largest first": "Biaya per kategori, terbesar dahulu",
  "Retail value by category, largest first": "Nilai jual per kategori, terbesar dahulu",
  "Saving by vendor, largest first": "Penghematan per vendor, terbesar dahulu",
  "Days of cover, at-risk SKUs": "Hari cover, SKU berisiko",
  "Days of cover, overstocked SKUs": "Hari cover, SKU kelebihan stok",
  "Days of cover, all SKUs": "Hari cover, semua SKU",
  "Shelf life remaining": "Sisa masa simpan",
  "Growth index, slow movers": "Indeks pertumbuhan, barang lambat",
  "Value by category, largest first": "Nilai per kategori, terbesar dahulu",
  "order lines in scope": "baris pesanan dalam cakupan",
  "Show only lines to reorder": "Tampilkan hanya baris yang perlu dipesan",
  "This metric is a rate, so the breakdowns below are each group's own rate and do not sum to the headline.": "Metrik ini berupa rasio, jadi rincian di bawah adalah rasio tiap grup dan tidak menjumlah ke angka utama.",
  "The per-store grid prices at selling price and holds no vendor split, so this measure has no per-store figure to show.": "Grid per-toko memakai harga jual dan tidak memuat pembagian vendor, jadi ukuran ini tidak punya angka per toko.",
  "Current value": "Nilai saat ini",
  "across": "mencakup",
  "SKUs in scope": "SKU dalam cakupan",
  "Click to break this number down": "Klik untuk membedah angka ini",
  "Show only the reorder zone": "Tampilkan hanya zona pemesanan ulang",
  "12-period history of this metric": "Riwayat 12 periode metrik ini",
  "This metric by category": "Metrik ini per kategori",
  "This metric by store": "Metrik ini per toko",
  "Top contributing SKUs": "SKU kontributor teratas",
  "Filter the board to this SKU": "Saring papan ke SKU ini",
  "Nothing in scope.": "Tidak ada dalam cakupan.",
  "Each store's own position, derived per store — not an allocation.": "Posisi milik tiap toko, diturunkan per toko — bukan alokasi.",
  "No history recorded. The source holds a single snapshot per SKU with no date column, so a trend here would be generated rather than measured.": "Tidak ada riwayat tercatat. Sumber data hanya menyimpan satu snapshot per SKU tanpa kolom tanggal, jadi tren di sini akan dikarang, bukan diukur.",
  "This metric is an average, so the breakdowns below are each group's own average and do not sum to the headline.": "Metrik ini rata-rata, jadi rincian di bawah adalah rata-rata tiap grup dan tidak menjumlah ke angka utama.",
  "at cost": "harga beli",
  lead: "waktu tunggu",
  "At cost": "Harga beli",
  Lines: "Baris",
  lines: "baris",
  "Vendor sourcing": "Sumber vendor",
  "recoverable across all vendors": "bisa dihemat di seluruh vendor",
  "Every line is already on its cheapest quote":
    "Semua baris sudah memakai penawaran termurah",
  "if switched": "jika dialihkan",
  "cheapest on file": "termurah yang tercatat",
  OTIF: "OTIF",
  // A3 · trade agreements. `designated` and `cheapest` are row flags, so they
  // stay lower case: they read as labels on a price, not as sentences.
  "Vendor quotes": "Penawaran vendor",
  "lines could move to a cheaper vendor": "baris bisa pindah ke vendor lebih murah",
  "already on best price": "sudah di harga terbaik",
  "ordered lines are already on the cheapest quote on file.":
    "baris pesanan sudah memakai penawaran termurah yang tercatat.",
  "No line in this scope has an order to place.":
    "Tidak ada baris pada cakupan ini yang perlu dipesan.",
  "All quotes": "Semua penawaran",
  valid: "berlaku",
  "units on order": "unit dipesan",
  "per unit cheaper": "lebih murah per unit",
  "more lines with a cheaper quote, not shown":
    "baris lain punya penawaran lebih murah, tidak ditampilkan",
  Vendor: "Vendor",
  "Unit price": "Harga satuan",
  "Min qty": "Qty minimum",
  Discount: "Diskon",
  designated: "ditunjuk",
  cheapest: "termurah",
  "Purchase order preview": "Pratinjau pesanan pembelian",
  "Nothing needs ordering in the current scope.":
    "Tidak ada yang perlu dipesan pada cakupan ini.",
  "Nothing in scope.": "Tidak ada dalam cakupan.",
  Max: "Maks",
  Order: "Pesan",
  Buy: "Beli",
  "Line cost": "Biaya baris",
  Vendor: "Vendor",
  recoverable: "bisa dihemat",
  "Cheapest quote for this line": "Penawaran termurah untuk baris ini",
  top: "teratas",
  stores: "toko",
  "Order value is shown twice: at selling price, which is what the A3 sheet totals, and at trade-agreement price, which is what the purchase order would actually cost.":
    "Nilai pesanan ditampilkan dua kali: harga jual, yang dijumlahkan sheet A3, dan harga trade-agreement, yang sebenarnya dibayar pesanan pembelian.",
  "Purchase quantities round up to whole packs, so a line buys a little more than its shortfall.":
    "Kuantitas beli dibulatkan ke atas ke kelipatan kemasan, jadi satu baris membeli sedikit lebih banyak dari kekurangannya.",
  "Workbook demonstration data, not a live ERP position. Order value is reported twice — at selling price, which is what the A3 sheet totals, and at trade-agreement price, which is what the purchase order would actually cost.":
    "Data demonstrasi workbook, bukan posisi ERP langsung. Nilai pesanan dilaporkan dua kali — harga jual, yang dijumlahkan sheet A3, dan harga trade-agreement, yang sebenarnya dibayar pesanan pembelian.",

  "Code or name": "Kode atau nama",

  // Requirement vs inbound supply (A3 spec section 4).
  "Requirement vs inbound supply": "Kebutuhan vs pasokan masuk",
  Requirement: "Kebutuhan",
  "Inbound + on-hand cover": "Cakupan stok + barang masuk",
  "Gap to cover": "Selisih yang harus ditutup",
  Covered: "Tercukupi",
  "Cover runs out at": "Cakupan habis pada",
  "Cover out": "Cakupan habis",
  "Order qty": "Jumlah pesan",
  "PO value": "Nilai PO",
  Fill: "Pemenuhan",
  "Inbound is placed on each SKU's lead day because the workbook records how much is on order but never when it arrives. Requirement is a flat ADS per day, which is all one ADS per SKU can support.":
    "Barang masuk ditempatkan pada hari lead time tiap SKU karena workbook mencatat berapa yang dipesan tetapi tidak pernah kapan tibanya. Kebutuhan memakai ADS rata per hari, karena satu ADS per SKU hanya mendukung itu.",

  // Route tabs and export (A3 spec section 7).
  "Purchase order route": "Rute pesanan pembelian",
  "All routes": "Semua rute",
  "Export CSV": "Ekspor CSV",
  "Export this route": "Ekspor rute ini",
  "Export full PO": "Ekspor PO penuh",

  // What-If (A3 spec section 9).
  "Order value (cost)": "Nilai pesanan (harga beli)",
  "Avg cover days": "Rata-rata hari cakupan",
  "ADS × (1 + demand/100) — lifts ROP, Max and the order":
    "ADS × (1 + demand/100) — menaikkan ROP, Maks, dan pesanan",
  "Promo-eligible SKUs order more": "SKU yang ikut promo memesan lebih banyak",
  "Open PO × (1 + inbound/100) — more inbound, smaller order":
    "Open PO × (1 + inbound/100) — makin banyak masuk, makin kecil pesanan",
  "Longer lead raises Max, so each line orders further ahead":
    "Lead time lebih panjang menaikkan Maks, jadi tiap baris memesan lebih jauh ke depan",
  "Safety days raise Max — bigger order, more capital":
    "Hari pengaman menaikkan Maks — pesanan lebih besar, modal lebih besar",
  "This is a simulated order, not one to send.":
    "Ini pesanan simulasi, bukan yang untuk dikirim.",
  "No modelled effect": "Tidak ada efek yang dimodelkan",
  "the workbook carries no term for it, so the figures above cannot move.":
    "workbook tidak punya sukunya, jadi angka di atas tidak bisa bergerak.",

  // Projected on-hand vs demand (A2 spec section 4).
  "Projected on-hand vs demand": "Proyeksi stok vs permintaan",
  "Projected on-hand": "Proyeksi stok di tangan",
  "Demand (modelled daily)": "Permintaan (model harian)",
  "Inbound landed": "Barang masuk yang tiba",
  "Nothing in scope to project.": "Tidak ada yang bisa diproyeksikan pada cakupan ini.",
  "Cover holds across the horizon": "Cakupan bertahan sepanjang horizon",
  "Under one day of cover from": "Kurang dari satu hari cakupan sejak",
  Inbound: "Barang masuk",
  "Avg DoS": "Rata-rata hari persediaan",
  "At risk": "Berisiko",
  "Projected forward from today's position. The workbook holds one on-hand reading per SKU and no history, so there is nothing to plot before day 0. Demand is the measured ADS spread across the week by the same day-of-week and seasonal model the Demand Forecasting board draws, and stock is reordered at ROP up to Max.":
    "Diproyeksikan maju dari posisi hari ini. Workbook hanya menyimpan satu angka stok per SKU dan tidak punya riwayat, jadi tidak ada yang bisa digambar sebelum hari ke-0. Permintaan adalah ADS terukur yang disebar sepanjang minggu memakai model hari-dalam-minggu dan musiman yang sama dengan board Demand Forecasting, dan stok dipesan ulang di ROP sampai Max.",

  "Past four weeks the curve keeps its shape from the seasonal profile and the reorder policy, but its level still rests on one measured ADS per SKU — a longer horizon adds structure, not more measurement.":
    "Lewat empat minggu, bentuk kurvanya masih datang dari profil musiman dan kebijakan pemesanan ulang, tapi levelnya tetap bertumpu pada satu ADS terukur per SKU — horizon yang lebih panjang menambah struktur, bukan menambah pengukuran.",

  // What-If simulator (A2 spec section 8). The lever labels and their effects
  // are the spec's own wording; the cell references stay untranslated because
  // `Constants!B16` is an address, not prose.
  "Levers re-run the workbook's formulas · no backend calls":
    "Tuas menjalankan ulang formula workbook · tanpa panggilan backend",
  Run: "Jalankan",
  Save: "Simpan",
  Reset: "Atur ulang",
  "Move a lever before saving a scenario":
    "Geser satu tuas dulu sebelum menyimpan skenario",
  "Baseline versus scenario": "Dasar dibanding skenario",
  Baseline: "Dasar",
  Scenario: "Skenario",
  Unchanged: "Tidak berubah",
  "Demand surge": "Lonjakan permintaan",
  "Promo pull": "Tarikan promo",
  "Markdown clear": "Cuci gudang",
  "Inbound cover": "Cakupan barang masuk",
  "Lead time": "Waktu tunggu",
  "Safety days": "Hari pengaman",
  "ADS × (1 + demand/100) — DoS falls, stockouts rise":
    "ADS × (1 + permintaan/100) — hari persediaan turun, kehabisan stok naik",
  "Promo-eligible SKUs deplete faster": "SKU berpromo terkuras lebih cepat",
  "No modelled effect — the workbook has no markdown term":
    "Tidak dimodelkan — workbook tidak punya suku cuci gudang",
  "Open PO × (1 + inbound/100) — fills Position":
    "PO terbuka × (1 + barang masuk/100) — mengisi Posisi",
  "ROP = ADS × (Lead + Δ + Safety) — pushes ROP up":
    "ROP = ADS × (Lead + Δ + Safety) — mendorong ROP naik",
  "ROP += safety — fewer stockouts, more capital":
    "ROP += pengaman — kehabisan stok berkurang, modal bertambah",
  "Expiry units": "Unit kedaluwarsa",

  // Compare scenarios (A2 spec section 8d).
  "Compare scenarios": "Bandingkan skenario",
  saved: "tersimpan",
  "Save a scenario to compare it against the baseline":
    "Simpan skenario untuk membandingkannya dengan dasar",
  Day: "Hari",
  Remove: "Hapus",
  "Scenarios are held in this browser tab only and are not saved anywhere.":
    "Skenario hanya tersimpan di tab peramban ini dan tidak disimpan di mana pun.",

  // The scenario banner. This one has to be unmissable: with levers driving
  // the page, every figure above and below it is simulated.
  "These are simulated figures, not the workbook position.":
    "Angka-angka ini hasil simulasi, bukan posisi workbook.",
  "Store and cluster charts stay on the baseline — they arrive pre-aggregated.":
    "Chart toko dan klaster tetap pada dasar — datanya sudah teragregasi sejak awal.",
  "Back to workbook": "Kembali ke workbook",

  // The two caveats the board must carry, not bury (A2 spec section 10).
  "Store and cluster breakdowns are gross: they sum local risk pockets and exceed the chain-net headline, which nets surplus against shortage across stores.":
    "Rincian toko dan klaster bersifat bruto: menjumlahkan kantong risiko lokal dan melebihi angka utama neto rantai, yang saling menghapus surplus dan kekurangan antar toko.",
  "At-risk value is the full position value of every non-healthy SKU, not an expected loss.":
    "Nilai berisiko adalah nilai posisi penuh setiap SKU tidak sehat, bukan perkiraan kerugian.",

  // Chat starter prompts (QC-042). These are the first words in the chat
  // panel, and clicking a chip puts these exact words in the composer, so a
  // missing entry here would send English on behalf of a Bahasa reader.
  // Follow-ups the model writes at runtime have no entry and pass through.
  // Agent Action modal: the ranked recommendation cards (QC-061, QC-055).
  "Next best action": "Aksi terbaik berikutnya",
  "High confidence": "Keyakinan tinggi",
  "Medium confidence": "Keyakinan sedang",
  "Low confidence": "Keyakinan rendah",
  "Select recommendations": "Pilih rekomendasi",

  "Suggested prompts": "Saran pertanyaan",
  "Suggested follow-ups": "Saran pertanyaan lanjutan",

  "Which agent should fix the margin problem?":
    "Agent mana yang harus memperbaiki masalah margin?",
  "What are the largest EBITDA variance drivers?":
    "Apa penyebab terbesar selisih EBITDA?",
  "Is the price decline or the cost overrun hurting margin more?":
    "Mana yang lebih menggerus margin: penurunan harga atau pembengkakan biaya?",

  "If Collection pulls cash in earlier, what happens to Week 5?":
    "Kalau Collection menarik kas lebih awal, apa dampaknya ke Minggu 5?",
  "Which action restores the minimum cash buffer fastest?":
    "Aksi mana yang paling cepat memulihkan buffer kas minimum?",
  "What does deferring the vendor payment cost us in Week 6?":
    "Berapa biayanya di Minggu 6 kalau pembayaran vendor ditunda?",

  "How much of the Week 5 cash shortfall can collections close?":
    "Berapa banyak kekurangan kas Minggu 5 yang bisa ditutup penagihan?",
  "Which customers should Collection prioritize?":
    "Pelanggan mana yang harus diprioritaskan Collection?",
  "Where is our overdue AR most concentrated?":
    "Di mana piutang jatuh tempo kita paling terkonsentrasi?",

  "Does the blocked fraud change the cash forecast?":
    "Apakah fraud yang berhasil diblokir mengubah proyeksi kas?",
  "Which leakage issues should be investigated first?":
    "Masalah kebocoran mana yang harus diselidiki lebih dahulu?",
  "Which vendor is riskiest, and why does it rank first?":
    "Vendor mana yang paling berisiko, dan kenapa ia di peringkat pertama?",

  // Placeholder boards (Retail Agents 4-9). The per-agent bullet lists stay in
  // English on purpose: they name backlog items, and translating a backlog
  // twice is how the two copies drift apart. The chrome around them does not
  // have that problem.
  Agent: "Agent",
  "This agent is a navigation entry only. Its dashboard, chat and monitoring are not built yet, so no figures are shown here — and none are implied.":
    "Agent ini baru berupa entri navigasi. Dashboard, chat dan monitoring-nya belum dibangun, jadi tidak ada angka yang ditampilkan di sini — dan tidak ada yang disiratkan.",
  "Planned for this board": "Rencana untuk board ini",
  "Needs to exist first": "Harus ada lebih dulu",
  "From mockup page": "Dari halaman mockup",
  "Build order is a dependency, not a preference: this agent reads what those produce.":
    "Urutan pembangunan adalah ketergantungan, bukan preferensi: agent ini membaca hasil dari agent-agent tersebut.",
};

// Payload wording: KPI labels, chart titles, filter and preset labels, levers.
const PAYLOAD = {
  // KPI labels
  "EBITDA margin": "Marjin EBITDA",
  EBITDA: "EBITDA",
  Revenue: "Pendapatan",
  "Gross margin": "Marjin kotor",
  "Opex/rev": "Opex/pendapatan",
  "Week 5 cash": "Kas Minggu 5",
  "Min buffer": "Buffer minimum",
  "Net USD exposure": "Eksposur USD neto",
  "FX loss if nothing": "Rugi FX bila diam",
  "Recommended hedge": "Lindung nilai disarankan",
  "AR outstanding": "Piutang beredar",
  Overdue: "Jatuh tempo",
  DSO: "DSO",
  "Cash freed at target": "Kas terbebas di target",
  "High-risk exposure": "Eksposur risiko tinggi",
  "Flagged this cycle": "Ditandai siklus ini",
  "Fraud held": "Fraud tertahan",
  Duplicates: "Duplikat",
  Blocked: "Diblokir",
  "Total protected": "Total terlindungi",

  // Chart and table titles
  "EBITDA drivers · budget to actual":
    "Pendorong EBITDA · anggaran ke aktual",
  "Revenue by product": "Pendapatan per produk",
  "Gross margin by product": "Marjin kotor per produk",
  "Gross margin pool by product": "Kumpulan marjin kotor per produk",
  "FX sensitivity · margin at weaker IDR":
    "Sensitivitas FX · marjin saat IDR melemah",
  "Operating expenses vs budget": "Beban operasional vs anggaran",
  "Imported COGS share": "Porsi COGS impor",
  "Cash forecast · closing by week": "Proyeksi kas · saldo akhir per minggu",
  "FX loss at the adverse rate": "Rugi FX pada kurs merugikan",
  "Agent option comparison · hedge the exposure":
    "Perbandingan opsi agent · lindung nilai eksposur",
  "Exposure covered vs still open": "Eksposur tertutup vs masih terbuka",
  "Week 5 vs buffer": "Minggu 5 vs buffer",
  // The scale suffix stays "mn" in both languages — it is a unit of measure
  // alongside the ISO 4217 code, not prose. Translating it here while the KPI
  // tiles rendered `kpi.unit` untranslated put "IDR jt" and "mn" on the same
  // screen. Only the words move. See format.js.
  "Receivables aging (IDR mn)": "Umur piutang (IDR mn)",
  "Who to chase first · ranked worklist":
    "Siapa dikejar dulu · daftar kerja terurut",
  "The prize · DSO to cash": "Hasilnya · DSO menjadi kas",
  "Risk exposure by tier": "Eksposur risiko per tingkat",
  "Three collection options · cash freed":
    "Tiga opsi penagihan · kas terbebas",
  "Aging mix": "Komposisi umur",
  "Overdue vs expected recovery": "Jatuh tempo vs perkiraan pemulihan",
  "Leakage & fraud by category": "Kebocoran & fraud per kategori",
  "Blocked vs recoverable vs lost":
    "Diblokir vs dapat dipulihkan vs hilang",
  "Recovery scenario · protected by claw-back rate":
    "Skenario pemulihan · terlindungi menurut tingkat klaim balik",
  "Action worklist": "Daftar kerja tindakan",
  "Vendor risk radar": "Radar risiko vendor",
  "Leakage mix": "Komposisi kebocoran",
  "Protected vs at risk": "Terlindungi vs berisiko",

  // Filters
  Product: "Produk",
  "Cost line": "Lini biaya",
  Week: "Minggu",
  "Hedge option": "Opsi lindung nilai",
  "Ageing bucket": "Kelompok umur",
  "Risk tier": "Tingkat risiko",
  Customer: "Pelanggan",
  "Leakage type": "Jenis kebocoran",
  Status: "Status",
  Vendor: "Vendor",
  "Legal entity": "Entitas hukum",
  "All entities": "Semua entitas",
  Period: "Periode",
  "All months": "Semua bulan",
  "Category group": "Grup kategori",
  "All categories": "Semua kategori",

  // Presets
  "Close the Week 5 gap": "Tutup celah Minggu 5",
  "Collect AR-012 early": "Tagih AR-012 lebih awal",
  "Cover the exposure in full": "Tutup eksposur sepenuhnya",
  "Recover price +3%": "Pulihkan harga +3%",
  "Input cost -3%": "Biaya input -3%",
  "IDR weakens 5%": "IDR melemah 5%",
  "Collect without a discount": "Tagih tanpa diskon",
  "Buy speed with 2%": "Beli kecepatan dengan 2%",
  "Pessimistic recovery": "Pemulihan pesimistis",
  "Workbook rates": "Tingkat sesuai workbook",
  "Release the hold": "Lepas penahanan",

  // Simulator levers
  Price: "Harga",
  Cost: "Biaya",
  Volume: "Volume",
  FX: "FX",
  Opex: "Opex",
  "Accelerate collection": "Percepat penagihan",
  "Defer payment": "Tunda pembayaran",
  "Credit line draw": "Penarikan fasilitas kredit",
  "Forward-cover USD": "Lindung nilai forward USD",
  "Pull from customer (mn)": "Tarik dari pelanggan (mn)",
  "Discount %": "Diskon %",
  "Hold amount mn": "Jumlah ditahan mn",
  "Dup recovery %": "Pemulihan duplikat %",
  "Overbill rec %": "Pemulihan overbilling %",

  // KPI delta templates. The backend splits a caption like "target 15.5%"
  // into a number (reformatted per-language by format.js) and this template,
  // with "{v}" marking where the number goes back in — see
  // `_extract_delta_number` in dashboard_blocks.py. Only the words move;
  // "{v}" must survive untouched, and finance jargon that is already kept as
  // an English loanword elsewhere in this dictionary (buffer, hedge, target,
  // vs) stays a loanword here too, for the same reason.
  "target {v}": "target {v}",
  "headroom {v} vs buffer": "headroom {v} vs buffer",
  "recommended hedge {v}M": "lindung nilai disarankan {v}M",
  "{v} of AR": "{v} dari piutang",
  "provision {v}": "provisi {v}",
  "{v} flags": "{v} temuan",
};

const DICTIONARY = { ...CHROME, ...PAYLOAD };

// The period line is generated, so it is rewritten by pattern rather than
// looked up. Order matters: longer phrases first.
const PERIOD_RULES = [
  [/(\d+)-week forecast/g, "Proyeksi $1 minggu"],
  [/AR ageing snapshot/g, "Snapshot umur piutang"],
  [/DSO on a (\d+)-day basis/g, "DSO basis $1 hari"],
  [/invoices scanned/g, "faktur dipindai"],
  [/actual vs budget/g, "aktual vs anggaran"],
  [/\bto\b/g, "s.d."],
  [/period not stated in the source workbook/g,
   "periode tidak dinyatakan di workbook sumber"],
];

const MONTHS = [
  ["January", "Januari"], ["February", "Februari"], ["March", "Maret"],
  ["April", "April"], ["June", "Juni"], ["July", "Juli"],
  ["August", "Agustus"], ["September", "September"], ["October", "Oktober"],
  ["November", "November"], ["December", "Desember"], ["May", "Mei"],
  ["Jan", "Jan"], ["Feb", "Feb"], ["Mar", "Mar"], ["Apr", "Apr"],
  ["Jun", "Jun"], ["Jul", "Jul"], ["Aug", "Agu"], ["Sep", "Sep"],
  ["Oct", "Okt"], ["Nov", "Nov"], ["Dec", "Des"],
];

export function translatePeriod(text, lang) {
  if (lang !== "id" || !text) {
    return text;
  }
  let out = text;
  for (const [pattern, replacement] of PERIOD_RULES) {
    out = out.replace(pattern, replacement);
  }
  for (const [english, indonesian] of MONTHS) {
    out = out.replace(new RegExp(`\\b${english}\\b`, "g"), indonesian);
  }
  return out;
}

// Some labels are generated with a figure in them — a preset named after the
// scenario stored with the dataset ("Price +4.0% alone") changes whenever that
// scenario does, so it cannot be a dictionary key. These carry the number
// across untouched and translate only the words around it.
export const LABEL_RULES = [
  [/^Price (\S+) alone$/, "Harga $1 saja"],
  [/^IDR weakens (\S+)$/, "IDR melemah $1"],
];

/** Translate one string, or return it unchanged when there is no entry. */
export function translate(text, lang) {
  if (lang !== "id" || typeof text !== "string" || !text) {
    return text;
  }
  const exact = DICTIONARY[text];
  if (exact !== undefined) {
    return exact;
  }
  for (const [pattern, replacement] of LABEL_RULES) {
    if (pattern.test(text)) {
      return text.replace(pattern, replacement);
    }
  }
  return text;
}

function translateElement(element, lang) {
  if (!element || typeof element !== "object") {
    return element;
  }
  return {
    ...element,
    title: translate(element.title, lang),
    period: translatePeriod(element.period, lang),
  };
}

function mapValues(source, fn) {
  return Object.fromEntries(
    Object.entries(source || {}).map(([key, value]) => [key, fn(value)])
  );
}

/**
 * Translate a dashboard payload in one pass.
 * Numbers, chart data and ids are untouched — only wording changes.
 */
export function translatePayload(dashboard, lang) {
  if (!dashboard || lang !== "id") {
    return dashboard;
  }

  const simulator = dashboard.simulator
    ? {
        ...dashboard.simulator,
        inputs: (dashboard.simulator.inputs || []).map((input) => ({
          ...input,
          label: translate(input.label, lang),
        })),
        presets: (dashboard.simulator.presets || []).map((preset) => ({
          ...preset,
          label: translate(preset.label, lang),
        })),
      }
    : dashboard.simulator;

  return {
    ...dashboard,
    period: translatePeriod(dashboard.period, lang),
    kpis: (dashboard.kpis || []).map((kpi) => ({
      ...kpi,
      label: translate(kpi.label, lang),
    })),
    views: mapValues(dashboard.views, (view) => translateElement(view, lang)),
    side: mapValues(dashboard.side, (view) => translateElement(view, lang)),
    filters: (dashboard.filters || []).map((filter) => ({
      ...filter,
      label: translate(filter.label, lang),
    })),
    simulator,
  };
}
