const ENTITY_DEFINITIONS = [
  {
    value: "GRC",
    label: "GRC · Grocery Retail",
    categories: ["Fresh Produce", "Beverages", "Pantry"],
  },
  {
    value: "FSH",
    label: "FSH · Fashion Retail",
    categories: ["Apparel", "Footwear", "Accessories"],
  },
  {
    value: "HBA",
    label: "HBA · Health & Beauty",
    categories: ["Personal Care", "Wellness", "Cosmetics"],
  },
  {
    value: "HME",
    label: "HME · Home & Electronics",
    categories: ["Homeware", "Electronics", "Small Appliances"],
  },
];

const CITY_NAMES = ["Jakarta", "Bandung", "Surabaya"];
const ITEM_NAMES = [
  "Everyday Essential",
  "Premium Selection",
  "Family Pack",
  "Urban Choice",
  "Seasonal Favourite",
  "Smart Value",
  "Signature Line",
  "Daily Fresh",
  "Classic Range",
  "New Arrival",
];

function hash(index, salt) {
  let value = (index + 1) * (2654435761 + salt * 97);
  value ^= value >>> 16;
  value = Math.imul(value, 2246822519);
  value ^= value >>> 13;
  return Math.abs(value >>> 0);
}

export const LEGAL_ENTITIES = ENTITY_DEFINITIONS.map(({ value, label }) => ({
  value,
  label,
}));

export const STORES = ENTITY_DEFINITIONS.flatMap((entity, entityIndex) =>
  CITY_NAMES.map((city, storeIndex) => ({
    value: `${entity.value}-S${storeIndex + 1}`,
    label: `${entity.value} ${city} ${storeIndex + 1}`,
    legal_entity_id: entity.value,
  })),
);

const baseRows = Array.from({ length: 400 }, (_, index) => {
  const entity = ENTITY_DEFINITIONS[index % ENTITY_DEFINITIONS.length];
  const storeIndex = Math.floor(index / ENTITY_DEFINITIONS.length) % CITY_NAMES.length;
  const categoryIndex = Math.floor(index / 12) % entity.categories.length;
  const skuNumber = String(index + 1).padStart(3, "0");
  const rawAds = 92 + (hash(index, 3) % 1320) / 10;
  const growthIndex = 0.92 + (hash(index, 5) % 490) / 1000;

  return {
    sku_id: `${entity.value}-${skuNumber}`,
    sku_name: `${ITEM_NAMES[index % ITEM_NAMES.length]} ${skuNumber}`,
    legal_entity_id: entity.value,
    category_id: `${entity.value}-C${String(categoryIndex + 1).padStart(2, "0")}`,
    category_label: entity.categories[categoryIndex],
    store_id: `${entity.value}-S${storeIndex + 1}`,
    ads_raw: rawAds,
    growth_index: growthIndex,
    mape_raw: 5.2 + (hash(index, 7) % 390) / 100,
    seasonality_raw: 1.02 + (hash(index, 11) % 230) / 1000,
    risk_score: hash(index, 13),
    trend_score: hash(index, 17),
    signal_score: hash(index, 19),
  };
});

const riskIds = new Set(
  [...baseRows]
    .sort((left, right) => right.risk_score - left.risk_score)
    .slice(0, 302)
    .map((row) => row.sku_id),
);
const trendIds = new Set(
  [...baseRows]
    .sort((left, right) => right.trend_score - left.trend_score)
    .slice(0, 355)
    .map((row) => row.sku_id),
);

export const DEMAND_SKUS = baseRows.map((row, index) => {
  const signals = [];
  if (trendIds.has(row.sku_id)) signals.push(index % 5 === 0 ? "viral" : "growth");
  if (row.signal_score % 4 === 0) signals.push("seasonal");
  if (row.signal_score % 7 === 0) signals.push("promo");

  return {
    ...row,
    stockout_risk: riskIds.has(row.sku_id),
    predicted_to_trend: trendIds.has(row.sku_id),
    signals: signals.length ? [...new Set(signals)] : ["stable"],
  };
});

export const CATEGORY_OPTIONS = ENTITY_DEFINITIONS.flatMap((entity) =>
  entity.categories.map((label, index) => ({
    value: `${entity.value}-C${String(index + 1).padStart(2, "0")}`,
    label,
    legal_entity_id: entity.value,
  })),
);

export const REFERENCE_BASELINE = Object.freeze({
  forecast_next_7d: 1656179,
  accuracy_pct: 93,
  trend_pct: 4.8,
  stockout_risk_skus: 302,
  predicted_to_trend: 355,
  seasonality_index: 114,
  peak: "Saturday ×1.35",
});

export const DAY_OF_WEEK_FACTORS = [0.85, 0.9, 0.95, 1, 1.15, 1.35, 1.25];
