import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { categoryColor, formatIdr } from "../presentation.js";

/**
 * How many categories get their own stacked segment before the tail is
 * collapsed. A vertical carries twenty categories and the whole chain carries
 * a hundred and sixty; past half a dozen the segments are thinner than their
 * own border and the legend stops being readable.
 */
const TOP_CATEGORIES = 6;
const OTHER_KEY = "__other__";

function topCategories(rows) {
  const totals = new Map();
  for (const row of rows) {
    for (const segment of row.segments) {
      totals.set(
        segment.category_id,
        (totals.get(segment.category_id) ?? 0) + segment.value,
      );
    }
  }
  return [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_CATEGORIES)
    .map(([categoryId]) => categoryId);
}

function StateTooltip({ active, payload, label, labels }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const shown = payload.filter((entry) => entry.value > 0);
  const total = shown.reduce((running, entry) => running + entry.value, 0);

  return (
    <div className="risk-chart-tooltip">
      <strong>{t(label)}</strong>
      {shown.map((entry) => (
        <span key={entry.dataKey}>
          {labels.get(entry.dataKey) ?? t("Other")}:{" "}
          {formatIdr(entry.value, language)}
        </span>
      ))}
      <span className="risk-tooltip-total">
        {t("Total")}: {formatIdr(total, language)}
      </span>
    </div>
  );
}

/**
 * A2 spec section 5a: one horizontal bar per state, segmented by category.
 * Value is `Position × price` for every SKU in that state — see
 * AT_RISK_VALUE_NOTE, it is exposure at full position value, not expected loss.
 */
export default function AtRiskByStatePanel({ rows }) {
  const { language, t } = useLanguage();

  if (!rows.length) {
    return (
      <section className="risk-panel" aria-label={t("At-risk value by state")}>
        <header className="risk-panel-head">
          <h3>{t("At-risk value by state")}</h3>
        </header>
        <p className="risk-empty">{t("No SKUs match the current scope.")}</p>
      </section>
    );
  }

  const keep = topCategories(rows);
  const labels = new Map();
  const data = rows.map((row) => {
    const point = { state: row.state, total: row.total };
    for (const segment of row.segments) {
      if (keep.includes(segment.category_id)) {
        point[segment.category_id] = segment.value;
        labels.set(segment.category_id, segment.label);
      } else {
        point[OTHER_KEY] = (point[OTHER_KEY] ?? 0) + segment.value;
      }
    }
    return point;
  });

  const hasOther = data.some((point) => point[OTHER_KEY] > 0);
  const series = hasOther ? [...keep, OTHER_KEY] : keep;

  return (
    <section className="risk-panel" aria-label={t("At-risk value by state")}>
      <header className="risk-panel-head">
        <h3>{t("At-risk value by state")}</h3>
        <span className="risk-panel-note">{t("Chain-net, full position value")}</span>
      </header>

      <div className="risk-chart risk-chart--tall" role="img" aria-label={t("At-risk value by state")}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--line)" }}
              tickFormatter={(value) => formatIdr(value, language, { digits: 0 })}
            />
            <YAxis
              type="category"
              dataKey="state"
              width={86}
              tick={{ fontSize: 11, fill: "var(--ink)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => t(value)}
            />
            <Tooltip
              cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }}
              content={<StateTooltip labels={labels} />}
            />
            {series.map((key, index) => (
              <Bar
                key={key}
                dataKey={key}
                stackId="value"
                fill={key === OTHER_KEY ? "var(--gray-400)" : categoryColor(index)}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="risk-legend" aria-hidden="true">
        {series.map((key, index) => (
          <li key={key}>
            <i
              style={{
                background: key === OTHER_KEY ? "var(--gray-400)" : categoryColor(index),
              }}
            />
            {key === OTHER_KEY ? t("Other categories") : labels.get(key)}
          </li>
        ))}
      </ul>
    </section>
  );
}
