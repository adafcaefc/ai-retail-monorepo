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
  usePlotArea,
  useXAxisScale,
  useYAxisScale,
} from "recharts";

import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import {
  buildDemandTransitionData,
  getDemandChartYAxisDomain,
} from "../data/chartSeries.js";

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

const YEARLY_STUB_LENGTH = 24;
const YEARLY_PLOT_INSET = 32;

// Yearly has only two genuine data points. These pixel-space segments give
// each series a short visual lead-in/out without changing its data or ticks.
function YearlyVisualStubs({ enabled, points }) {
  const plotArea = usePlotArea();
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();

  if (!enabled || !plotArea || !xScale || !yScale) return null;

  const actual = points[0];
  const forecast = points[1];
  const actualX = xScale(actual.label, { position: "middle" });
  const forecastX = xScale(forecast.label, { position: "middle" });
  const actualY = yScale(actual.actual);
  const forecastY = yScale(forecast.forecast);
  if ([actualX, forecastX, actualY, forecastY].some((value) => value == null)) {
    return null;
  }

  const left = plotArea.x;
  const right = plotArea.x + plotArea.width;
  return (
    <g
      className="demand-yearly-stubs"
      pointerEvents="none"
      clipPath="none"
    >
      <line
        className="demand-yearly-actual-stub"
        data-testid="yearly-actual-stub"
        x1={Math.max(left, actualX - YEARLY_STUB_LENGTH)}
        x2={actualX}
        y1={actualY}
        y2={actualY}
        stroke="var(--demand-actual)"
        strokeWidth={2.4}
      />
      <line
        className="demand-yearly-forecast-stub"
        data-testid="yearly-forecast-stub"
        x1={forecastX}
        x2={Math.min(right, forecastX + YEARLY_STUB_LENGTH)}
        y1={forecastY}
        y2={forecastY}
        stroke="var(--demand-forecast)"
        strokeWidth={2.4}
        strokeDasharray="6 3"
      />
    </g>
  );
}

export default function ForecastLineChart({
  points,
  ariaLabel,
  compact = false,
  includeConfidence = false,
}) {
  const { language, t } = useLanguage();
  const yAxisDomain = getDemandChartYAxisDomain(points, { includeConfidence });
  const chartPoints = points.map((point) => ({
    ...point,
    confidence_range:
      point.confidence_low == null || point.confidence_high == null
        ? null
        : [point.confidence_low, point.confidence_high],
  }));
  const transition = buildDemandTransitionData(chartPoints);
  const data = transition.data;
  const isYearly = data.length === 2
    && data[0]?.label === "Y-1"
    && data[1]?.label === "Y+1";
  // The series ends actuals at its final historical point and starts forecast
  // at its first genuine forecast point. The legacy fixture may also carry an
  // equal-valued connector point; in both cases the marker belongs on the
  // first genuine forecast point.
  const boundary = transition.firstForecastKey;
  const hasConfidenceBand = data.some(
    (point) => point.confidence_low != null && point.confidence_high != null,
  );

  return (
    <div className={`demand-forecast-chart${compact ? " demand-forecast-chart--compact" : ""}`} role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 16, left: 2, bottom: 2 }}>
          <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            padding={isYearly ? { left: YEARLY_PLOT_INSET, right: YEARLY_PLOT_INSET } : undefined}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={{ stroke: "var(--line)" }}
            minTickGap={18}
          />
          <YAxis
            domain={yAxisDomain}
            tickCount={5}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={false}
            width={58}
            tickFormatter={(value) => formatNumber(value, language, { maximumFractionDigits: 0 })}
          />
          <Tooltip content={<DemandTooltip />} />
          {hasConfidenceBand ? (
            <Area
              type="monotone"
              dataKey="confidence_range"
              stroke="none"
              fill="var(--demand-band)"
              fillOpacity={0.32}
              isAnimationActive={false}
            />
          ) : null}
          {boundary ? (
            <ReferenceLine
              x={boundary}
              stroke="var(--demand-boundary)"
              strokeDasharray="4 4"
              label={{ value: t("Forecast starts"), position: "insideTopRight", dy: -4, fontSize: 10, fill: "var(--muted)" }}
            />
          ) : null}
          <Line type="monotone" dataKey="actual" name={t("Actual")} stroke="var(--demand-actual)" strokeWidth={2.4} dot={false} connectNulls={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="forecast" name={t("AI Forecast")} stroke="var(--demand-forecast)" strokeWidth={2.4} strokeDasharray="6 3" dot={false} connectNulls={false} isAnimationActive={false} />
          <Line
            type="linear"
            dataKey="forecast_transition"
            name=""
            stroke="var(--demand-forecast)"
            strokeWidth={1.6}
            strokeDasharray="2 3"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
            legendType="none"
          />
          <YearlyVisualStubs enabled={isYearly} points={data} />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="demand-chart-legend" aria-hidden="true">
        <span className="actual">{t("Actual")}</span>
        <span className="forecast">{t("AI Forecast")}</span>
        {hasConfidenceBand ? <span className="band">{t("Confidence band")}</span> : null}
      </div>
    </div>
  );
}
