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
import { REQUIREMENT_NOTE } from "../data/contract.js";
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
 * Two cumulative curves. Requirement accumulates at a flat ADS per day, which
 * is all one ADS per SKU can support. Cover is today's on-hand plus each SKU's
 * open PO once it lands on its lead day — it steps rather than slopes, because
 * a delivery is an event, not a trickle.
 *
 * Where requirement crosses cover is the gap a purchase order exists to close,
 * and `gap = requirement − cover → PO` is the spec's own reading of it.
 *
 * The mockup lifts requirement by 1.02. That factor is in no workbook cell and
 * stands for nothing, so it is not reproduced here — reproduced, it would read
 * as a measured safety margin rather than as a prototype's rounding.
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
          {requirement.cover_runs_out === null
            ? t("Cover holds across the horizon")
            : `${t("Cover runs out at")} D+${requirement.cover_runs_out}`}
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
            <Tooltip content={<RequirementTooltip />} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            {/* Today. There is no history to divide off — see the caveat. */}
            <ReferenceLine x="Today" stroke="var(--line)" strokeDasharray="4 4" />
            {requirement.cover_runs_out !== null ? (
              <ReferenceLine
                x={`D+${requirement.cover_runs_out}`}
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

      <p className="po-panel-caveat">{t(REQUIREMENT_NOTE)}</p>
    </section>
  );
}
