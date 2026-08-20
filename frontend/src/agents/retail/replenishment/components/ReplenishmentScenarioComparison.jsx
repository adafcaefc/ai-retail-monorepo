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

/** Baseline plus up to four scenarios, A3 spec section 9d. */
const SERIES_COLOURS = [
  "var(--po-baseline, var(--gray-400))",
  "var(--po-scenario, var(--accent))",
  "var(--po-compare-2, var(--po-route-direct))",
  "var(--po-compare-3, var(--po-route-flow))",
  "var(--po-compare-4, var(--po-route-cross))",
];

function leverSummary(levers) {
  const moved = Object.entries(levers).filter(([, value]) => value !== 0);
  if (!moved.length) return "baseline";
  return moved.map(([id, value]) => `${id} ${value > 0 ? "+" : ""}${value}`).join(" · ");
}

/**
 * A3 spec section 9d (`#ch-compare`): saved scenarios overlaid.
 *
 * What is overlaid is each scenario's cover curve, not its KPI totals. The
 * question a buyer brings to a scenario is "does this run me out before the PO
 * lands", and four totals per scenario cannot answer it however neatly they are
 * tabulated. The listed figure is the order value each scenario commits, which
 * is what the comparison is ultimately deciding between.
 *
 * Scenarios live in this browser tab only. Nothing is posted anywhere and
 * nothing survives a reload, which the footer says plainly — a saved scenario
 * that quietly disappears is worse than one that never claimed to persist.
 */
export default function ReplenishmentScenarioComparison({
  baseline,
  scenarios,
  onRemove,
}) {
  const { language, t } = useLanguage();

  if (!baseline?.points?.length) return null;

  // One row per week, one column per series — the shape Recharts wants.
  const data = baseline.points.map((point, index) => {
    const row = { label: point.label, baseline: point.cover };
    for (const [position, scenario] of scenarios.entries()) {
      row[`s${position}`] = scenario.requirement.points[index]?.cover ?? null;
    }
    return row;
  });

  return (
    <section className="po-panel po-compare" aria-labelledby="po-compare-title">
      <header className="po-panel-head">
        <h3 id="po-compare-title">{t("Compare scenarios")}</h3>
        <span className="po-panel-note">
          {scenarios.length
            ? `${scenarios.length} / 4 ${t("saved")}`
            : t("Save a scenario to compare it against the baseline")}
        </span>
      </header>

      <div className="po-chart" role="img" aria-label={t("Compare scenarios")}>
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
              width={56}
              tickFormatter={(value) => formatUnits(value, language)}
            />
            <Tooltip formatter={(value) => formatUnits(Math.round(value), language)} />
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
        <ul className="po-scenario-list">
          {scenarios.map((scenario, position) => (
            <li key={scenario.id}>
              <span
                className="po-scenario-swatch"
                style={{ background: SERIES_COLOURS[position + 1] }}
                aria-hidden="true"
              />
              <span className="po-scenario-name">{scenario.name}</span>
              <span className="po-scenario-levers">{leverSummary(scenario.levers)}</span>
              <span className="po-scenario-value">
                {formatIdr(scenario.kpis.order_value_cost, language)}
              </span>
              <button
                type="button"
                className="po-button po-button--quiet"
                onClick={() => onRemove(scenario.id)}
                aria-label={`${t("Remove")} ${scenario.name}`}
              >
                {t("Remove")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="po-panel-caveat">
        {t("Scenarios are held in this browser tab only and are not saved anywhere.")}
      </p>
    </section>
  );
}
