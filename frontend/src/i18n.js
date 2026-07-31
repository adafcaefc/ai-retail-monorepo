// QC-058: Bahasa Indonesia toggle.
//
// The board's wording comes from two places: the React components, and the
// dashboard payload the agents build in Python. Rather than thread a locale
// through the backend, the payload is translated once when it arrives
// (`translatePayload`) and the components use `t()`.
//
// Lookup is by exact English string. Anything absent renders in English, which
// keeps a missing entry a visibly untranslated label rather than a blank one
// or a crash. Figures are never touched: a number is the same in both.

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
  "Receivables aging (IDR mn)": "Umur piutang (IDR jt)",
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
  "Pull from customer (mn)": "Tarik dari pelanggan (jt)",
  "Discount %": "Diskon %",
  "Hold amount mn": "Jumlah ditahan jt",
  "Dup recovery %": "Pemulihan duplikat %",
  "Overbill rec %": "Pemulihan overbilling %",
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
