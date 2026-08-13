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
  "Frontend mock scenario": "Skenario mock frontend",
  "What-If Simulator": "Simulator What-If",
  "Baseline versus scenario · no backend calls": "Baseline versus skenario · tanpa panggilan backend",
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
