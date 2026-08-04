import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import {
  numberLocale,
  translateUnit
} from "../format.js";
import { useLanguage } from "../LanguageProvider.jsx";


// Categorical fallback for series/slices with no business meaning attached
// (an arbitrary 4th product, an unlabelled pie slice). Sourced from the same
// ramps as styles.css's --blue-*/--gray-* tokens rather than an unrelated
// palette, and deliberately leaves out --green-500/--amber-500/--red-500 —
// those already mean "good/warn/bad" on every KPI tile, so reusing them here
// would fake a status signal on a category that isn't one. "Scenario" purple
// and the indigo below are the two accents this app already treats as
// meaning-free chart colour (see resolvePointColor's "scenario" match and
// getBusinessColor's "top 5"/"customer a" entries further down).
const DEFAULT_COLORS = [
  "#175cd3", // --blue-500
  "#7a52b3", // scenario purple
  "#12469e", // --blue-600
  "#3b4a68", // --gray-700
  "#0f3b85", // --blue-700
  "#5b5fc7", // indigo
  "#0e7490"  // teal — chart-only, sits between blue and green without touching --green-500
];


export default function ChartRenderer({
  data,
  variant = "default"
}) {
  const { language } =
    useLanguage();

  const chartPayload =
    normalizeChartPayload(data);

  const size =
    resolveChartSize(variant);

  if (!chartPayload.rows.length) {
    return (
      <section className="chart-empty">
        <strong>
          Chart cannot be displayed.
        </strong>

        <span>
          The chart payload does not
          contain valid numeric data.
        </span>
      </section>
    );
  }

  return (
    <section
      className={
        "chart-card" +
        (variant !== "default"
          ? ` chart-card--${variant}`
          : "")
      }
    >
      <ChartHeader
        title={chartPayload.title}
        subtitle={chartPayload.subtitle}
        tag={chartPayload.tag}
      />

      <div className="chart-container">
        <ChartByType
          payload={chartPayload}
          size={size}
          language={language}
        />
      </div>

      {chartPayload.note && (
        <footer className="chart-note">
          {chartPayload.note}
        </footer>
      )}
    </section>
  );
}

function resolveChartSize(variant) {
  if (variant === "compact") {
    return {
      mode: "fill",
      height: "100%",
      bar: "100%",
      line: "100%",
      area: "100%",
      waterfall: "100%",
      circular: "100%",
      pieInner: "42%",
      pieOuter: "68%",
      margin: {
        top: 12,
        right: 8,
        bottom: 8,
        left: 0
      },
      showLegend: false
    };
  }

  if (variant === "fill") {
    return {
      mode: "fill",
      height: "100%",
      bar: "100%",
      line: "100%",
      area: "100%",
      waterfall: "100%",
      circular: "100%",
      pieInner: "48%",
      pieOuter: "72%",
      margin: {
        top: 18,
        right: 14,
        bottom: 12,
        left: 4
      },
      showLegend: true
    };
  }

  return {
    mode: "fixed",
    height: null,
    bar: null,
    line: 280,
    area: 260,
    waterfall: 280,
    circular: 260,
    pieInner: 56,
    pieOuter: 92,
    margin: null,
    showLegend: true
  };
}


function ChartHeader({
  title,
  subtitle,
  tag
}) {
  return (
    <header className="chart-card-header">
      <div>
        <h3>
          {title || "Financial chart"}
        </h3>

        {subtitle && (
          <p>
            {subtitle}
          </p>
        )}
      </div>

      {tag && (
        <span className="chart-tag">
          {tag}
        </span>
      )}
    </header>
  );
}


function ChartByType({
  payload,
  size,
  language
}) {
  switch (payload.chartType) {
    case "line":
      return (
        <LineChartView
          payload={payload}
          size={size}
          language={language}
        />
      );

    case "area":
      return (
        <AreaChartView
          payload={payload}
          size={size}
          language={language}
        />
      );

    case "pie":
    case "donut":
      return (
        <CircularChartView
          payload={payload}
          size={size}
          language={language}
        />
      );

    case "waterfall":
      return (
        <WaterfallChartView
          payload={payload}
          size={size}
          language={language}
        />
      );

    case "bar":
    default:
      return (
        <BarChartView
          payload={payload}
          size={size}
          language={language}
        />
      );
  }
}


function BarChartView({
  payload,
  size,
  language
}) {
  const {
    rows,
    series,
    target,
    targetLabel,
    unit
  } = payload;

  const hasLongLabels =
    rows.some(
      (row) =>
        String(row.name).length > 16
    );

  const isCompact =
    rows.length <= 6;

  const chartHeight =
    size.mode === "fill"
      ? size.bar
      : hasLongLabels
        ? 235
        : isCompact
          ? 220
          : 300;

  const margin =
    size.margin || {
      top: 28,
      right: 18,
      bottom:
        hasLongLabels
          ? 58
          : 24,
      left: 4
    };

  return (
    <ResponsiveContainer
      width="100%"
      height={chartHeight}
      debounce={80}
    >
      <BarChart
        data={rows}

        margin={{
          ...margin,
          // A value label sits 8px above the tallest bar in 10px type, so it
          // needs ~26px of headroom. The compact variant's 12px top margin
          // clipped the label in half ("7,845" losing its upper row).
          top: payload.showValues
            ? Math.max(margin.top || 0, 26)
            : margin.top,
          bottom:
            hasLongLabels
              ? Math.max(
                  margin.bottom || 0,
                  size.mode === "fill"
                    ? 36
                    : 58
                )
              : margin.bottom
        }}

        barCategoryGap="24%"
      >
        <CartesianGrid
          vertical={false}
          stroke="#edf0f5"
        />

        <XAxis
          dataKey="name"

          axisLine={{
            stroke: "#d7dee9"
          }}

          tickLine={false}
          interval={0}

          angle={
            hasLongLabels
              ? -16
              : 0
          }

          textAnchor={
            hasLongLabels
              ? "end"
              : "middle"
          }

          height={
            hasLongLabels
              ? size.mode === "fill"
                ? 42
                : 62
              : 34
          }

          tick={{
            fontSize:
              size.mode === "fill"
                ? 9
                : 9,
            fill: "#62708a"
          }}
        />

        <YAxis
          axisLine={false}
          tickLine={false}
          width={
            size.mode === "fill"
              ? 48
              : 64
          }

          tick={{
            fontSize: 10,
            fill: "#8a8f9c"
          }}

          tickFormatter={
            (value) =>
              formatAxisNumber(value, language)
          }
        />

        <Tooltip
          cursor={{
            fill:
              "rgba(122, 82, 179, 0.06)"
          }}

          content={
            <CustomTooltip
              unit={unit}
              language={language}
            />
          }
        />

        {series.length > 1 &&
          size.showLegend && (
          <Legend
            verticalAlign="top"
            align="right"

            wrapperStyle={{
              paddingBottom: 12,
              fontSize: 11
            }}
          />
        )}

        {Number.isFinite(target) && (
          <ReferenceLine
            y={target}

            stroke="#888888"
            strokeWidth={1.4}
            strokeDasharray="5 4"

            label={{
              value:
                targetLabel ||
                `Target ${formatFullNumber(
                  target,
                  language
                )}`,

              position:
                "insideTopRight",

              fill: "#666666",
              fontSize: 10,
              fontWeight: 700
            }}
          />
        )}

        {series.map(
          (
            seriesDefinition,
            seriesIndex
          ) => (
            <Bar
              key={
                seriesDefinition.key
              }

              dataKey={
                seriesDefinition.key
              }

              name={
                seriesDefinition.name
              }

              maxBarSize={
                size.mode === "fill"
                  ? 56
                  : 52
              }

              radius={[
                4,
                4,
                0,
                0
              ]}

              isAnimationActive
              animationDuration={450}
            >
              {rows.map(
                (row, rowIndex) => (
                  <Cell
                    key={
                      `${seriesDefinition.key}-${row.name}-${rowIndex}`
                    }

                    fill={
                      getRowColor({
                        row,
                        rowIndex,
                        seriesIndex,
                        payload
                      })
                    }
                  />
                )
              )}

              {payload.showValues && (
                <LabelList
                  dataKey={
                    seriesDefinition.key
                  }

                  position="top"

                  content={
                    <ChartValueLabel language={language} />
                  }
                />
              )}
            </Bar>
          )
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}

function WaterfallChartView({
  payload,
  size,
  language
}) {
  const {
    unit
  } = payload;

  const waterfallRows =
    buildWaterfallRows(
      payload.rows
    );

  const hasLongLabels =
    waterfallRows.some(
      (row) =>
        String(
          row.name
        ).length > 14
    );

  const chartHeight =
    size.mode === "fill"
      ? size.waterfall
      : size.waterfall || 280;

  const margin =
    size.margin || {
      top: 38,
      right: 24,
      bottom:
        hasLongLabels
          ? 82
          : 42,
      left: 12
    };

  return (
    <ResponsiveContainer
      width="100%"
      height={chartHeight}
      debounce={80}
    >
      <BarChart
        data={waterfallRows}
        margin={{
          ...margin,
          // Same headroom rule as BarChartView: the fill/compact variants
          // pass a 12-18px top margin, which clips the value labels.
          top: payload.showValues
            ? Math.max(margin.top || 0, 26)
            : margin.top,
          bottom:
            hasLongLabels
              ? Math.max(
                  margin.bottom || 0,
                  size.mode === "fill"
                    ? 48
                    : 82
                )
              : margin.bottom
        }}
        barCategoryGap="24%"
      >
        <CartesianGrid
          vertical={false}
          stroke="#edf0f5"
        />

        <XAxis
          dataKey="name"
          axisLine={{
            stroke: "#d7dee9"
          }}
          tickLine={false}
          interval={0}
          angle={
            hasLongLabels
              ? -22
              : 0
          }
          textAnchor={
            hasLongLabels
              ? "end"
              : "middle"
          }
          height={
            hasLongLabels
              ? size.mode === "fill"
                ? 56
                : 90
              : 44
          }
          tick={{
            fontSize: 10,
            fill: "#62708a"
          }}
        />

        <YAxis
          axisLine={false}
          tickLine={false}
          width={
            size.mode === "fill"
              ? 48
              : 56
          }
          
          domain={[
            0,
            (dataMax) =>
              Math.ceil(
                dataMax*1.15
              )
          ]}

          tick={{
            fontSize: 9,
            fill: "#8a8f9c"
          }}

          tickFormatter={
            (value) =>
              formatAxisNumber(value, language)
          }
        />

        <ReferenceLine
          y={0}
          stroke="#98a2b3"
          strokeWidth={1}
        />

        <Tooltip
          cursor={{
            fill:
              "rgba(23, 92, 211, 0.06)"
          }}
          content={
            <WaterfallTooltip
              unit={unit}
              language={language}
            />
          }
        />

        <Bar
          dataKey="base"
          stackId="waterfall"
          fill="transparent"
          isAnimationActive={false}
        />

        <Bar
          dataKey="change"
          stackId="waterfall"
          maxBarSize={
            size.mode === "fill"
              ? 58
              : 66
          }
          radius={[4, 4, 0, 0]}
          isAnimationActive
          animationDuration={450}
        >
          {waterfallRows.map(
            (row, index) => (
              <Cell
                key={
                  `${row.name}-${index}`
                }
                fill={row.color}
              />
            )
          )}

          {payload.showValues && (
            <LabelList
              dataKey="displayValue"
              position="top"
              formatter={
                (value) =>
                  formatChartValue(value, language)
              }
              fill="#344054"
              fontSize={10}
              fontWeight={700}
            />
          )}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}


// Opening and closing bars are anchors, not drivers — neither is a "good" or
// "bad" movement, so both share one neutral colour instead of the previous
// purple/cyan pair, which spent two extra hues on values that carry the same
// meaning. Only the bars in between are positive/negative, and those now use
// the app's real --green-500/--red-500 instead of an unrelated green/red.
const WATERFALL_ANCHOR_COLOR = "#3b4a68"; // --gray-700
const WATERFALL_POSITIVE_COLOR = "#18794e"; // --green-500
const WATERFALL_NEGATIVE_COLOR = "#d92d20"; // --red-500
const WATERFALL_EMPTY_COLOR = "#9aa7bd"; // --gray-400

function buildWaterfallRows(
  rows
) {
  let runningTotal = 0;

  return rows.map(
    (row, index) => {
      const numericValue =
        Number(row.value);

      const isFirst =
        index === 0;

      const isLast =
        index ===
        rows.length - 1;

      if (
        !Number.isFinite(
          numericValue
        )
      ) {
        return {
          name: row.name,
          base: 0,
          change: 0,
          displayValue: 0,
          color: WATERFALL_EMPTY_COLOR,
          kind: "empty"
        };
      }

      if (isFirst) {
        runningTotal =
          numericValue;

        return {
          name: row.name,
          base: 0,
          change: numericValue,
          displayValue:
            numericValue,
          color: WATERFALL_ANCHOR_COLOR,
          kind: "opening"
        };
      }

      if (isLast) {
        return {
          name: row.name,
          base: 0,
          change: numericValue,
          displayValue:
            numericValue,
          color: WATERFALL_ANCHOR_COLOR,
          kind: "closing"
        };
      }

      const previousTotal =
        runningTotal;

      const nextTotal =
        runningTotal +
        numericValue;

      const base =
        Math.min(
          previousTotal,
          nextTotal
        );

      const change =
        Math.abs(
          numericValue
        );

      runningTotal =
        nextTotal;

      return {
        name: row.name,
        base,
        change,
        displayValue:
          numericValue,

        color:
          numericValue >= 0
            ? WATERFALL_POSITIVE_COLOR
            : WATERFALL_NEGATIVE_COLOR,

        kind:
          numericValue >= 0
            ? "positive"
            : "negative"
      };
    }
  );
}


function WaterfallTooltip({
  active,
  payload,
  label,
  unit,
  language
}) {
  if (
    !active ||
    !Array.isArray(payload) ||
    !payload.length
  ) {
    return null;
  }

  const row =
    payload.find(
      (item) =>
        item.dataKey ===
        "change"
    )?.payload ||
    payload[0]?.payload;

  if (!row) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <strong>
        {label}
      </strong>

      <div className="chart-tooltip-row">
        <span
          className="chart-tooltip-dot"
          style={{
            background:
              row.color ||
              WATERFALL_ANCHOR_COLOR
          }}
        />

        <span>
          {getWaterfallTooltipLabel(
            row.kind
          )}
        </span>

        <b>
          {formatFullNumber(
            row.displayValue,
            language
          )}

          {unit
            ? ` ${translateUnit(unit, language)}`
            : ""}
        </b>
      </div>
    </div>
  );
}

function getWaterfallTooltipLabel(
  kind
) {
  if (kind === "opening") {
    return "Opening value";
  }

  if (kind === "closing") {
    return "Closing value";
  }

  if (kind === "positive") {
    return "Positive driver";
  }

  if (kind === "negative") {
    return "Negative driver";
  }

  return "Value";
}


function LineChartView({
  payload,
  size,
  language
}) {
  const {
    rows,
    series,
    target,
    targetLabel,
    unit,
    highlight
  } = payload;

  // The filter layer sends `highlight` instead of dropping points: a curve
  // filtered to one week is one stranded dot, but a marked week keeps its
  // whole context around it.
  const highlightRow =
    highlight
      ? rows.find(
          (row) =>
            row.name === highlight
        )
      : null;

  const chartHeight =
    size.mode === "fill"
      ? size.line
      : size.line || 280;

  const margin =
    size.margin || {
      top: 20,
      right: 24,
      bottom: 28,
      left: 8
    };

  return (
    <ResponsiveContainer
      width="100%"
      height={chartHeight}
      debounce={80}
    >
      <LineChart
        data={rows}

        margin={margin}
      >
        <CartesianGrid
          vertical={false}
          stroke="#edf0f5"
        />

        <XAxis
          dataKey="name"
          axisLine={{
            stroke: "#d7dee9"
          }}
          tickLine={false}
          tick={{
            fontSize: 10,
            fill: "#62708a"
          }}
        />

        <YAxis
          axisLine={false}
          tickLine={false}
          width={
            size.mode === "fill"
              ? 48
              : 64
          }
          domain={[
            (dataMin) =>
              Math.floor(
                Math.min(
                  dataMin,
                  Number.isFinite(target)
                    ? target
                    : dataMin
                ) * 0.92
              ),
            (dataMax) =>
              Math.ceil(
                Math.max(
                  dataMax,
                  Number.isFinite(target)
                    ? target
                    : dataMax
                ) * 1.08
              )
          ]}
          tickFormatter={
            (value) =>
              formatAxisNumber(value, language)
          }
          tick={{
            fontSize: 10,
            fill: "#8a8f9c"
          }}
        />

        <Tooltip
          content={
            <CustomTooltip
              unit={unit}
              language={language}
            />
          }
        />

        {size.showLegend && (
          <Legend
            verticalAlign="top"
            align="right"

            wrapperStyle={{
              paddingBottom: 8,
              fontSize: 11
            }}
          />
        )}

        {Number.isFinite(target) && (
          <ReferenceLine
            y={target}
            stroke="#888888"
            strokeWidth={1.4}
            strokeDasharray="5 4"

            label={{
              value:
                targetLabel ||
                `Target ${formatFullNumber(
                  target,
                  language
                )}`,

              position:
                "insideTopRight",

              fill: "#666666",
              fontSize: 10,
              fontWeight: 700
            }}
          />
        )}

        {highlightRow && (
          <ReferenceLine
            x={highlightRow.name}
            stroke="#7a52b3"
            strokeWidth={1.6}
            strokeDasharray="4 3"

            label={{
              value:
                `${highlightRow.name} · ${formatChartValue(
                  highlightRow.value,
                  language
                )}`,

              position: "top",

              fill: "#7a52b3",
              fontSize: 10,
              fontWeight: 700
            }}
          />
        )}

        {series.map(
          (
            seriesDefinition,
            index
          ) => (
            <Line
              key={
                seriesDefinition.key
              }

              type="monotone"

              dataKey={
                seriesDefinition.key
              }

              name={
                seriesDefinition.name
              }

              stroke={
                seriesDefinition.color ||
                DEFAULT_COLORS[
                  index %
                    DEFAULT_COLORS.length
                ]
              }

              strokeWidth={3}

              dot={{
                r: 3,
                strokeWidth: 2,
                fill: "#ffffff"
              }}

              activeDot={{
                r: 5
              }}

              connectNulls
            />
          )
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}


function AreaChartView({
  payload,
  size,
  language
}) {
  const {
    rows,
    series,
    target,
    targetLabel,
    unit
  } = payload;

  const chartHeight =
    size.mode === "fill"
      ? size.area
      : size.area || 260;

  const margin =
    size.margin || {
      top: 24,
      right: 20,
      bottom: 28,
      left: 8
    };

  return (
    <ResponsiveContainer
      width="100%"
      height={chartHeight}
      debounce={80}
    >
      <AreaChart
        data={rows}

        margin={margin}
      >
        <CartesianGrid
          vertical={false}
          stroke="#edf0f5"
        />

        <XAxis
          dataKey="name"
          axisLine={{
            stroke: "#d7dee9"
          }}
          tickLine={false}
          tick={{
            fontSize: 10,
            fill: "#62708a"
          }}
        />

        <YAxis
          axisLine={false}
          tickLine={false}
          width={
            size.mode === "fill"
              ? 48
              : 64
          }
          tickFormatter={
            (value) =>
              formatAxisNumber(value, language)
          }
        />

        <Tooltip
          content={
            <CustomTooltip
              unit={unit}
              language={language}
            />
          }
        />

        {size.showLegend && (
          <Legend
            verticalAlign="top"
            align="right"

            wrapperStyle={{
              paddingBottom: 8,
              fontSize: 11
            }}
          />
        )}

        {Number.isFinite(target) && (
          <ReferenceLine
            y={target}
            stroke="#888888"
            strokeWidth={1.4}
            strokeDasharray="5 4"

            label={{
              value:
                targetLabel ||
                `Target ${formatFullNumber(
                  target,
                  language
                )}`,

              position:
                "insideTopRight",

              fill: "#666666",
              fontSize: 10,
              fontWeight: 700
            }}
          />
        )}

        {series.map(
          (
            seriesDefinition,
            index
          ) => {
            const color =
              seriesDefinition.color ||
              DEFAULT_COLORS[
                index %
                  DEFAULT_COLORS.length
              ];

            return (
              <Area
                key={
                  seriesDefinition.key
                }

                type="monotone"

                dataKey={
                  seriesDefinition.key
                }

                name={
                  seriesDefinition.name
                }

                stroke={color}
                fill={color}
                fillOpacity={0.16}
                strokeWidth={3}
                connectNulls
              />
            );
          }
        )}
      </AreaChart>
    </ResponsiveContainer>
  );
}


function CircularChartView({
  payload,
  size,
  language
}) {
  const {
    rows,
    series,
    chartType,
    unit
  } = payload;

  const valueKey =
    series[0]?.key ||
    "value";

  const chartHeight =
    size.mode === "fill"
      ? size.circular
      : size.circular || 260;

  const innerRadius =
    chartType === "donut"
      ? size.pieInner
      : 0;

  return (
    <ResponsiveContainer
      width="100%"
      height={chartHeight}
      debounce={80}
    >
      <PieChart
        margin={{
          top: 4,
          right: 4,
          bottom: 4,
          left: 4
        }}
      >
        <Tooltip
          content={
            <CustomTooltip
              unit={unit}
              language={language}
            />
          }
        />

        {/*
          Slice names always ride in the legend, never as outside labels.
          Outside labels are laid out beyond the pie's radius, so in a short
          side card they escaped the card and covered whatever sat below.
        */}
        <Legend
          verticalAlign="bottom"
          height={22}
          iconSize={8}
          wrapperStyle={{
            fontSize: 10,
            lineHeight: "14px"
          }}
        />

        <Pie
          data={rows}
          dataKey={valueKey}
          nameKey="name"

          innerRadius={innerRadius}
          outerRadius={size.pieOuter}
          paddingAngle={2}

          label={<PieSliceLabel />}
          labelLine={false}
        >
          {rows.map(
            (row, index) => (
              <Cell
                key={
                  `${row.name}-${index}`
                }

                fill={
                  // "Others" is the aggregated remainder a filter leaves
                  // behind; it recedes so the chosen slice carries the chart.
                  row.muted
                    ? "#d7dee9" // --gray-200
                    : row.color ||
                      DEFAULT_COLORS[
                        index %
                          DEFAULT_COLORS.length
                      ]
                }
              />
            )
          )}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
  );
}


function ChartValueLabel({
  x,
  y,
  width,
  value,
  language
}) {
  const numericX =
    Number(x);

  const numericY =
    Number(y);

  const numericWidth =
    Number(width);

  if (
    !Number.isFinite(
      Number(value)
    )
  ) {
    return null;
  }

  return (
    <text
      x={
        numericX +
        numericWidth / 2
      }

      y={numericY - 8}

      textAnchor="middle"

      fill="#344054"
      fontSize={10}
      fontWeight={700}
    >
      {formatChartValue(value, language)}
    </text>
  );
}


function CustomTooltip({
  active,
  payload,
  label,
  unit,
  language
}) {
  if (
    !active ||
    !Array.isArray(payload) ||
    !payload.length
  ) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <strong>
        {label}
      </strong>

      {payload.map(
        (
          item,
          index
        ) => (
          <div
            key={
              `${item.name}-${index}`
            }

            className="chart-tooltip-row"
          >
            <span
              className="chart-tooltip-dot"

              style={{
                background:
                  item.payload?.color ||
                  item.color ||
                  "#7a52b3"
              }}
            />

            <span>
              {item.name}
            </span>

            <b>
              {formatFullNumber(
                item.value,
                language
              )}

              {unit
                ? ` ${translateUnit(unit, language)}`
                : ""}
            </b>
          </div>
        )
      )}
    </div>
  );
}


/**
 * Percentage drawn inside its own slice.
 *
 * Kept within the pie's radius by construction, so it can never overflow the
 * card the way Recharts' default outside labels did. Slices too thin to hold
 * a legible number are skipped — the legend and tooltip still name them.
 */
function PieSliceLabel({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  percent
}) {
  const pct =
    Math.round(
      Number(percent) * 100
    );

  if (
    !Number.isFinite(pct) ||
    pct < 8
  ) {
    return null;
  }

  const inner =
    Number(innerRadius) || 0;

  const outer =
    Number(outerRadius) || 0;

  // Mid-band for a donut, two-thirds out for a full pie — both stay clear
  // of the centre hole and of the outer edge.
  const radius =
    inner > 0
      ? inner + (outer - inner) * 0.5
      : outer * 0.62;

  const radians =
    (-Number(midAngle) * Math.PI) /
    180;

  const x =
    Number(cx) +
    radius * Math.cos(radians);

  const y =
    Number(cy) +
    radius * Math.sin(radians);

  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      dominantBaseline="central"
      fill="#ffffff"
      fontSize={10}
      fontWeight={800}
      style={{
        paintOrder: "stroke",
        stroke: "rgba(0, 0, 0, 0.28)",
        strokeWidth: 2.5
      }}
    >
      {pct}%
    </text>
  );
}


function normalizeChartPayload(
  rawPayload
) {
  const payload =
    rawPayload || {};

    let chartType =
    normalizeChartType(
      payload.chart_type ||
      payload.type
    );

  if (
    chartType === "bar" &&
    isBridgePayload(payload)
  ) {
    chartType = "waterfall";
  }

  const rawData =
    Array.isArray(payload.data)
      ? payload.data
      : [];

  const hasMultiSeries =
    rawData.length > 0 &&
    rawData.every(
      (item) =>
        item &&
        typeof item === "object" &&
        Array.isArray(
          item.values
        )
    );

  const normalized =
    hasMultiSeries
      ? normalizeMultiSeries(
          rawData
        )
      : normalizeSingleSeries(
          rawData,
          payload
        );

  const target =
    toFiniteNumber(
      payload.target ??
      payload.target_value,
      null
    );

  return {
    title:
      payload.title ||
      "Financial chart",

    // QC-035: the period is the subtitle unless the chart states its own, so
    // every chart says which span its numbers cover.
    subtitle:
      payload.subtitle ||
      payload.description ||
      payload.period ||
      "",

    tag:
      payload.tag ||
      getDefaultTag(
        chartType
      ),

    note:
      payload.note ||
      "",

    chartType,

    unit:
      payload.unit ||
      payload.y_axis_title ||
      "",

    target,

    targetLabel:
      payload.target_label ||
      "",

    showValues:
      payload.show_values !==
      false,

    // Set by the filter layer on line charts: the point to call out on the
    // intact curve, instead of filtering 12 of 13 weeks away.
    highlight:
      payload.highlight ||
      null,

    rows:
      normalized.rows,

    series:
      normalized.series
  };
}

function isBridgePayload(
  payload
) {
  const searchableText = [
    payload?.title,
    payload?.subtitle,
    payload?.description,
    payload?.tag,
    payload?.chart_type,
    payload?.type
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return (
    searchableText.includes(
      "ebitda bridge"
    ) ||
    searchableText.includes(
      "variance bridge"
    ) ||
    searchableText.includes(
      "waterfall"
    ) ||
    searchableText.includes(
      "bridge"
    )
  );
}

function normalizeSingleSeries(
  rawData,
  payload
) {
  const target =
    toFiniteNumber(
      payload.target ??
      payload.target_value,
      null
    );

  const rows = rawData
    .map(
      (
        point,
        index
      ) => {
        const value =
          getPointValue(point);

        const label =
          getPointLabel(
            point,
            index
          );

        return {
          name: label,

          value,

          // Set by the filter layer: the "Others" remainder a narrowed
          // donut aggregates its unselected slices into.
          muted:
            Boolean(point.muted),

          color:
            resolvePointColor({
              point,
              label,
              value,
              target,
              index
            })
        };
      }
    )
    .filter((row) =>
      Number.isFinite(
        row.value
      )
    );

  return {
    rows,

    series: [
      {
        key: "value",

        name:
          payload.series_name ||
          payload.y_axis_title ||
          "Value",

        color:
          payload.color ||
          "#7a52b3"
      }
    ]
  };
}


function normalizeMultiSeries(
  rawSeries
) {
  const rowMap =
    new Map();

  const series =
    rawSeries.map(
      (
        seriesDefinition,
        seriesIndex
      ) => {
        const seriesKey =
          `series_${seriesIndex}`;

        const seriesName =
          String(
            seriesDefinition.legend ||
            seriesDefinition.name ||
            `Series ${
              seriesIndex + 1
            }`
          );

        const seriesColor =
          seriesDefinition.color ||
          DEFAULT_COLORS[
            seriesIndex %
              DEFAULT_COLORS.length
          ];

        const values =
          Array.isArray(
            seriesDefinition.values
          )
            ? seriesDefinition.values
            : [];

        values.forEach(
          (
            point,
            pointIndex
          ) => {
            const label =
              getPointLabel(
                point,
                pointIndex
              );

            const value =
              getPointValue(point);

            if (
              !Number.isFinite(value)
            ) {
              return;
            }

            if (
              !rowMap.has(label)
            ) {
              rowMap.set(
                label,
                {
                  name: label
                }
              );
            }

            rowMap.get(label)[
              seriesKey
            ] = value;
          }
        );

        return {
          key: seriesKey,
          name: seriesName,
          color: seriesColor
        };
      }
    );

  return {
    rows:
      Array.from(
        rowMap.values()
      ),

    series
  };
}


function resolvePointColor({
  point,
  label,
  value,
  target,
  index
}) {
  if (point?.color) {
    return point.color;
  }

  const normalized =
    normalizeLabel(label);

  if (
    normalized.includes(
      "scenario"
    ) &&
    Number.isFinite(target)
  ) {
    return value <= target
      ? "#18794e" // --green-500
      : "#7a52b3";
  }

  return getBusinessColor(
    label,
    index
  );
}


// Business-term → colour lookup. Chart row labels are always plain English
// here by design — i18n.js's translatePayload explicitly leaves chart `data`
// untouched ("Numbers, chart data and ids are untouched — only wording
// changes"), so this matching is stable across the EN/ID toggle already.
// What it lacked was any connection to the app's real palette: every hex
// below now traces to the same --green-500/--amber-500/--amber-600/--red-500/
// --gray-900/--gray-500/--blue-200 tokens the KPI tiles and rest of the UI
// use, in the same hue family as before (red stays red, amber stays amber),
// so a receivables aging ramp (1-30 → 90+) now reads as a real green→amber→
// red escalation instead of three shades of orange that were hard to tell
// apart.
function getBusinessColor(
  label,
  index
) {
  const normalized =
    normalizeLabel(label);

  const exactColors = {
    current: "#172033", // --gray-900

    "1-30": "#18794e", // --green-500
    "31-60": "#b54708", // --amber-500
    "61-90": "#9a3d12", // --amber-600
    "90+": "#d92d20", // --red-500

    high: "#d92d20", // --red-500
    medium: "#b54708", // --amber-500
    low: "#18794e", // --green-500

    now: "#d92d20", // --red-500
    scenario: "#7a52b3", // chart-only accent, see DEFAULT_COLORS above
    target: "#bcd2f4", // --blue-200

    "cash freed": "#18794e", // --green-500
    "cash recovered": "#18794e", // --green-500
    "gross cash collected":
      "#18794e", // --green-500

    "discount cost":
      "#d92d20", // --red-500

    "customer a":
      "#7a52b3",

    "top 5":
      "#5b5fc7",

    "all overdue":
      "#18794e" // --green-500
  };

  if (
    exactColors[normalized]
  ) {
    return exactColors[
      normalized
    ];
  }

  const partialColors = [
    [
      "customer a",
      "#7a52b3"
    ],
    [
      "top 5",
      "#5b5fc7"
    ],
    [
      "all overdue",
      "#18794e"
    ],
    [
      "cash freed",
      "#18794e"
    ],
    [
      "cash recovered",
      "#18794e"
    ],
    [
      "discount cost",
      "#d92d20"
    ],
    [
      "high",
      "#d92d20"
    ],
    [
      "medium",
      "#b54708"
    ],
    [
      "low",
      "#18794e"
    ]
  ];

  const match =
    partialColors.find(
      ([part]) =>
        normalized.includes(part)
    );

  if (match) {
    return match[1];
  }

  return DEFAULT_COLORS[
    index %
      DEFAULT_COLORS.length
  ];
}


function getRowColor({
  row,
  rowIndex,
  seriesIndex,
  payload
}) {
  if (
    payload.series.length === 1
  ) {
    return (
      row.color ||
      DEFAULT_COLORS[
        rowIndex %
          DEFAULT_COLORS.length
      ]
    );
  }

  return (
    payload.series[
      seriesIndex
    ]?.color ||
    DEFAULT_COLORS[
      seriesIndex %
        DEFAULT_COLORS.length
    ]
  );
}


function getPointLabel(
  point,
  index
) {
  return String(
    point?.label ??
    point?.name ??
    point?.category ??
    point?.x ??
    point?.week ??
    point?.period ??
    `Item ${index + 1}`
  );
}


function getPointValue(point) {
  return Number(
    point?.value ??
    point?.y ??
    point?.amount ??
    point?.total
  );
}


function normalizeChartType(
  type
) {
  const normalized =
    String(type || "bar")
      .trim()
      .toLowerCase()
      .replace(
        /[\s-]+/g,
        "_"
      );

  if (
    normalized === "line"
  ) {
    return "line";
  }

  if (
    normalized === "area"
  ) {
    return "area";
  }

  if (
    normalized === "pie"
  ) {
    return "pie";
  }

  if (
    normalized === "donut" ||
    normalized === "doughnut"
  ) {
    return "donut";
  }

  if (
    normalized ===
      "waterfall" ||
    normalized ===
      "bridge" ||
    normalized ===
      "variance_bridge" ||
    normalized ===
      "ebitda_bridge"
  ) {
    return "waterfall";
  }

  return "bar";
}


function normalizeLabel(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}


function getDefaultTag(
  chartType
) {
  return `${chartType} chart`;
}


function toFiniteNumber(
  value,
  fallback
) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return fallback;
  }

  const numericValue =
    Number(value);

  return Number.isFinite(
    numericValue
  )
    ? numericValue
    : fallback;
}


function formatAxisNumber(value, language) {
  const numericValue =
    Number(value);

  if (
    !Number.isFinite(
      numericValue
    )
  ) {
    return String(value);
  }

  if (
    Math.abs(
      numericValue
    ) >= 1_000_000
  ) {
    return `${(
      numericValue /
      1_000_000
    ).toFixed(1)}M`;
  }

  if (
    Math.abs(
      numericValue
    ) >= 100_000
  ) {
    return `${Math.round(
      numericValue / 1_000
    )}K`;
  }

  return numericValue
    .toLocaleString(
      numberLocale(language),
      {
        maximumFractionDigits:
          Number.isInteger(
            numericValue
          )
            ? 0
            : 1
      }
    );
}


function formatChartValue(value, language) {
  const numericValue =
    Number(value);

  if (
    !Number.isFinite(
      numericValue
    )
  ) {
    return String(value);
  }

  return numericValue
    .toLocaleString(
      numberLocale(language),
      {
        maximumFractionDigits:
          Number.isInteger(
            numericValue
          )
            ? 0
            : 1
      }
    );
}


function formatFullNumber(value, language) {
  const numericValue =
    Number(value);

  if (
    !Number.isFinite(
      numericValue
    )
  ) {
    return String(value);
  }

  return numericValue
    .toLocaleString(
      numberLocale(language),
      {
        maximumFractionDigits: 2
      }
    );
}