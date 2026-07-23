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


const DEFAULT_COLORS = [
  "#7a52b3",
  "#5b5fc7",
  "#2e8b57",
  "#ed7d31",
  "#c4314b",
  "#1f3864",
  "#06aed4"
];


export default function ChartRenderer({
  data
}) {
  const chartPayload =
    normalizeChartPayload(data);

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
    <section className="chart-card">
      <ChartHeader
        title={chartPayload.title}
        subtitle={chartPayload.subtitle}
        tag={chartPayload.tag}
      />

      <div className="chart-container">
        <ChartByType
          payload={chartPayload}
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
  payload
}) {
  switch (payload.chartType) {
    case "line":
      return (
        <LineChartView
          payload={payload}
        />
      );

    case "area":
      return (
        <AreaChartView
          payload={payload}
        />
      );

    case "pie":
    case "donut":
      return (
        <CircularChartView
          payload={payload}
        />
      );

    case "bar":
    default:
      return (
        <BarChartView
          payload={payload}
        />
      );
  }
}


function BarChartView({
  payload
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
    isCompact ? 285 : 360;

  return (
    <ResponsiveContainer
      width="100%"
      height={chartHeight}
    >
      <BarChart
        data={rows}

        margin={{
          top: 38,
          right: 24,
          bottom:
            hasLongLabels
              ? 82
              : 35,
          left: 12
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
              ? 90
              : 40
          }

          tick={{
            fontSize: 10,
            fill: "#62708a"
          }}
        />

        <YAxis
          axisLine={false}
          tickLine={false}
          width={64}

          tick={{
            fontSize: 10,
            fill: "#8a8f9c"
          }}

          tickFormatter={
            formatAxisNumber
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
            />
          }
        />

        {series.length > 1 && (
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
                  target
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

              maxBarSize={66}

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
                    <ChartValueLabel />
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


function LineChartView({
  payload
}) {
  const {
    rows,
    series,
    target,
    targetLabel,
    unit
  } = payload;

  return (
    <ResponsiveContainer
      width="100%"
      height={500}
    >
      <LineChart
        data={rows}

        margin={{
          top: 30,
          right: 24,
          bottom: 35,
          left: 12
        }}
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
          width={64}
          tickFormatter={
            formatAxisNumber
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
            />
          }
        />

        <Legend
          verticalAlign="top"
          align="right"

          wrapperStyle={{
            paddingBottom: 12,
            fontSize: 11
          }}
        />

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
                  target
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
                r: 4,
                strokeWidth: 2,
                fill: "#ffffff"
              }}

              activeDot={{
                r: 6
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
  payload
}) {
  const {
    rows,
    series,
    target,
    targetLabel,
    unit
  } = payload;

  return (
    <ResponsiveContainer
      width="100%"
      height={330}
    >
      <AreaChart
        data={rows}

        margin={{
          top: 30,
          right: 24,
          bottom: 35,
          left: 12
        }}
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
          width={64}
          tickFormatter={
            formatAxisNumber
          }
        />

        <Tooltip
          content={
            <CustomTooltip
              unit={unit}
            />
          }
        />

        <Legend
          verticalAlign="top"
          align="right"

          wrapperStyle={{
            paddingBottom: 12,
            fontSize: 11
          }}
        />

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
                  target
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
  payload
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

  return (
    <ResponsiveContainer
      width="100%"
      height={320}
    >
      <PieChart>
        <Tooltip
          content={
            <CustomTooltip
              unit={unit}
            />
          }
        />

        <Legend
          verticalAlign="bottom"
          wrapperStyle={{
            fontSize: 11
          }}
        />

        <Pie
          data={rows}
          dataKey={valueKey}
          nameKey="name"

          innerRadius={
            chartType === "donut"
              ? 64
              : 0
          }

          outerRadius={108}
          paddingAngle={2}

          label={
            payload.showValues
              ? renderPieLabel
              : false
          }

          labelLine={false}
        >
          {rows.map(
            (row, index) => (
              <Cell
                key={
                  `${row.name}-${index}`
                }

                fill={
                  row.color ||
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
  value
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
      {formatChartValue(value)}
    </text>
  );
}


function CustomTooltip({
  active,
  payload,
  label,
  unit
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
                item.value
              )}

              {unit
                ? ` ${unit}`
                : ""}
            </b>
          </div>
        )
      )}
    </div>
  );
}


function renderPieLabel({
  name,
  percent
}) {
  return (
    `${name} ` +
    `${Math.round(
      percent * 100
    )}%`
  );
}


function normalizeChartPayload(
  rawPayload
) {
  const payload =
    rawPayload || {};

  const chartType =
    normalizeChartType(
      payload.chart_type ||
      payload.type
    );

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

    subtitle:
      payload.subtitle ||
      payload.description ||
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

    rows:
      normalized.rows,

    series:
      normalized.series
  };
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
      ? "#2e8b57"
      : "#7a52b3";
  }

  return getBusinessColor(
    label,
    index
  );
}


function getBusinessColor(
  label,
  index
) {
  const normalized =
    normalizeLabel(label);

  const exactColors = {
    current: "#1f3864",

    "1-30": "#5b7aa8",
    "31-60": "#ed7d31",
    "61-90": "#d1603a",
    "90+": "#c4314b",

    high: "#c4314b",
    medium: "#ed7d31",
    low: "#2e8b57",

    now: "#c4314b",
    scenario: "#7a52b3",
    target: "#9aa0d6",

    "cash freed": "#2e8b57",
    "cash recovered": "#2e8b57",
    "gross cash collected":
      "#2e8b57",

    "discount cost":
      "#c4314b",

    "customer a":
      "#7a52b3",

    "top 5":
      "#5b5fc7",

    "all overdue":
      "#2e8b57"
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
      "#2e8b57"
    ],
    [
      "cash freed",
      "#2e8b57"
    ],
    [
      "cash recovered",
      "#2e8b57"
    ],
    [
      "discount cost",
      "#c4314b"
    ],
    [
      "high",
      "#c4314b"
    ],
    [
      "medium",
      "#ed7d31"
    ],
    [
      "low",
      "#2e8b57"
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


function normalizeChartType(type) {
  const normalized =
    String(
      type || "bar"
    )
      .trim()
      .toLowerCase();

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


function formatAxisNumber(value) {
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
      "en-US",
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


function formatChartValue(value) {
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
      "en-US",
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


function formatFullNumber(value) {
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
      "en-US",
      {
        maximumFractionDigits: 2
      }
    );
}