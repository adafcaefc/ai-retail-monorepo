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
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { BASELINE_LEVERS, LEVER_DEFINITIONS, SIMULATION_STRIP_METRICS } from "../data/contract.js";
import { formatIdr, formatPercent } from "../presentation.js";

/** How each metrics-strip tile reads as text — A5 spec section 9c (#sim-metrics). */
function stripMetricValue(id, value, language) {
  if (id === "recovery_rate_pct" || id === "avg_depth_pct") {
    return formatPercent(value / 100, language, { digits: 1 });
  }
  return formatIdr(value, language);
}

/**
 * The What-If simulator — A5 spec section 9c. Every lever here is modelled;
 * `markdown` is the one that moves recoverable value rather than state or
 * position — it widens the recovery depth f14-recoverable-at-risk-value
 * applies to f23's gross exposure. `is-inert` styling stays available for a
 * future lever this formula set genuinely does not model.
 *
 * Live, not draft-and-apply: every slider move recomputes baseline/scenario
 * (and, with "Drive whole page" on, the rest of the dashboard) immediately —
 * `levers` IS the current value, not a draft awaiting a Run click. This is
 * cheap because `buildPricingMarkdownDashboard` is pure/synchronous over
 * already-fetched rows (see dashboardData.js); the parent wraps the derived
 * dashboard in `useDeferredValue` so dragging itself stays smooth.
 */
export default function PricingWhatIfSimulator({
  simulation,
  levers,
  onLeverChange,
  onReset,
  onSave,
  driveWholePage,
  onDriveWholePageChange,
  canSave,
  busy,
}) {
  const { language, t } = useLanguage();
  const index = simulation?.index ?? [];

  return (
    <section className="pricing-simulator" data-testid="pricing-simulator">
      <header className="pricing-section-head">
        <h3>{t("What-If simulator")}</h3>
        <label className="pricing-drive-toggle">
          <input
            type="checkbox"
            checked={driveWholePage}
            onChange={(event) => onDriveWholePageChange(event.target.checked)}
          />
          {t("Drive whole page")}
        </label>
      </header>

      <div className="pricing-levers">
        {LEVER_DEFINITIONS.map((lever) => (
          <label key={lever.id} className={`pricing-lever${lever.modelled === false ? " is-inert" : ""}`}>
            <span className="pricing-lever-label">
              {t(lever.label)}
              <em className="pricing-lever-cell">{lever.cell}</em>
            </span>
            <span className="pricing-lever-effect">{t(lever.effect)}</span>
            <span className="pricing-lever-control">
              <input
                type="range"
                min={lever.min}
                max={lever.max}
                step={lever.step}
                value={Number(levers?.[lever.id] ?? BASELINE_LEVERS[lever.id])}
                disabled={busy}
                onChange={(event) => onLeverChange(lever.id, Number(event.target.value))}
              />
              <output>
                {levers?.[lever.id] ?? BASELINE_LEVERS[lever.id]}
                {lever.unit}
              </output>
            </span>
          </label>
        ))}
      </div>

      <div className="pricing-simulator-actions">
        <button type="button" className="pricing-button" onClick={onReset} disabled={busy}>
          {t("Reset")}
        </button>
        <button
          type="button"
          className="pricing-button"
          onClick={onSave}
          disabled={!canSave || busy}
          title={!canSave ? t("Move a lever, then save") : ""}
        >
          {t("Save scenario")}
        </button>
      </div>

      <div className="pricing-simulator-chart">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={index} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis domain={[0, "auto"]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="baseline_index" name={t("Baseline")} fill="var(--gray-400)" />
            <Bar dataKey="scenario_index" name={t("Scenario")} fill="var(--blue-500)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {simulation?.applied ? (
        <div className="pricing-sim-metrics">
          {SIMULATION_STRIP_METRICS.map(({ id, label, lowerIsBetter }) => {
            const baseline = simulation.baseline?.[id] ?? 0;
            const scenario = simulation.scenario?.[id] ?? 0;
            const delta = scenario - baseline;
            const improved = lowerIsBetter ? delta < 0 : delta > 0;
            const tone = delta === 0 ? "flat" : improved ? "good" : "bad";
            return (
              <article key={id} className={`pricing-sim-metric is-${tone}`}>
                <span>{t(label)}</span>
                <strong>{stripMetricValue(id, scenario, language)}</strong>
                <small>
                  {delta === 0
                    ? t("Unchanged")
                    : `(${delta > 0 ? "+" : "−"}${stripMetricValue(id, Math.abs(delta), language)})`}
                </small>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
