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

import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { getDemandScenarioYAxisDomain } from "../data/chartSeries.js";

const SERIES_COLORS = [
  "var(--blue-500)",
  "var(--green-500)",
  "var(--amber-500)",
  "var(--red-500)",
];

function future(series) {
  return (series?.points || []).filter((point) => point.forecast != null);
}

function leverSummary(levers) {
  return `demand ${levers.demand}% · promo ${levers.promo}% · markdown ${levers.markdown}% · inbound ${levers.inbound}% · lead ${levers.lead}d · safety ${levers.safety}d`;
}

export function visibleDemandScenarios(scenarios) {
  return scenarios.slice(-4);
}

export default function DemandScenarioComparison({ baselineForecast, scenarios, hiddenCount = 0, onRemove }) {
  const { language, t } = useLanguage();
  const baseline = future(baselineForecast);
  const visibleScenarios = visibleDemandScenarios(scenarios);
  const data = baseline.map((point, index) => {
    const row = { label: point.label, baseline: point.forecast };
    visibleScenarios.forEach((scenario) => {
      row[scenario.id] = future(scenario.forecast)[index]?.forecast ?? null;
    });
    return row;
  });
  const axisDomain = getDemandScenarioYAxisDomain(data);

  return (
    <section className="demand-panel demand-scenario-compare" aria-labelledby="demand-compare-title">
      <header className="demand-panel-head">
        <div>
          <p>{t("Local scenario workspace")}</p>
          <h2 id="demand-compare-title">{t("Compare Scenarios")}</h2>
          <span>{t("Baseline plus locally saved forecast overlays")}</span>
        </div>
        <span className="demand-panel-tag">
          {scenarios.length} {t("compatible")}
          {hiddenCount ? ` · ${hiddenCount} ${t("hidden by current scope")}` : ""}
        </span>
      </header>

      {scenarios.length ? (
        <>
          <div className="demand-compare-chart" role="img" aria-label={t("Saved scenario comparison chart")}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
                <YAxis domain={axisDomain} tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={58} tickFormatter={(value) => formatNumber(value, language, { maximumFractionDigits: 0 })} />
                <Tooltip formatter={(value) => formatNumber(value, language, { maximumFractionDigits: 0 })} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Line type="monotone" dataKey="baseline" name={t("Baseline")} stroke="var(--gray-400)" strokeDasharray="4 3" strokeWidth={2} dot={false} isAnimationActive={false} />
                {visibleScenarios.map((scenario, index) => (
                  <Line key={scenario.id} type="monotone" dataKey={scenario.id} name={scenario.name} stroke={SERIES_COLORS[index]} strokeWidth={2.2} dot={false} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="demand-scenario-table-wrap">
            <table>
              <thead><tr><th>{t("Scenario")}</th><th>{t("Lever values")}</th><th>{t("Forecast 7d")}</th><th>{t("Saved")}</th><th /></tr></thead>
              <tbody>
                {scenarios.map((scenario) => (
                  <tr key={scenario.id}>
                    <td><strong>{scenario.name}</strong></td>
                    <td>{leverSummary(scenario.levers)}</td>
                    <td>{formatNumber(scenario.metrics.forecast_next_7d, language, { maximumFractionDigits: 0 })}</td>
                    <td>{scenario.savedAt}</td>
                    <td><button type="button" onClick={() => onRemove(scenario.id)} aria-label={`${t("Remove")} ${scenario.name}`}>×</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="demand-compare-empty">
          <strong>{t(hiddenCount ? "No compatible scenarios for this scope" : "No saved scenarios yet")}</strong>
          <span>{t(hiddenCount
            ? "Saved scenarios remain available when their original scope, grain, and horizon are restored."
            : "Run and save scenarios to overlay them against baseline.")}</span>
        </div>
      )}
    </section>
  );
}
