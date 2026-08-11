import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { GROSS_VS_NET_NOTE } from "../data/contract.js";
import { formatIdr, formatUnits } from "../presentation.js";

/** Stores are 160 wide; only the worst few are legible or interesting. */
const TOP_STORES = 12;

function ValueTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  return (
    <div className="risk-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("At-risk value")}: {formatIdr(payload[0].value, language)}
      </span>
    </div>
  );
}

function CountTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const point = payload[0].payload;
  return (
    <div className="risk-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("Stockout-risk SKUs")}: {formatUnits(point.stockout_risk_count, language)}
      </span>
      <span>
        {t("SKUs stocked")}: {formatUnits(point.sku_count, language)}
      </span>
      <span>
        {t("At-risk value")}: {formatIdr(point.at_risk_value, language)}
      </span>
    </div>
  );
}

function ValueBarChart({ data, xKey, onSelect, activeKey }) {
  const { language, t } = useLanguage();
  return (
    <div className="risk-chart" role="img" aria-label={t("At-risk value")}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey={xKey}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={{ stroke: "var(--line)" }}
            interval={0}
            angle={-18}
            textAnchor="end"
            height={44}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={false}
            width={58}
            tickFormatter={(value) => formatIdr(value, language, { digits: 0 })}
          />
          <Tooltip cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }} content={<ValueTooltip />} />
          <Bar
            dataKey="value"
            isAnimationActive={false}
            onClick={onSelect ? (point) => onSelect(point.payload) : undefined}
            cursor={onSelect ? "pointer" : undefined}
          >
            {data.map((point) => (
              <Cell
                key={point[xKey]}
                fill={
                  activeKey && point.selection_key === activeKey
                    ? "var(--accent-info-strong)"
                    : "var(--accent-info)"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * A2 spec section 6. Four breakdowns of the same exposure.
 *
 * These are GROSS per-store figures: they sum local pockets of risk, so their
 * totals sit above the chain-net headline in the KPI row. That is by design
 * (spec section 10 note 1) and the panel says so, because a reader who spots
 * the gap will otherwise file it as a reconciliation bug.
 */
export default function DimensionCharts({
  byCategory,
  byStore,
  byCluster,
  byLegalEntity,
  scope,
  onSelectCategory,
  onSelectLegalEntity,
}) {
  const { language, t } = useLanguage();

  const categoryData = byCategory.slice(0, 10).map((row) => ({
    ...row,
    name: row.label,
    selection_key: row.category_id,
  }));
  const clusterData = byCluster.map((row) => ({
    ...row,
    name: row.cluster,
    selection_key: row.cluster,
  }));
  const entityData = byLegalEntity.map((row) => ({
    ...row,
    name: row.label,
    selection_key: row.legal_entity_id,
  }));
  const storeData = byStore.slice(0, TOP_STORES).map((row) => ({
    ...row,
    name: row.label,
  }));

  return (
    <section className="risk-dimension-grid" aria-label={t("Risk by dimension")}>
      <article className="risk-panel">
        <header className="risk-panel-head">
          <h3>{t("At-risk value by category")}</h3>
          <span className="risk-panel-note">{t("Top 10")}</span>
        </header>
        <ValueBarChart
          data={categoryData}
          xKey="name"
          activeKey={scope.category_group}
          onSelect={(point) => onSelectCategory(point.selection_key)}
        />
      </article>

      <article className="risk-panel">
        <header className="risk-panel-head">
          <h3>{t("Stockout-risk by store")}</h3>
          <span className="risk-panel-note" title={t(GROSS_VS_NET_NOTE)}>
            {t("Gross · top 12")}
          </span>
        </header>
        <div className="risk-chart" role="img" aria-label={t("Stockout-risk by store")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={storeData} margin={{ top: 6, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="store_id"
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--line)" }}
                interval={0}
                height={30}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={false}
                width={34}
                tickFormatter={(value) => formatUnits(value, language)}
              />
              <Tooltip cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }} content={<CountTooltip />} />
              <Bar dataKey="stockout_risk_count" fill="var(--risk-stockout)" isAnimationActive={false} />
              <Bar dataKey="healthy_count" stackId="rest" fill="var(--gray-200)" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </article>

      <article className="risk-panel">
        <header className="risk-panel-head">
          <h3>{t("At-risk value by cluster")}</h3>
          <span className="risk-panel-note" title={t(GROSS_VS_NET_NOTE)}>
            {t("Gross")}
          </span>
        </header>
        <ValueBarChart data={clusterData} xKey="name" />
      </article>

      <article className="risk-panel">
        <header className="risk-panel-head">
          <h3>{t("At-risk value by legal entity")}</h3>
          <span className="risk-panel-note" title={t(GROSS_VS_NET_NOTE)}>
            {t("Gross")}
          </span>
        </header>
        <ValueBarChart
          data={entityData}
          xKey="name"
          activeKey={scope.legal_entity_id}
          onSelect={(point) => onSelectLegalEntity(point.selection_key)}
        />
      </article>
    </section>
  );
}
