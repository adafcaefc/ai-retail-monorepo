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
  REQUIREMENT_CURVE_NOTE,
  REQUIREMENT_NOTE,
} from "../data/contract.js";
import { formatIdr, formatPercent, formatUnits } from "../presentation.js";

function RequirementTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const point = payload[0].payload;
  const gap = point.requirement - point.cover;

  return (
    <div className="po-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("Requirement")}: {formatUnits(Math.round(point.requirement), language)}
      </span>
      <span>
        {t("Inbound + on-hand cover")}: {formatUnits(Math.round(point.cover), language)}
      </span>
      <span className={gap > 0 ? "po-tooltip-gap" : ""}>
        {gap > 0
          ? `${t("Gap to cover")}: ${formatUnits(Math.round(gap), language)}`
          : t("Covered")}
      </span>
    </div>
  );
}

/**
 * A3 spec section 4 (`#ch-main`): what the chain needs against what is coming.
 *
 * Two presentations, and the data picks. With the 32-week demand curve the
 * lines now carry, the chart is weekly: requirement is the scope's demand —
 * 16 measured weeks, then 16 forecast weeks, today between W-1 and W+1 — and
 * cover is modelled as the lagged blend of last week's and this week's
 * demand, because no table records when an inbound order arrives. Where
 * requirement stands above cover is the gap a purchase order exists to close,
 * and `gap = requirement − cover → PO` is the spec's own reading of it.
 *
 * Without the curve the chart is the daily fallback: requirement accumulating
 * at a flat ADS, cover stepping up as open POs land on their lead days.
 *
 * The mockup lifts requirement by 1.03. That factor is in no workbook cell and
 * stands for nothing, so it is not reproduced here — reproduced, it would read
 * as a measured safety margin rather than as a prototype's rounding. Its
 * every-fourth-week cover dips are invented for the same reason.
 */
export default function RequirementVsInboundPanel({ requirement, kpis }) {
  const { language, t } = useLanguage();

  if (!requirement.points.length) {
    return (
      <section className="po-panel po-requirement" aria-label={t("Requirement vs inbound supply")}>
        <header className="po-panel-head">
          <h3>{t("Requirement vs inbound supply")}</h3>
        </header>
        <p className="po-empty">{t("Nothing in scope to project.")}</p>
      </section>
    );
  }

  const weekly = requirement.mode === "weekly";
  // The divider's label: the last actual week, the mockup's own `splitAt`.
  const todayLabel = weekly
    ? requirement.points[requirement.split_index]?.label
    : "Today";
  // When cover first falls short: W+k on the weekly chart, D+n on the daily
  // one. Null means it never does inside the horizon.
  const shortfallLabel = weekly
    ? requirement.first_shortfall_week
    : requirement.cover_runs_out === null
      ? null
      : `D+${requirement.cover_runs_out}`;

  /* A3 spec section 4, `#main-stats`. */
  const metrics = [
    ["Reorder", formatUnits(kpis.skus_to_reorder, language)],
    ["Order qty", formatUnits(Math.round(kpis.order_units), language)],
    ["PO value", formatIdr(kpis.order_value_cost, language)],
    ["Fill", formatPercent(kpis.fill_rate_pct, language)],
  ];

  return (
    <section className="po-panel po-requirement" aria-label={t("Requirement vs inbound supply")}>
      <header className="po-panel-head">
        <h3>{t("Requirement vs inbound supply")}</h3>
        <span className="po-panel-note">
          {shortfallLabel === null
            ? t("Cover holds across the horizon")
            : `${t("Cover runs out at")} ${shortfallLabel}`}
        </span>
      </header>

      <div
        className="po-chart po-chart--tall"
        role="img"
        aria-label={t("Requirement vs inbound supply")}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={requirement.points}
            margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
          >
            <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              interval={weekly ? 3 : 6}
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
            <Tooltip content={<RequirementTooltip />} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            {/* Today: on the split between the last actual week and the first
                forecast one — or, on the daily fallback, the left edge. */}
            <ReferenceLine
              x={todayLabel}
              stroke="var(--line)"
              strokeDasharray="4 4"
              label={{
                value: t("Today"),
                position: "top",
                fontSize: 9,
                fill: "var(--muted)",
              }}
            />
            {shortfallLabel !== null ? (
              <ReferenceLine
                x={shortfallLabel}
                stroke="var(--po-gap, var(--danger))"
                strokeDasharray="2 3"
                label={{
                  value: t("Cover out"),
                  position: "top",
                  fontSize: 9,
                  fill: "var(--muted)",
                }}
              />
            ) : null}
            <Line
              type="monotone"
              dataKey="requirement"
              name={t("Requirement")}
              stroke="var(--po-requirement, var(--danger))"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="cover"
              name={t("Inbound + on-hand cover")}
              stroke="var(--po-cover, var(--success))"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <dl className="po-metric-strip">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt>{t(label)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <p className="po-panel-caveat">
        {t(weekly ? REQUIREMENT_CURVE_NOTE : REQUIREMENT_NOTE)}
      </p>
    </section>
  );
}
