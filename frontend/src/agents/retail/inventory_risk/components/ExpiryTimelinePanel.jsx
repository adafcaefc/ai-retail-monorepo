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
import { formatUnits } from "../presentation.js";

function BucketTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  return (
    <div className="risk-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("Units at risk")}: {formatUnits(payload[0].value, language)}
      </span>
    </div>
  );
}

/**
 * A2 spec section 6 (`#ch-dim-sea`): fresh units bucketed by remaining
 * shelf-life, plus the shortest-dated watchlist.
 *
 * This one is thin on purpose rather than by accident — only perishable SKUs
 * carrying expiry units participate, and in this dataset that is a handful of
 * Grocery lines. An empty state is the honest render for every other scope,
 * not a bug to pad with zeros.
 */
export default function ExpiryTimelinePanel({ timeline, onSelect }) {
  const { language, t } = useLanguage();
  const total = timeline.buckets.reduce((running, bucket) => running + bucket.units, 0);

  return (
    <section className="risk-panel risk-expiry" aria-label={t("Expiry timeline")}>
      <header className="risk-panel-head">
        <h3>{t("Expiry timeline")}</h3>
        <span className="risk-panel-note">
          {formatUnits(Math.round(total), language)} {t("units")}
        </span>
      </header>

      {total === 0 ? (
        <p className="risk-empty">{t("No expiry exposure in the current scope.")}</p>
      ) : (
        <>
          <div className="risk-chart" role="img" aria-label={t("Expiry timeline")}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={timeline.buckets.map((bucket) => ({ ...bucket, name: t(bucket.label) }))}
                margin={{ top: 6, right: 8, left: 0, bottom: 4 }}
              >
                <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "var(--muted)" }}
                  tickLine={false}
                  axisLine={{ stroke: "var(--line)" }}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "var(--muted)" }}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                  tickFormatter={(value) => formatUnits(value, language)}
                />
                <Tooltip cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }} content={<BucketTooltip />} />
                <Bar dataKey="units" fill="var(--risk-expiry)" isAnimationActive={true} animationDuration={300} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <ul className="risk-watchlist">
            {timeline.watchlist.map((item) => (
              <li key={item.sku_id}>
                <button type="button" onClick={() => onSelect(item.sku_id)}>
                  <span className="risk-watchlist-sku">{item.sku_id}</span>
                  <span className="risk-watchlist-name">{item.name}</span>
                  <span className="risk-watchlist-days">{item.shelf_life_days}d</span>
                  <span className="risk-watchlist-units">
                    {formatUnits(Math.round(item.units), language)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
