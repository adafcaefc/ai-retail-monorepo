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
import { PROJECTION_NOTE } from "../data/contract.js";
import { formatDays, formatIdr, formatUnits } from "../presentation.js";

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
        {t("Demand per day")}: {formatUnits(Math.round(point.demand), language)}
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
 * The replenishment cycle in two lines — stock falling by a day's demand,
 * stepping back up as open POs land at their lead time. Both lines are read
 * from the workbook per SKU (`ads`, `open_po`, `lead_days`); the only
 * assumption is that demand is flat, which it has to be, because one ADS per
 * SKU is all the workbook holds.
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
              name={t("Demand per day")}
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

      <p className="risk-panel-caveat">{t(PROJECTION_NOTE)}</p>
    </section>
  );
}
