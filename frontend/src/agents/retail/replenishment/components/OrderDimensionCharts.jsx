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
 * A3 spec sections 5b and 6 — the mockup's four dimension charts
 * (`ch-dim-cat`, `ch-dim-store`, `ch-dim-clu`, `ch-dim-le`).
 *
 * Store, cluster and legal-entity figures are GROSS: they sum each store's own
 * shortfall, where the chain-net headline nets surplus in one store against
 * shortage in another. The two will not add up, on purpose — the same caveat
 * Inventory Risk carries, for the same reason.
 *
 * ALL FOUR PANELS PLOT ONE MEASURE, `order_value_retail`.
 * The category panel used to plot `order_value_cost` while the other three
 * plotted retail. Both numbers are real and the workbook states each of them
 * (see the builder's module docstring), but they differ by about a fifth — so
 * a reader comparing the tallest category bar against the tallest cluster bar
 * was comparing a cost against a price. Store rows carry no trade price at
 * all, which settles which of the two the grid can share: retail. The cost
 * figure keeps its own home on the vendor sourcing panel, where a buyer wants
 * exactly that.
 */
export default function OrderDimensionCharts({
  byCategory,
  byStore,
  byCluster,
  byLegalEntity = [],
  onSelectCategory,
  onSelectLegalEntity,
}) {
  const { language, t } = useLanguage();

  return (
    <div className="po-dimension-grid">
      <Panel
        title="Order value by category"
        rows={byCategory}
        dataKey="order_value_retail"
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
      <Panel
        title="Order value by legal entity"
        rows={byLegalEntity}
        dataKey="order_value_retail"
        onSelect={onSelectLegalEntity}
      />
    </div>
  );
}
