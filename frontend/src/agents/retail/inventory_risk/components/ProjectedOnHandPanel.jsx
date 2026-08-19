import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import {
  DAYS_PER_WEEK,
  DEFAULT_HORIZON_WEEKS,
  LONG_HORIZON_NOTE,
  PROJECTION_NOTE,
} from "../data/contract.js";
import { formatDays, formatIdr, formatUnits } from "../presentation.js";

/**
 * How many points the axis skips between labels.
 *
 * Recharts counts the points it hides, so a label every N weeks is
 * `N * 7 - 1`. N grows with the horizon to hold the label count near five:
 * four weeks labels every week, sixteen weeks every four. A fixed spacing
 * tuned for 28 days would crowd seventeen labels onto a sixteen-week curve.
 */
function labelInterval(horizonWeeks) {
  const everyNWeeks = Math.max(1, Math.ceil(horizonWeeks / DEFAULT_HORIZON_WEEKS));
  return everyNWeeks * DAYS_PER_WEEK - 1;
}

function ProjectionTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const point = payload[0].payload;
  return (
    <div className="risk-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("Projected on-hand")}: {formatUnits(Math.round(point.on_hand), language)}
      </span>
      <span>
        {t("Demand (modelled daily)")}:{" "}
        {formatUnits(Math.round(point.demand), language)}
      </span>
      <span>
        {t("Inbound landed")}: {formatUnits(Math.round(point.inbound), language)}
      </span>
    </div>
  );
}

/**
 * A2 spec section 4 (`#ch-main`): projected on-hand against demand.
 *
 * The replenishment cycle in two lines — stock falling by a day's demand and
 * stepping back up as orders land at their lead time. Every figure behind them
 * is read from the workbook per SKU (`ads`, `open_po`, `lead_days`, `rop`,
 * `max`); what is modelled is how a measured week of demand is spread across
 * its seven days, which is why the demand line is labelled as modelled.
 *
 * The spec draws a split line between history and forecast. There is no
 * history: the workbook stores a single on-hand reading. So the reference line
 * marks today and the panel says why nothing sits to its left, rather than
 * back-casting a straight line and letting it read as measurement.
 */
export default function ProjectedOnHandPanel({ projection }) {
  const { language, t } = useLanguage();

  if (!projection.points.length) {
    return (
      <section className="risk-panel risk-projection" aria-label={t("Projected on-hand vs demand")}>
        <header className="risk-panel-head">
          <h3>{t("Projected on-hand vs demand")}</h3>
        </header>
        <p className="risk-empty">{t("Nothing in scope to project.")}</p>
      </section>
    );
  }

  const horizonWeeks = projection.horizon_weeks;

  const metrics = [
    ["Position", formatUnits(Math.round(projection.metrics.position), language)],
    ["Inbound", formatUnits(Math.round(projection.metrics.inbound), language)],
    ["Avg DoS", formatDays(projection.metrics.avg_dos, language)],
    ["At risk", formatIdr(projection.metrics.at_risk_value, language)],
  ];

  return (
    <section className="risk-panel risk-projection" aria-label={t("Projected on-hand vs demand")}>
      <header className="risk-panel-head">
        <h3>{t("Projected on-hand vs demand")}</h3>
        <span className="risk-panel-note">
          {projection.days_to_empty === null
            ? t("Cover holds across the horizon")
            : `${t("Under one day of cover from")} D+${projection.days_to_empty}`}
        </span>
      </header>

      <div className="risk-chart risk-chart--tall" role="img" aria-label={t("Projected on-hand vs demand")}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={projection.points} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              interval={labelInterval(horizonWeeks)}
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
            <Tooltip content={<ProjectionTooltip />} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            {/* Today, not a history split: there is no history to divide off. */}
            <ReferenceLine x="Today" stroke="var(--line)" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="on_hand"
              name={t("Projected on-hand")}
              stroke="var(--risk-projection)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="demand"
              name={t("Demand (modelled daily)")}
              stroke="var(--risk-demand)"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <dl className="risk-metric-strip">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt>{t(label)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <p className="risk-panel-caveat">
        {t(PROJECTION_NOTE)}
        {horizonWeeks > DEFAULT_HORIZON_WEEKS ? ` ${t(LONG_HORIZON_NOTE)}` : ""}
      </p>
    </section>
  );
}
