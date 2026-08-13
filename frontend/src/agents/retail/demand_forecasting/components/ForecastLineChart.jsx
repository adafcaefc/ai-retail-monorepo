import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

function DemandTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload || {};
  return (
    <div className="demand-chart-tooltip">
      <strong>{label}</strong>
      {point.actual != null ? <span>{t("Actual")}: {formatNumber(point.actual, language, { maximumFractionDigits: 0 })}</span> : null}
      {point.forecast != null ? <span>{t("AI Forecast")}: {formatNumber(point.forecast, language, { maximumFractionDigits: 0 })}</span> : null}
      {point.confidence_low != null && point.confidence_high != null ? (
        <span>
          {t("Confidence")}: {formatNumber(point.confidence_low, language, { maximumFractionDigits: 0 })}
          {" – "}
          {formatNumber(point.confidence_high, language, { maximumFractionDigits: 0 })}
        </span>
      ) : null}
    </div>
  );
}

export default function ForecastLineChart({ points, ariaLabel, compact = false }) {
  const { language, t } = useLanguage();
  const data = points.map((point) => ({
    ...point,
    confidence_range:
      point.confidence_low == null || point.confidence_high == null
        ? null
        : [point.confidence_low, point.confidence_high],
  }));
  const boundary = data.find((point) => point.forecast != null)?.key;

  return (
    <div className={`demand-forecast-chart${compact ? " demand-forecast-chart--compact" : ""}`} role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 16, left: 2, bottom: 2 }}>
          <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} minTickGap={18} />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={false}
            width={58}
            tickFormatter={(value) => formatNumber(value, language, { maximumFractionDigits: 0 })}
          />
          <Tooltip content={<DemandTooltip />} />
          <Area
            type="monotone"
            dataKey="confidence_range"
            stroke="none"
            fill="var(--demand-band)"
            fillOpacity={0.32}
            isAnimationActive={false}
          />
          {boundary ? (
            <ReferenceLine
              x={boundary}
              stroke="var(--demand-boundary)"
              strokeDasharray="4 4"
              label={{ value: t("Forecast starts"), position: "insideTopRight", fontSize: 10, fill: "var(--muted)" }}
            />
          ) : null}
          <Line type="monotone" dataKey="actual" name={t("Actual")} stroke="var(--demand-actual)" strokeWidth={2.4} dot={false} connectNulls={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="forecast" name={t("AI Forecast")} stroke="var(--demand-forecast)" strokeWidth={2.4} strokeDasharray="6 3" dot={false} connectNulls={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="demand-chart-legend" aria-hidden="true">
        <span className="actual">{t("Actual")}</span>
        <span className="forecast">{t("AI Forecast")}</span>
        <span className="band">{t("Confidence band")}</span>
      </div>
    </div>
  );
}
