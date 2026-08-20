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
import { LEVER_DEFINITIONS, MARKDOWN_INSIGHT_NOTE } from "../data/contract.js";
import { formatDays, formatIdr, formatUnits } from "../presentation.js";

/** How the four compared metrics read as text, A2 spec section 8c. */
function metricValue(id, value, language) {
  if (id === "at_risk_value") return formatIdr(value, language);
  if (id === "expiry_units") return formatUnits(Math.round(value), language);
  return formatNumber(value, language, { maximumFractionDigits: 0 });
}

/**
 * A2 spec section 8c (`#ch-simagent`): baseline against scenario.
 *
 * The five levers left are `Constants` B16, B17, B19–B21, and moving one
 * redraws this panel's own chart and KPI strip immediately — see
 * `liveSimulation`. Nothing here computes anything; it moves numbers into
 * sliders and reads the answer back.
 *
 * Two different things happen on two different triggers, and the header note
 * says which is which: the panel itself follows `draftLevers` on every tick,
 * because it costs one pass over the rows already in hand. Run commits that
 * position to the rest of the board (subject to "Levers drive whole page")
 * and is what a saved scenario is measured from — see
 * `InventoryRiskDashboard.jsx` for why re-running every other panel on every
 * tick would fight a multi-lever drag instead of following it.
 *
 * The sliders start at zero, which is where the workbook's own levers sit. The
 * mockup starts promo at 15 and markdown at 25, but those are the values of a
 * published *scenario*, not of the baseline, and opening there would show a
 * simulation while the board claimed to show the workbook.
 */
export default function RiskWhatIfSimulator({
  liveSimulation,
  draftLevers,
  onLeverChange,
  onRun,
  onSave,
  onReset,
  driveWholePage,
  onDriveWholePageChange,
  canSave,
  busy,
}) {
  const { language, t } = useLanguage();

  const chartData = (liveSimulation?.index ?? []).map((metric) => ({
    id: metric.id,
    label: t(metric.label),
    baseline: 100,
    // A baseline of zero has no index; drawing 100 there would invent a
    // comparison that does not exist.
    scenario: metric.scenario_index === null ? 0 : Math.max(0, metric.scenario_index),
  }));

  const strip = [
    ["Stockout-risk SKUs", "stockout_risk_skus"],
    ["Expiry-risk units", "expiry_units"],
    ["Inventory value", "inventory_value"],
    ["Avg days of supply", "avg_dos"],
  ];

  return (
    <section className="risk-panel risk-simulator" aria-labelledby="risk-simulator-title">
      <header className="risk-panel-head risk-simulator-head">
        <div>
          <h3 id="risk-simulator-title">{t("What-If Simulator")}</h3>
          <span className="risk-panel-note">
            {t(
              "This chart moves as you drag · press Run to apply the position across the whole board",
            )}
          </span>
        </div>
        <div className="risk-simulator-actions">
          <button type="button" className="risk-button" onClick={onRun} disabled={busy}>
            {busy ? t("Running…") : t("Run")}
          </button>
          <button
            type="button"
            className="risk-button risk-button--quiet"
            onClick={onSave}
            disabled={!canSave}
            title={canSave ? "" : t("Run a scenario before saving it")}
          >
            {t("Save")}
          </button>
          <button type="button" className="risk-button risk-button--quiet" onClick={onReset}>
            {t("Reset")}
          </button>
        </div>
      </header>

      <label className="risk-drive-toggle">
        <input
          type="checkbox"
          checked={driveWholePage}
          onChange={(event) => onDriveWholePageChange(event.target.checked)}
        />
        <span>{t("Levers drive whole page")}</span>
      </label>

      <div className="risk-lever-grid">
        {LEVER_DEFINITIONS.map((lever) => (
          <label key={lever.id} className="risk-lever">
            <span>
              <b>{t(lever.label)}</b>
              <output>
                {draftLevers[lever.id]}
                {lever.unit}
              </output>
            </span>
            <input
              type="range"
              aria-label={t(lever.label)}
              min={lever.min}
              max={lever.max}
              step={lever.step}
              value={draftLevers[lever.id]}
              onChange={(event) => onLeverChange(lever.id, Number(event.target.value))}
            />
            <small title={`Constants!${lever.cell}`}>{t(lever.effect)}</small>
          </label>
        ))}
      </div>

      <p className="risk-simulator-note">{t(MARKDOWN_INSIGHT_NOTE)}</p>

      <div className="risk-simulator-results">
        <div
          className="risk-chart risk-chart--sim"
          role="img"
          aria-label={t("Baseline versus scenario")}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 9, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--line)" }}
              />
              <YAxis
                domain={[0, "auto"]}
                tick={{ fontSize: 9, fill: "var(--muted)" }}
                tickFormatter={(value) => `${Math.round(value)}`}
                tickLine={false}
                axisLine={false}
                width={36}
              />
              <Tooltip
                formatter={(value) =>
                  `${formatNumber(value, language, { maximumFractionDigits: 1 })} index`
                }
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar
                dataKey="baseline"
                name={t("Baseline")}
                fill="var(--risk-baseline)"
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
              <Bar
                dataKey="scenario"
                name={t("Scenario")}
                fill="var(--risk-scenario)"
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="risk-scenario-metrics">
          {strip.map(([label, id]) => {
            const scenario = liveSimulation?.scenario?.[id] ?? 0;
            const baseline = liveSimulation?.baseline?.[id] ?? 0;
            const delta = scenario - baseline;
            return (
              <article key={id}>
                <span>{t(label)}</span>
                <strong>
                  {id === "avg_dos"
                    ? formatDays(scenario, language)
                    : metricValue(id, scenario, language)}
                </strong>
                <small>
                  {delta === 0
                    ? t("Unchanged")
                    : `${delta > 0 ? "+" : "−"}${
                        id === "avg_dos"
                          ? formatDays(Math.abs(delta), language)
                          : metricValue(id, Math.abs(delta), language)
                      }`}
                </small>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
