import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

function TrendTooltip({ active, payload }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div className="demand-chart-tooltip">
      <strong>{item.sku_name}</strong>
      <span>{t("Predicted uplift")}: +{formatNumber(item.predicted_uplift_pct, language, { maximumFractionDigits: 1 })}%</span>
      <span>ADS: {formatNumber(item.ads_units_per_day, language, { maximumFractionDigits: 1 })} {t("units/day")}</span>
      <span>{item.signals.map(t).join(" · ")}</span>
    </div>
  );
}

export default function PredictedTrendPanel({ items, onSelect }) {
  const { language, t } = useLanguage();
  return (
    <section className="demand-panel demand-trend-panel" aria-labelledby="demand-trend-title">
      <header className="demand-panel-head">
        <div>
          <p>{t("Emerging demand")}</p>
          <h2 id="demand-trend-title">{t("Predicted to trend")}</h2>
          <span>{t("Top items by expected demand uplift")}</span>
        </div>
      </header>
      {items.length ? (
        <>
          <div className="demand-trend-chart" role="img" aria-label={t("Predicted-to-trend ranking chart")}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={items} layout="vertical" margin={{ top: 4, right: 22, bottom: 4, left: 4 }}>
                <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10, fill: "var(--muted)" }} tickFormatter={(value) => `${value}%`} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="sku_name" width={112} tick={{ fontSize: 9, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                <Tooltip content={<TrendTooltip />} />
                <Bar dataKey="predicted_uplift_pct" fill="var(--demand-trend)" radius={[0, 5, 5, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ul className="demand-trend-list">
            {items.slice(0, 5).map((item) => (
              <li key={item.sku_id}>
                <button type="button" onClick={() => onSelect(item.sku_id)}>
                  <span>
                    <strong>{item.sku_name}</strong>
                    <small>{item.signals.map(t).join(" · ")}</small>
                  </span>
                  <b>+{formatNumber(item.predicted_uplift_pct, language, { maximumFractionDigits: 1 })}%</b>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : <p className="workboard-empty">{t("No trending items match the current scope.")}</p>}
    </section>
  );
}
