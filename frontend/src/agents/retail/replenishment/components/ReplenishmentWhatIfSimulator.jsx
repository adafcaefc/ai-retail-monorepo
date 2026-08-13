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
import { LEVER_DEFINITIONS, SIMULATION_METRICS } from "../data/contract.js";
import { formatDays, formatIdr, formatUnits } from "../presentation.js";

/** How each compared metric reads as text. */
function metricValue(id, value, language) {
  if (id === "order_value_cost") return formatIdr(value, language);
  if (id === "avg_cover_days") return formatDays(value, language);
  if (id === "order_units") return formatUnits(Math.round(value), language);
  return formatNumber(value, language, { maximumFractionDigits: 0 });
}

/**
 * A3 spec section 9c: baseline against scenario for the purchase order.
 *
 * The six levers are `Constants` B16–B21, and moving one re-runs the workbook's
 * own expressions over every line in scope — see `data/engine.js`. Nothing here
 * computes anything; it moves numbers into sliders and reads the answer back.
 *
 * Sliders start at zero, where the workbook's own levers sit. The mockup opens
 * promo at 15 and markdown at 25, but those are the values of a published
 * *scenario*, and opening there would show a simulation while the board claimed
 * to show the workbook.
 */
export default function ReplenishmentWhatIfSimulator({
  simulation,
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

  const chartData = simulation.index.map((metric) => ({
    id: metric.id,
    label: t(metric.label),
    baseline: 100,
    // A baseline of zero has no index; drawing 100 there would invent a
    // comparison that does not exist.
    scenario: metric.scenario_index === null ? 0 : Math.max(0, metric.scenario_index),
  }));

  return (
    <section className="po-panel po-simulator" aria-labelledby="po-simulator-title">
      <header className="po-panel-head po-simulator-head">
        <div>
          <h3 id="po-simulator-title">{t("What-If Simulator")}</h3>
          <span className="po-panel-note">
            {t("Levers re-run the workbook's formulas · no backend calls")}
          </span>
        </div>
        <div className="po-simulator-actions">
          <button type="button" className="po-button" onClick={onRun} disabled={busy}>
            {busy ? t("Running…") : t("Run")}
          </button>
          <button
            type="button"
            className="po-button po-button--quiet"
            onClick={onSave}
            disabled={!canSave}
            title={canSave ? "" : t("Move a lever before saving a scenario")}
          >
            {t("Save")}
          </button>
          <button type="button" className="po-button po-button--quiet" onClick={onReset}>
            {t("Reset")}
          </button>
        </div>
      </header>

      <label className="po-drive-toggle">
        <input
          type="checkbox"
          checked={driveWholePage}
          onChange={(event) => onDriveWholePageChange(event.target.checked)}
        />
        <span>{t("Levers drive whole page")}</span>
      </label>

      <div className="po-lever-grid">
        {LEVER_DEFINITIONS.map((lever) => (
          <label
            key={lever.id}
            className={lever.modelled === false ? "po-lever po-lever--inert" : "po-lever"}
          >
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
              disabled={lever.modelled === false}
              onChange={(event) => onLeverChange(lever.id, Number(event.target.value))}
            />
            <small title={`Constants!${lever.cell}`}>{t(lever.effect)}</small>
          </label>
        ))}
      </div>

      <div className="po-simulator-results">
        <div
          className="po-chart po-chart--sim"
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
                fill="var(--po-baseline, var(--gray-400))"
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
              <Bar
                dataKey="scenario"
                name={t("Scenario")}
                fill="var(--po-scenario, var(--accent))"
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="po-scenario-metrics">
          {SIMULATION_METRICS.map(({ id, label }) => {
            const scenario = simulation.scenario?.[id] ?? 0;
            const baseline = simulation.baseline?.[id] ?? 0;
            const delta = scenario - baseline;
            return (
              <article key={id}>
                <span>{t(label)}</span>
                <strong>{metricValue(id, scenario, language)}</strong>
                <small>
                  {delta === 0
                    ? t("Unchanged")
                    : `${delta > 0 ? "+" : "−"}${metricValue(id, Math.abs(delta), language)}`}
                </small>
              </article>
            );
          })}
        </div>
      </div>

      {/*
       * Why a slider can move and nothing happen. Saying so is the difference
       * between a documented gap and a board that looks broken.
       */}
      {simulation.unmodelled.length ? (
        <p className="po-panel-caveat">
          {t("No modelled effect")}: {simulation.unmodelled.map((id) => t(id)).join(", ")} —{" "}
          {t("the workbook carries no term for it, so the figures above cannot move.")}
        </p>
      ) : null}
    </section>
  );
}
