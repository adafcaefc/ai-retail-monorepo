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
 * Compare Scenarios — A6 spec section 9d. The baseline is the workbook's own
 * curve (simulation.baseline), never the currently-applied levers, so a
 * comparison whose reference moves with the sliders compares nothing.
 */
export default function AssortmentScenarioComparison({ baseline, scenarios, onRemove }) {
  const { t } = useLanguage();
  if (!scenarios || scenarios.length === 0) return null;

  const metricIds = ["delist_candidates", "grow_candidates", "avg_gmroi", "capital_freed"];
  const labels = ["Delist", "Grow", "Avg GMROI", "Capital freed"];

  const data = metricIds.map((id, i) => {
    const point = { metric: labels[i] };
    if (baseline) point["Baseline"] = Number(baseline[id]) || 0;
    scenarios.forEach((sc) => {
      point[sc.name] = Number(sc.kpis?.[id]) || 0;
    });
    return point;
  });

  const seriesNames = ["Baseline", ...scenarios.map((s) => s.name)];

  return (
    <section className="assortment-scenario-comparison" data-testid="assortment-scenario-comparison">
      <header className="assortment-section-head">
        <h3>{t("Compare scenarios")}</h3>
        <span className="assortment-section-note">
          {t("Counts and rupiah share one axis — read each metric against its own baseline, not against the others.")}
        </span>
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
      <ul className="assortment-scenario-list">
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
