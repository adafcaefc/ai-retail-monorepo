import { useLanguage } from "../../../../LanguageProvider.jsx";
import KpiSparkline from "../../../../components/KpiSparkline.jsx";
import { kpiAccent, kpiTone, formatIdr, formatPercent, formatUnits, formatRoi } from "../presentation.js";
import { KPI_FORMULAS } from "../data/contract.js";

/**
 * The six headline KPI tiles. Each carries its value, a sparkline, and a hover
 * formula label sourced from the workbook. Tone follows promotion semantics:
 * high cannibalization is the only warn state here.
 */
const TILES = [
  { id: "active_promo_skus", label: "Active promo SKUs", format: "units" },
  { id: "uplift_pct", label: "Uplift %", format: "percent" },
  { id: "incremental_margin", label: "Incremental margin", format: "idr" },
  { id: "roi_x", label: "ROI", format: "roi" },
  { id: "cannib_pct", label: "Cannib %", format: "percent" },
  { id: "funding_pct", label: "Funding %", format: "percent" },
];

export default function PromoKpiGrid({ kpis, sparklines = {}, onOpenDrilldown }) {
  const { t, language } = useLanguage();

  return (
    <div className="promo-kpi-grid" data-testid="promo-kpi-grid">
      {TILES.map((tile) => {
        const value = Number(kpis?.[tile.id]) || 0;
        const sparkline = sparklines[tile.id];
        return (
          <button
            type="button"
            key={tile.id}
            className={`promo-kpi promo-kpi--${kpiTone(tile.id, value)}`}
            style={{ "--promo-kpi-accent": kpiAccent(tile.id) }}
            title={KPI_FORMULAS[tile.id] ?? ""}
            onClick={() => onOpenDrilldown?.(tile.id)}
          >
            <span className="promo-kpi-label">{t(tile.label)}</span>
            <span className="promo-kpi-value">{formatValue(tile, value, language)}</span>
            {sparkline ? (
              <KpiSparkline kind={sparkline.kind} values={sparkline.values} />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function formatValue(tile, value, language) {
  switch (tile.format) {
    case "idr":
      return formatIdr(value, language);
    case "percent":
      return formatPercent(value / 100, language); // stored as a whole number (26 -> 26%)
    case "roi":
      return formatRoi(value, language);
    case "units":
    default:
      return formatUnits(value, language);
  }
}
