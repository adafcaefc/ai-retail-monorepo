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
  REQUIREMENT_FALLBACK_NOTE,
  REQUIREMENT_NOTE,
} from "../data/contract.js";
import { formatIdr, formatPercent, formatUnits } from "../presentation.js";

function RequirementTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const point = payload[0].payload;

  // History points (W-16..W-1) carry actual_demand only — the forward fields
  // are null there, not zero, because no table records what was delivered 16
  // weeks ago. Today is deliberately NOT one of these: it carries both demand
  // series, which is what joins the history line to the forecast line.
  if (point.requirement === null) {
    return (
      <div className="po-chart-tooltip">
        <strong>{label}</strong>
        <span>
          {t("Actual demand")}: {formatUnits(Math.round(point.actual_demand), language)}
        </span>
      </div>
    );
  }

  // Today carries both demand series but no arrival, so it reads as the
  // opening position and nothing else.
  if (point.inbound === null) {
    return (
      <div className="po-chart-tooltip">
        <strong>{label}</strong>
        <span>
          {t("Requirement")}: {formatUnits(Math.round(point.requirement), language)}
        </span>
        <span>
          {t("On hand")}: {formatUnits(Math.round(point.on_hand_after), language)}
        </span>
      </div>
    );
  }

  /*
   * The two plotted flows, then the stock underneath them. A week where
   * inbound falls short of demand is ordinary -- the shelf covers it -- so
   * the shortfall reading comes off `on_hand_after`, not off the gap between
   * the lines. Saying "short" on a week the shelf covered would send a buyer
   * chasing a purchase order that is not needed.
   */
  const gap = point.inbound - point.requirement;

  return (
    <div className="po-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("Requirement")}: {formatUnits(Math.round(point.requirement), language)}
      </span>
      <span>
        {t("Inbound supply")}: {formatUnits(Math.round(point.inbound), language)}
      </span>
      <span>
        {gap >= 0
          ? `${t("Builds stock by")}: ${formatUnits(Math.round(gap), language)}`
          : `${t("Draws stock by")}: ${formatUnits(Math.round(-gap), language)}`}
      </span>
      <span className={point.on_hand_after <= 0 ? "po-tooltip-gap" : ""}>
        {point.on_hand_after <= 0
          ? t("Shelf empty")
          : `${t("On hand after")}: ${formatUnits(Math.round(point.on_hand_after), language)}`}
      </span>
    </div>
  );
}

/**
 * A3 spec section 4 (`#ch-main`): what the chain needs against what is coming.
 *
 * 33 weekly points, W-16 through Today through W+16, every plotted series in
 * units per week — see `computeRequirement` in `data/selectors.js` for where
 * the curves come from and for the two unit mismatches this shape exists to
 * end. *Actual demand* and *Requirement* are one continuous demand backbone
 * measured either side of now; *Inbound supply* is what arrives each week,
 * oscillating about that backbone rather than sitting above it.
 *
 * The stock the two flows imply (`on_hand_after`) is deliberately NOT a line
 * here. It is two to three times the weekly rate — a shelf restocked every
 * week or two has to be — and drawing it on this axis is what made the gap
 * look like a 3M surplus instead of ordinary batching. It belongs in the
 * tooltip, where it answers the question the lines cannot: a week where
 * inbound dips under demand is absorbed by the shelf, and only an empty shelf
 * is a shortfall.
 *
 * The three `<Line>`s keep `connectNulls={false}` on purpose. The chart once
 * showed a gap at the divider, and the fix was not to bridge two series across
 * a null — that would draw a line between quantities that were never the same
 * thing. Today simply carries a real value in both demand series now, so they
 * meet at a point they genuinely share.
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

  /*
   * The y-axis is framed on the data, not anchored at zero.
   *
   * Every plotted series here is a weekly rate in the same narrow band --
   * demand runs 1.60M to 1.91M and inbound tracks it within a few percent --
   * so a zero-anchored axis spends 80% of its height on empty space below the
   * lines and squeezes the entire comparison into the top tenth of the panel.
   * At that scale a real 2.4% swing in supply is a couple of pixels and reads
   * as a flat line.
   *
   * This is a comparison of two like quantities, not a magnitude chart, so
   * framing on the data is the honest choice rather than a flattering one --
   * and the axis ticks state the range they cover, so nothing is hidden. The
   * padding keeps the curves off the top and bottom edges.
   */
  const plotted = requirement.points.flatMap((point) =>
    [point.actual_demand, point.requirement, point.inbound].filter(
      (value) => typeof value === "number",
    ),
  );
  const low = plotted.length ? Math.min(...plotted) : 0;
  const high = plotted.length ? Math.max(...plotted) : 0;
  const padding = (high - low) * 0.2 || high * 0.05 || 1;
  const domain = [Math.max(0, low - padding), high + padding];

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
            : `${t("Cover runs out at")} W+${requirement.cover_runs_out}`}
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
              domain={domain}
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={(value) => formatUnits(value, language)}
            />
            <Tooltip content={<RequirementTooltip />} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            {/* The boundary between 16 real weeks of history and 16 of forecast. */}
            <ReferenceLine x="Today" stroke="var(--line)" strokeDasharray="4 4" />
            {requirement.cover_runs_out !== null ? (
              <ReferenceLine
                x={`W+${requirement.cover_runs_out}`}
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
              dataKey="actual_demand"
              name={t("Actual demand")}
              stroke="var(--muted)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
            <Line
              type="monotone"
              dataKey="requirement"
              name={t("Requirement")}
              stroke="var(--po-requirement, var(--danger))"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
            <Line
              type="monotone"
              dataKey="inbound"
              name={t("Inbound supply")}
              stroke="var(--po-cover, var(--success))"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
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
        {t(requirement.inbound_scheduled ? REQUIREMENT_NOTE : REQUIREMENT_FALLBACK_NOTE)}
      </p>
    </section>
  );
}
