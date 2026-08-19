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
import ExpiryTimelinePanel from "./ExpiryTimelinePanel.jsx";

/**
 * Height per store row, from the mockup's `hbarChart(…, {rh:27})`.
 *
 * Horizontal bars grow downward as stores are added rather than squeezing bar
 * width, so this chart is sized from its row count instead of inheriting
 * `.risk-chart`'s fixed height. That is the whole reason the mockup picks a
 * horizontal layout here and vertical everywhere else: stores are the
 * highest-cardinality dimension on the board.
 */
const STORE_ROW_HEIGHT = 27;

/** Axis labels and margins that sit outside the rows themselves. */
const STORE_CHART_CHROME = 46;

/** Label gutter for store names, matching the mockup's `pl:110`. */
const STORE_LABEL_WIDTH = 110;

/**
 * How many stores the chart draws.
 *
 * The mockup plots every active store, which works at its scale but not at
 * this one: the chain carries 160, and a row apiece is a four-thousand-pixel
 * card that dwarfs every other panel and re-lays-out on every filter change.
 * The bars are sorted worst-first, so a cut here drops the stores nobody is
 * looking at — the ones with no reorder zone at all.
 */
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

function StoreTooltip({ active, payload }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const point = payload[0].payload;
  return (
    <div className="risk-chart-tooltip">
      <strong>
        {point.store_id} · {point.label}
      </strong>
      <span>
        {t("Stockout")}: {formatUnits(point.stockout_count, language)}
      </span>
      <span>
        {t("Low")}: {formatUnits(point.low_count, language)}
      </span>
      {/*
        Still reported even though neither is plotted any more. The mockup
        charts only the reorder zone (Stockout + Low), but a reader hovering a
        short bar needs to know whether the rest of that store is healthy or
        merely at risk in some other way.
      */}
      <span>
        {t("Other at risk")}: {formatUnits(point.other_at_risk_count, language)}
      </span>
      <span>
        {t("Healthy")}: {formatUnits(point.healthy_count, language)}
      </span>
      <span className="risk-tooltip-total">
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
 * A2 spec section 6. Five breakdowns of the same exposure, in the mockup's
 * three-row arrangement (`dimRowHTML('a2')`):
 *
 *   row 1   category | store
 *   row 2   cluster  | expiry timeline & watchlist
 *   row 3   legal entity, full width
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
  expiryTimeline,
  scope,
  onSelectCategory,
  onSelectLegalEntity,
  onSelectExpirySku,
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
  /* Worst reorder zone first, as the mockup sorts, then cut to what fits. */
  const storeData = [...byStore]
    .sort(
      (a, b) =>
        b.stockout_count + b.low_count - (a.stockout_count + a.low_count),
    )
    .slice(0, TOP_STORES);
  const storeChartHeight =
    storeData.length * STORE_ROW_HEIGHT + STORE_CHART_CHROME;

  return (
    <section className="risk-dimension-grid" aria-label={t("Risk by dimension")}>
      <div className="risk-dimension-row">
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
              {t("Gross · reorder zone · top 12")}
            </span>
          </header>
          {/* One horizontal stack per store covering the reorder zone only:
              Stockout plus Low, the two states that mean "order this now".
              The remaining SKUs at that store stay in the tooltip rather than
              on the axis, so bar length reads as urgency instead of size. */}
          <div
            className="risk-chart"
            style={{ height: storeChartHeight }}
            role="img"
            aria-label={t("Stockout-risk by store")}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={storeData}
                layout="vertical"
                margin={{ top: 6, right: 12, left: 0, bottom: 4 }}
              >
                <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 10, fill: "var(--muted)" }}
                  tickLine={false}
                  axisLine={{ stroke: "var(--line)" }}
                  tickFormatter={(value) => formatUnits(value, language)}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={STORE_LABEL_WIDTH}
                  interval={0}
                  tick={{ fontSize: 10, fill: "var(--ink)" }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }} content={<StoreTooltip />} />
                <Bar dataKey="stockout_count" stackId="skus" fill="var(--risk-stockout)" isAnimationActive={false} />
                <Bar dataKey="low_count" stackId="skus" fill="var(--risk-low)" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <ul className="risk-legend" aria-hidden="true">
            <li><i style={{ background: "var(--risk-stockout)" }} />{t("Stockout")}</li>
            <li><i style={{ background: "var(--risk-low)" }} />{t("Low")}</li>
          </ul>
        </article>
      </div>

      <div className="risk-dimension-row">
        <article className="risk-panel">
          <header className="risk-panel-head">
            <h3>{t("At-risk value by cluster")}</h3>
            <span className="risk-panel-note" title={t(GROSS_VS_NET_NOTE)}>
              {t("Gross")}
            </span>
          </header>
          <ValueBarChart data={clusterData} xKey="name" />
        </article>

        {/* The mockup pairs the expiry timeline with cluster rather than giving
            it a row of its own — it is a dimension chart like the rest. */}
        <ExpiryTimelinePanel timeline={expiryTimeline} onSelect={onSelectExpirySku} />
      </div>

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
