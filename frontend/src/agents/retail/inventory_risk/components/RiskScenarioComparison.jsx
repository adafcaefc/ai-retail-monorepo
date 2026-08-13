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
import { formatIdr, formatUnits } from "../presentation.js";

/** Baseline plus up to four scenarios, A2 spec section 8d. */
const SERIES_COLOURS = [
  "var(--risk-baseline)",
  "var(--risk-scenario)",
  "var(--risk-compare-2)",
  "var(--risk-compare-3)",
  "var(--risk-compare-4)",
];

function leverSummary(levers) {
  const moved = Object.entries(levers).filter(([, value]) => value !== 0);
  return moved.length ? moved.map(([id, value]) => `${id} ${value > 0 ? "+" : ""}${value}`).join(" · ") : "baseline";
}

/**
 * A2 spec section 8d (`#ch-compare`): saved scenarios overlaid.
 *
 * What is overlaid is each scenario's stock curve, not its KPI totals. A
 * scenario is a shape over time — "does this run the chain down before the PO
 * lands" — and four numbers per scenario cannot answer that, however neatly
 * they are tabulated.
 *
 * Scenarios live in this session only. Nothing is posted anywhere and nothing
 * survives a reload, which the footer says plainly: a saved scenario that
 * quietly disappears is worse than one that never claimed to persist.
 */
export default function RiskScenarioComparison({ baseline, scenarios, onRemove }) {
  const { language, t } = useLanguage();

  if (!baseline?.points?.length) return null;

  // One row per day, one column per series — the shape Recharts wants.
  const data = baseline.points.map((point, index) => {
    const row = { label: point.label, baseline: point.on_hand };
    for (const [position, scenario] of scenarios.entries()) {
      row[`s${position}`] = scenario.projection.points[index]?.on_hand ?? null;
    }
    return row;
  });

  return (
    <section className="risk-panel risk-compare" aria-labelledby="risk-compare-title">
      <header className="risk-panel-head">
        <h3 id="risk-compare-title">{t("Compare scenarios")}</h3>
        <span className="risk-panel-note">
          {scenarios.length
            ? `${scenarios.length} / 4 ${t("saved")}`
            : t("Save a scenario to compare it against the baseline")}
        </span>
      </header>

      <div className="risk-chart" role="img" aria-label={t("Compare scenarios")}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              interval={6}
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--line)" }}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={false}
              width={52}
              tickFormatter={(value) => formatUnits(value, language)}
            />
            <Tooltip
              formatter={(value) => formatUnits(Math.round(value), language)}
              labelFormatter={(label) => `${t("Day")} ${label}`}
            />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Line
              type="monotone"
              dataKey="baseline"
              name={t("Baseline")}
              stroke={SERIES_COLOURS[0]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            {scenarios.map((scenario, position) => (
              <Line
                key={scenario.id}
                type="monotone"
                dataKey={`s${position}`}
                name={scenario.name}
                stroke={SERIES_COLOURS[position + 1]}
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {scenarios.length > 0 && (
        <ul className="risk-scenario-list">
          {scenarios.map((scenario, position) => (
            <li key={scenario.id}>
              <span
                className="risk-scenario-swatch"
                style={{ background: SERIES_COLOURS[position + 1] }}
                aria-hidden="true"
              />
              <span className="risk-scenario-name">{scenario.name}</span>
              <span className="risk-scenario-levers">{leverSummary(scenario.levers)}</span>
              <span className="risk-scenario-value">
                {formatIdr(scenario.kpis.at_risk_value, language)}
              </span>
              <button
                type="button"
                className="risk-button risk-button--quiet"
                onClick={() => onRemove(scenario.id)}
                aria-label={`${t("Remove")} ${scenario.name}`}
              >
                {t("Remove")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="risk-panel-caveat">
        {t("Scenarios are held in this browser tab only and are not saved anywhere.")}
      </p>
    </section>
  );
}
