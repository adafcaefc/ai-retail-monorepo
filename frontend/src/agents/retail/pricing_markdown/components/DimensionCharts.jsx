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
import { GRAIN_NOTE } from "../data/contract.js";
import { formatIdr, formatUnits, stateColor } from "../presentation.js";

const TOP_STORES = 12;

function ValueTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  return (
    <div className="pricing-chart-tooltip">
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
    <div className="pricing-chart-tooltip">
      <strong>{point.store_id} · {point.label}</strong>
      <span>{t("Expiry")}: {formatUnits(point.expiry_count, language)}</span>
      <span>{t("Overstock")}: {formatUnits(point.overstock_count, language)}</span>
      <span>{t("Slow-mover")}: {formatUnits(point.slow_mover_count, language)}</span>
      <span>{t("Other")}: {formatUnits(point.other_count, language)}</span>
      <span className="pricing-tooltip-total">
        {t("At-risk value")}: {formatIdr(point.at_risk_value, language)}
      </span>
    </div>
  );
}

function ValueBarChart({ data, xKey }) {
  const { language, t } = useLanguage();
  return (
    <div className="pricing-chart" role="img" aria-label={t("At-risk value")}>
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
          <Bar dataKey="value" isAnimationActive={false}>
            {data.map((point, i) => (
              <Cell key={point[xKey] ?? i} fill="var(--accent-info)" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * A5 spec section 6. Five breakdowns: store, cluster, channel, inventory
 * state (full population), legal entity.
 */
export default function DimensionCharts({ byStore, byCluster, byChannel, byState, byLegalEntity }) {
  const { language, t } = useLanguage();

  const storeData = byStore.slice(0, TOP_STORES).map((row) => ({ ...row, name: row.label }));
  const clusterData = byCluster.map((row) => ({ ...row, name: row.cluster }));
  const channelData = byChannel.map((row) => ({ ...row, name: row.channel }));
  const stateData = byState.map((row) => ({ ...row, name: t(row.state) }));
  const entityData = byLegalEntity.map((row) => ({ ...row, name: row.label }));

  return (
    <section className="pricing-dimension-grid" aria-label={t("Pricing & Markdown by dimension")}>
      <article className="pricing-panel">
        <header className="pricing-panel-head">
          <h3>{t("At-risk value by store")}</h3>
          <span className="pricing-panel-note" title={t(GRAIN_NOTE)}>
            {t("Gross · top 12")}
          </span>
        </header>
        <div className="pricing-chart" role="img" aria-label={t("At-risk value by store")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={storeData} margin={{ top: 6, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="store_id" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} interval={0} height={30} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={34} tickFormatter={(v) => formatUnits(v, language)} />
              <Tooltip cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }} content={<StoreTooltip />} />
              <Bar dataKey="expiry_count" stackId="skus" fill="var(--red-700)" isAnimationActive={false} />
              <Bar dataKey="overstock_count" stackId="skus" fill="var(--blue-500)" isAnimationActive={false} />
              <Bar dataKey="slow_mover_count" stackId="skus" fill="var(--amber-600)" isAnimationActive={false} />
              <Bar dataKey="other_count" stackId="skus" fill="var(--gray-200)" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ul className="pricing-legend" aria-hidden="true">
          <li><i style={{ background: "var(--red-700)" }} />{t("Expiry")}</li>
          <li><i style={{ background: "var(--blue-500)" }} />{t("Overstock")}</li>
          <li><i style={{ background: "var(--amber-600)" }} />{t("Slow-mover")}</li>
          <li><i style={{ background: "var(--gray-200)" }} />{t("Other")}</li>
        </ul>
      </article>

      <article className="pricing-panel">
        <header className="pricing-panel-head">
          <h3>{t("At-risk value by cluster")}</h3>
          <span className="pricing-panel-note" title={t(GRAIN_NOTE)}>{t("Gross")}</span>
        </header>
        <ValueBarChart data={clusterData} xKey="name" />
      </article>

      <article className="pricing-panel">
        <header className="pricing-panel-head">
          <h3>{t("At-risk value by channel")}</h3>
          <span className="pricing-panel-note" title={t(GRAIN_NOTE)}>{t("Gross")}</span>
        </header>
        <ValueBarChart data={channelData} xKey="name" />
      </article>

      <article className="pricing-panel">
        <header className="pricing-panel-head">
          <h3>{t("Inventory value by state")}</h3>
          <span className="pricing-panel-note">{t("All states, not only markdown candidates")}</span>
        </header>
        <div className="pricing-chart" role="img" aria-label={t("Inventory value by state")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stateData} margin={{ top: 6, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} interval={0} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={58} tickFormatter={(v) => formatIdr(v, language, { digits: 0 })} />
              <Tooltip formatter={(v) => formatIdr(v, language)} />
              <Bar dataKey="value" isAnimationActive={false}>
                {stateData.map((row) => (
                  <Cell key={row.state} fill={stateColor(row.state)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </article>

      <article className="pricing-panel">
        <header className="pricing-panel-head">
          <h3>{t("At-risk value by legal entity")}</h3>
          <span className="pricing-panel-note" title={t(GRAIN_NOTE)}>{t("Gross")}</span>
        </header>
        <ValueBarChart data={entityData} xKey="name" />
      </article>
    </section>
  );
}
