import { useLanguage } from "../../../../LanguageProvider.jsx";
import KpiSparkline from "../../../../components/KpiSparkline.jsx";
import { kpiAccent, kpiTone, formatIdr, formatPercent, formatUnits, formatIndex } from "../presentation.js";
import { KPI_FORMULAS } from "../data/contract.js";

/** The six headline KPI tiles — A5 spec section 3. */
const TILES = [
  { id: "markdown_candidates", label: "Markdown candidates", format: "units" },
  { id: "avg_depth_pct", label: "Avg depth %", format: "percent" },
  { id: "at_risk_value", label: "At-risk value", format: "idr" },
  { id: "recoverable_value", label: "Recoverable", format: "idr" },
  { id: "write_off_value", label: "Write-off", format: "idr" },
  { id: "comp_idx", label: "Comp idx", format: "index" },
];

export default function PricingKpiGrid({ kpis, sparklines = {}, onOpenDrilldown }) {
  const { t, language } = useLanguage();

  return (
    <div className="pricing-kpi-grid" data-testid="pricing-kpi-grid">
      {TILES.map((tile) => {
        const value = Number(kpis?.[tile.id]) || 0;
        const sparkline = sparklines[tile.id];
        return (
          <button
            type="button"
            key={tile.id}
            className={`pricing-kpi pricing-kpi--${kpiTone(tile.id, value)}`}
            style={{ "--pricing-kpi-accent": kpiAccent(tile.id) }}
            title={KPI_FORMULAS[tile.id] ?? ""}
            onClick={() => onOpenDrilldown?.(tile.id)}
          >
            <span className="pricing-kpi-label">{t(tile.label)}</span>
            <span className="pricing-kpi-value">{formatValue(tile, value, language)}</span>
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
      return formatPercent(value / 100, language); // stored as a whole number (28.4 -> 28.4%)
    case "index":
      return formatIndex(value, language);
    case "units":
    default:
      return formatUnits(value, language);
  }
}
