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
    <div className="assortment-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("Contribution/day")}: {formatIdr(payload[0].value, language)}
      </span>
    </div>
  );
}

function StoreTooltip({ active, payload }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="assortment-chart-tooltip">
      <strong>{point.store_id} · {point.label}</strong>
      <span>{t("SKUs stocked")}: {formatUnits(point.sku_count, language)}</span>
      <span>{t("Inventory value")}: {formatIdr(point.inv_value, language)}</span>
      <span className="assortment-tooltip-total">
        {t("Contribution/day")}: {formatIdr(point.value, language)}
      </span>
    </div>
  );
}

function ValueBarChart({ data, xKey, tooltip }) {
  const { language, t } = useLanguage();
  return (
    <div className="assortment-chart" role="img" aria-label={t("Contribution/day")}>
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
          <Tooltip
            cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }}
            content={tooltip ?? <ValueTooltip />}
          />
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
 * A6 spec section 6. Five breakdowns: store, cluster, channel, inventory
 * state (value, full population), legal entity.
 */
export default function DimensionCharts({ byStore, byCluster, byChannel, byState, byLegalEntity }) {
  const { language, t } = useLanguage();

  const storeData = byStore.slice(0, TOP_STORES).map((row) => ({ ...row, name: row.label }));
  const clusterData = byCluster.map((row) => ({ ...row, name: row.cluster }));
  const channelData = byChannel.map((row) => ({ ...row, name: row.channel }));
  const stateData = byState.map((row) => ({ ...row, name: t(row.state) }));
  const entityData = byLegalEntity.map((row) => ({ ...row, name: row.label }));

  return (
    <section className="assortment-dimension-grid" aria-label={t("Assortment by dimension")}>
      <article className="assortment-panel">
        <header className="assortment-panel-head">
          <h3>{t("Contribution/day by store")}</h3>
          <span className="assortment-panel-note" title={t(GRAIN_NOTE)}>
            {t("Store grain · top 12")}
          </span>
        </header>
        <ValueBarChart data={storeData} xKey="store_id" tooltip={<StoreTooltip />} />
      </article>

      <article className="assortment-panel">
        <header className="assortment-panel-head">
          <h3>{t("Contribution/day by cluster")}</h3>
          <span className="assortment-panel-note" title={t(GRAIN_NOTE)}>{t("Store grain")}</span>
        </header>
        <ValueBarChart data={clusterData} xKey="name" />
      </article>

      <article className="assortment-panel">
        <header className="assortment-panel-head">
          <h3>{t("Contribution/day by channel")}</h3>
          <span className="assortment-panel-note" title={t(GRAIN_NOTE)}>{t("Store grain")}</span>
        </header>
        <ValueBarChart data={channelData} xKey="name" />
      </article>

      <article className="assortment-panel">
        <header className="assortment-panel-head">
          <h3>{t("Inventory value by state")}</h3>
          <span className="assortment-panel-note">{t("All states, not only delist candidates")}</span>
        </header>
        <div className="assortment-chart" role="img" aria-label={t("Inventory value by state")}>
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

      <article className="assortment-panel">
        <header className="assortment-panel-head">
          <h3>{t("Contribution/day by legal entity")}</h3>
          <span className="assortment-panel-note" title={t(GRAIN_NOTE)}>{t("Store grain")}</span>
        </header>
        <ValueBarChart data={entityData} xKey="name" />
      </article>
    </section>
  );
}
