import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLanguage } from "../../../../LanguageProvider.jsx";

const SERIES_COLOURS = ["var(--blue-500)", "var(--green-500)", "var(--amber-500)", "var(--red-500)"];

/**
 * Compare Scenarios — A4 spec section 9d. Overlays the baseline plus up to four
 * saved scenarios, one line each. The baseline is the workbook's own curve
 * (simulation.baseline), never the currently-applied levers, so a comparison
 * whose reference moves with the sliders compares nothing.
 */
export default function PromoScenarioComparison({ baseline, scenarios, onRemove }) {
  const { t } = useLanguage();
  if (!scenarios || scenarios.length === 0) return null;

  const metricIds = ["active_promo_skus", "uplift_pct", "incremental_margin", "roi_x"];
  const labels = ["Promo SKUs", "Uplift %", "Incr margin", "ROI"];

  const data = metricIds.map((id, i) => {
    const point = { metric: labels[i] };
    if (baseline) point["Baseline"] = Number(baseline[id]) || 0;
    scenarios.forEach((sc, idx) => {
      point[sc.name] = Number(sc.kpis?.[id]) || 0;
    });
    return point;
  });

  const seriesNames = ["Baseline", ...scenarios.map((s) => s.name)];

  return (
    <section className="promo-scenario-comparison" data-testid="promo-scenario-comparison">
      <header className="promo-section-head">
        <h3>{t("Compare scenarios")}</h3>
      </header>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="metric" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          {seriesNames.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={SERIES_COLOURS[i % SERIES_COLOURS.length]}
              strokeWidth={2}
              dot
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <ul className="promo-scenario-list">
        {scenarios.map((sc, i) => (
          <li key={sc.id}>
            <span style={{ color: SERIES_COLOURS[i % SERIES_COLOURS.length] }}>●</span>
            {sc.name}
            <button type="button" onClick={() => onRemove(sc.id)}>
              {t("Remove")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
