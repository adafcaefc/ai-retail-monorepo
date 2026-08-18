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
 * Compare Scenarios — A5 spec section 9d. The baseline is the workbook's own
 * curve (simulation.baseline), never the currently-applied levers, so a
 * comparison whose reference moves with the sliders compares nothing.
 */
export default function PricingScenarioComparison({ baseline, scenarios, onRemove }) {
  const { t } = useLanguage();
  if (!scenarios || scenarios.length === 0) return null;

  const metricIds = ["markdown_candidates", "at_risk_value", "recoverable_value", "write_off_value"];
  const labels = ["Candidates", "At-risk value", "Recoverable", "Write-off"];

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
    <section className="pricing-scenario-comparison" data-testid="pricing-scenario-comparison">
      <header className="pricing-section-head">
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
      <ul className="pricing-scenario-list">
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
