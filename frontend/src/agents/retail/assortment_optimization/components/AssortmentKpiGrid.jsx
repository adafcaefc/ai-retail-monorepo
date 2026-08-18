import { useLanguage } from "../../../../LanguageProvider.jsx";
import KpiSparkline from "../../../../components/KpiSparkline.jsx";
import {
  formatGmroi,
  formatIdr,
  formatPercent,
  formatUnits,
  kpiAccent,
  kpiTone,
} from "../presentation.js";
import { KPI_FORMULAS } from "../data/contract.js";

/** The six headline KPI tiles — A6 spec section 3. */
const TILES = [
  { id: "delist_candidates", label: "Delist candidates", format: "units" },
  { id: "grow_candidates", label: "Grow candidates", format: "units" },
  { id: "avg_gmroi", label: "Avg GMROI", format: "gmroi" },
  { id: "tail_share_pct", label: "Tail share %", format: "percent" },
  { id: "capital_freed", label: "Capital freed", format: "idr" },
  { id: "contribution_per_day", label: "Contribution/day", format: "idr" },
];

export default function AssortmentKpiGrid({ kpis, sparklines = {}, onOpenDrilldown }) {
  const { t, language } = useLanguage();

  return (
    <div className="assortment-kpi-grid" data-testid="assortment-kpi-grid">
      {TILES.map((tile) => {
        const value = Number(kpis?.[tile.id]) || 0;
        const sparkline = sparklines[tile.id];
        return (
          <button
            type="button"
            key={tile.id}
            className={`assortment-kpi assortment-kpi--${kpiTone(tile.id, value)}`}
            style={{ "--assortment-kpi-accent": kpiAccent(tile.id) }}
            title={KPI_FORMULAS[tile.id] ?? ""}
            onClick={() => onOpenDrilldown?.(tile.id)}
          >
            <span className="assortment-kpi-label">{t(tile.label)}</span>
            <span className="assortment-kpi-value">{formatValue(tile, value, language)}</span>
            {sparkline ? <KpiSparkline kind={sparkline.kind} values={sparkline.values} /> : null}
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
      return formatPercent(value / 100, language); // stored as a whole number (47.1 -> 47.1%)
    case "gmroi":
      return formatGmroi(value, language);
    case "units":
    default:
      return formatUnits(value, language);
  }
}
