import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { categoryColor, formatIdr, formatPercent } from "../presentation.js";

/** Same reasoning as the stacked bar: a hundred and sixty slices is not a chart. */
const TOP_SLICES = 20;

function DonutTooltip({ active, payload }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const slice = payload[0].payload;
  return (
    <div className="risk-chart-tooltip">
      <strong>{slice.label}</strong>
      <span>{formatIdr(slice.value, language)}</span>
      <span>
        {t("Share")}: {formatPercent(slice.share, language)}
      </span>
    </div>
  );
}

/** A2 spec section 5b: share of inventory value by category. */
export default function CategoryValueDonut({ rows, total }) {
  const { language, t } = useLanguage();

  if (!rows.length) {
    return (
      <section className="risk-panel" aria-label={t("Inventory value by category")}>
        <header className="risk-panel-head">
          <h3>{t("Inventory value by category")}</h3>
        </header>
        <p className="risk-empty">{t("No SKUs match the current scope.")}</p>
      </section>
    );
  }

  const head = rows.slice(0, TOP_SLICES);
  const tail = rows.slice(TOP_SLICES);
  const data = tail.length
    ? [
        ...head,
        {
          category_id: "__other__",
          label: t("Other categories"),
          value: tail.reduce((running, row) => running + row.value, 0),
          share: tail.reduce((running, row) => running + row.share, 0),
        },
      ]
    : head;

  return (
    <section className="risk-panel" aria-label={t("Inventory value by category")}>
      <header className="risk-panel-head">
        <h3>{t("Inventory value by category")}</h3>
        <span className="risk-panel-note">{formatIdr(total, language)}</span>
      </header>

      <div className="risk-chart risk-chart--tall" role="img" aria-label={t("Inventory value by category")}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius="52%"
              outerRadius="82%"
              paddingAngle={1}
              stroke="var(--card, #fff)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {data.map((slice, index) => (
                <Cell
                  key={slice.category_id}
                  fill={
                    slice.category_id === "__other__"
                      ? "var(--gray-400)"
                      : categoryColor(index)
                  }
                />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <ul className="risk-legend" aria-hidden="true">
        {data.map((slice, index) => (
          <li key={slice.category_id}>
            <i
              style={{
                background:
                  slice.category_id === "__other__"
                    ? "var(--gray-400)"
                    : categoryColor(index),
              }}
            />
            {slice.label}
            <b>{formatPercent(slice.share, language, { digits: 0 })}</b>
          </li>
        ))}
      </ul>
    </section>
  );
}
