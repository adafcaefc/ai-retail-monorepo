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
import { formatIdr, formatUnits } from "../presentation.js";

const TOP_N = 12;

function Panel({ title, rows, dataKey, onSelect, note }) {
  const { language, t } = useLanguage();
  const data = rows.slice(0, TOP_N);

  return (
    <article className="po-panel" aria-label={t(title)}>
      <header className="po-panel-head">
        <h3>{t(title)}</h3>
        {note ? <span className="po-panel-note">{note}</span> : null}
      </header>

      {data.length === 0 ? (
        <p className="po-empty">{t("Nothing in scope.")}</p>
      ) : (
        <div className="po-chart" role="img" aria-label={t(title)}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 12, left: 0, bottom: 4 }}
            >
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fontSize: 9, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => formatIdr(value, language)}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={116}
                tick={{ fontSize: 9, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--line)" }}
              />
              <Tooltip
                cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }}
                formatter={(value) => formatIdr(value, language)}
              />
              <Bar
                dataKey={dataKey}
                fill="var(--po-bar)"
                isAnimationActive={false}
                radius={[0, 4, 4, 0]}
                cursor={onSelect ? "pointer" : undefined}
                onClick={onSelect ? (entry) => onSelect(entry.id) : undefined}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </article>
  );
}

/**
 * A3 spec sections 5b and 6.
 *
 * Store and cluster figures are GROSS: they sum each store's own shortfall,
 * where the chain-net headline nets surplus in one store against shortage in
 * another. The two will not add up, on purpose — the same caveat Inventory
 * Risk carries, for the same reason.
 */
export default function OrderDimensionCharts({
  byCategory,
  byStore,
  byCluster,
  onSelectCategory,
}) {
  const { language, t } = useLanguage();

  return (
    <div className="po-dimension-grid">
      <Panel
        title="Order value by category"
        rows={byCategory}
        dataKey="order_value_cost"
        onSelect={onSelectCategory}
        note={`${t("top")} ${Math.min(TOP_N, byCategory.length)}`}
      />
      <Panel
        title="Order value by store"
        rows={byStore}
        dataKey="order_value_retail"
        note={`${formatUnits(byStore.length, language)} ${t("stores")}`}
      />
      <Panel
        title="Order value by cluster"
        rows={byCluster}
        dataKey="order_value_retail"
      />
    </div>
  );
}
