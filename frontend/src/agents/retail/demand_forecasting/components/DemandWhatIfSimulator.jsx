import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

const METRICS = [
  ["forecast_next_7d", "Forecast 7d", "number"],
  ["stockout_risk_skus", "Stockout SKUs", "number"],
  ["forecast_accuracy_pct", "Accuracy %", "percent"],
  ["predicted_to_trend", "Trending", "number"],
];

function metricValue(value, kind, language) {
  return `${formatNumber(value, language, { maximumFractionDigits: kind === "percent" ? 1 : 0 })}${kind === "percent" ? "%" : ""}`;
}

export default function DemandWhatIfSimulator({
  simulation,
  draftLevers,
  onLeverChange,
  onRun,
  onSave,
  onLoad,
  onReset,
  driveWholePage,
  onDriveWholePageChange,
  savedCount,
  busy,
  canSave,
}) {
  const { language, t } = useLanguage();
  const chartData = METRICS.map(([id, label]) => ({
    id,
    label: t(label),
    baseline: 100,
    scenario: simulation.baseline[id]
      ? Math.max(0, (simulation.scenario[id] / simulation.baseline[id]) * 100)
      : 100,
  }));

  return (
    <section className="demand-panel demand-simulator" aria-labelledby="demand-simulator-title">
      <header className="demand-panel-head demand-simulator-head">
        <div>
          <p>{t("Frontend mock scenario")}</p>
          <h2 id="demand-simulator-title">{t("What-If Simulator")}</h2>
          <span>{t("Baseline versus scenario · no backend calls")}</span>
        </div>
        <div className="demand-simulator-actions">
          <button type="button" className="demand-button" onClick={onRun} disabled={busy}>{busy ? t("Running…") : t("Run")}</button>
          <button type="button" className="demand-button demand-button--quiet" onClick={onSave} disabled={!canSave}>{t("Save")}</button>
          <button type="button" className="demand-button demand-button--quiet" onClick={onLoad} disabled={!savedCount || busy} title={!savedCount ? t("No saved scenarios yet") : ""}>{t("Load")}</button>
          <button type="button" className="demand-button demand-button--quiet" onClick={onReset}>{t("Reset")}</button>
        </div>
      </header>

      <label className="demand-drive-toggle">
        <input type="checkbox" checked={driveWholePage} onChange={(event) => onDriveWholePageChange(event.target.checked)} />
        <span>{t("Levers drive whole page")}</span>
      </label>

      <div className="demand-lever-grid">
        {simulation.levers.map((lever) => (
          <label key={lever.id} className="demand-lever">
            <span><b>{t(lever.label)}</b><output>{draftLevers[lever.id]}{lever.unit}</output></span>
            <input
              type="range"
              aria-label={t(lever.label)}
              min={lever.min}
              max={lever.max}
              step={lever.step}
              value={draftLevers[lever.id]}
              onChange={(event) => onLeverChange(lever.id, Number(event.target.value))}
            />
            <small>{t(lever.effect)}</small>
          </label>
        ))}
      </div>

      <div className="demand-simulator-results">
        <div className="demand-simulation-chart" role="img" aria-label={t("Baseline versus scenario chart")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
              <YAxis domain={[0, "auto"]} tick={{ fontSize: 9, fill: "var(--muted)" }} tickFormatter={(value) => `${Math.round(value)}`} tickLine={false} axisLine={false} />
              <Tooltip formatter={(value) => `${formatNumber(value, language, { maximumFractionDigits: 1 })} index`} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar dataKey="baseline" name={t("Baseline")} fill="var(--demand-baseline)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="scenario" name={t("Scenario")} fill="var(--demand-scenario)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="demand-scenario-metrics">
          {METRICS.map(([id, label, kind]) => (
            <article key={id}>
              <span>{t(label)}</span>
              <strong>{metricValue(simulation.scenario[id], kind, language)}</strong>
              <small>{t("Baseline")}: {metricValue(simulation.baseline[id], kind, language)}</small>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

