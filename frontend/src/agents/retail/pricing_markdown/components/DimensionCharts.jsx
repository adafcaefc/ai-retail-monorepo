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
import { ALL, GRAIN_NOTE } from "../data/contract.js";
import { formatIdr, formatUnits, stateColor } from "../presentation.js";

const TOP_STORES = 12;

/**
 * A panel title, its usual note (e.g. "Gross · top 12"), and an optional
 * "Back to all X" reset button — shown alongside the note, not instead of it.
 */
function PanelHead({ title, note, noteTitle, selected, resetLabel, onSelect }) {
  const { t } = useLanguage();
  const hasSelection = Boolean(onSelect) && Boolean(selected) && selected !== ALL;
  return (
    <header className="pricing-panel-head">
      <h3>{t(title)}</h3>
      <div className="pricing-panel-head-actions">
        {note ? (
          <span className="pricing-panel-note" title={noteTitle ? t(noteTitle) : undefined}>
            {note}
          </span>
        ) : null}
        {hasSelection ? (
          <button type="button" className="pricing-chart-reset" onClick={() => onSelect(ALL)}>
            {t(resetLabel)}
          </button>
        ) : null}
      </div>
    </header>
  );
}

/**
 * A row of filter-shortcut pills mirroring the chart above it — the primary
 * click target in tests (Recharts bar clicks are mocked out there), same
 * role as demand_forecasting's DrilldownButtons. A local copy of
 * PricingCharts.jsx's own DrilldownPills — this file already keeps its own
 * copy of ScopeCollapseNote rather than sharing one across the two files.
 */
function DrilldownPills({ rows, idKey, onSelect, label }) {
  const { t } = useLanguage();
  if (!onSelect || !rows.length) return null;
  return (
    <div className="pricing-chart-drilldowns" aria-label={t(label)}>
      {rows.map((row) => (
        <button key={row[idKey]} type="button" onClick={() => onSelect(row[idKey])}>
          {row.label ?? row.name}
        </button>
      ))}
    </div>
  );
}

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

/**
 * When a panel's own grouping dimension has been narrowed to a single bar by
 * the active scope, it's still numerically correct but has nothing left to
 * compare — a short pointer beats a bare 1-bar chart that reads as broken.
 * Data-driven (row count), not scope-condition-driven; see PricingCharts.jsx's
 * copy of the same idea for why.
 */
function ScopeCollapseNote({ data, labelKey = "name" }) {
  const { t } = useLanguage();
  if (data.length !== 1) return null;
  return (
    <p className="pricing-footnote">
      {t("Scoped to")} <b>{data[0][labelKey]}</b>
    </p>
  );
}

function ValueBarChart({ data, xKey, onSelect }) {
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
          <Bar
            dataKey="value"
            isAnimationActive={false}
            onClick={onSelect ? (entry) => onSelect(entry?.payload ?? entry) : undefined}
            cursor={onSelect ? "pointer" : undefined}
          >
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
export default function DimensionCharts({
  byStore,
  byCluster,
  byChannel,
  byState,
  byLegalEntity,
  scope,
  onSelectStore,
  onSelectState,
  onSelectLegalEntity,
}) {
  const { language, t } = useLanguage();

  const storeData = byStore.slice(0, TOP_STORES).map((row) => ({ ...row, name: row.label }));
  const clusterData = byCluster.map((row) => ({ ...row, name: row.cluster }));
  const channelData = byChannel.map((row) => ({ ...row, name: row.channel }));
  const stateData = byState.map((row) => ({ ...row, name: t(row.state) }));
  const entityData = byLegalEntity.map((row) => ({ ...row, name: row.label }));

  return (
    <section className="pricing-dimension-grid" aria-label={t("Pricing & Markdown by dimension")}>
      <article className="pricing-panel">
        <PanelHead
          title="At-risk value by store"
          note={t("Gross · top 12")}
          noteTitle={GRAIN_NOTE}
          selected={scope?.store_id}
          resetLabel="Back to all stores"
          onSelect={onSelectStore}
        />
        <ScopeCollapseNote data={storeData} />
        <div className="pricing-chart" role="img" aria-label={t("At-risk value by store")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={storeData} margin={{ top: 6, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="store_id" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} interval={0} height={30} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={34} tickFormatter={(v) => formatUnits(v, language)} />
              <Tooltip cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }} content={<StoreTooltip />} />
              <Bar
                dataKey="expiry_count"
                stackId="skus"
                fill="var(--red-700)"
                isAnimationActive={false}
                onClick={onSelectStore ? (entry) => onSelectStore(entry?.store_id ?? entry?.payload?.store_id) : undefined}
                cursor={onSelectStore ? "pointer" : undefined}
              />
              <Bar
                dataKey="overstock_count"
                stackId="skus"
                fill="var(--blue-500)"
                isAnimationActive={false}
                onClick={onSelectStore ? (entry) => onSelectStore(entry?.store_id ?? entry?.payload?.store_id) : undefined}
                cursor={onSelectStore ? "pointer" : undefined}
              />
              <Bar
                dataKey="slow_mover_count"
                stackId="skus"
                fill="var(--amber-600)"
                isAnimationActive={false}
                onClick={onSelectStore ? (entry) => onSelectStore(entry?.store_id ?? entry?.payload?.store_id) : undefined}
                cursor={onSelectStore ? "pointer" : undefined}
              />
              <Bar
                dataKey="other_count"
                stackId="skus"
                fill="var(--gray-200)"
                isAnimationActive={false}
                onClick={onSelectStore ? (entry) => onSelectStore(entry?.store_id ?? entry?.payload?.store_id) : undefined}
                cursor={onSelectStore ? "pointer" : undefined}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ul className="pricing-legend" aria-hidden="true">
          <li><i style={{ background: "var(--red-700)" }} />{t("Expiry")}</li>
          <li><i style={{ background: "var(--blue-500)" }} />{t("Overstock")}</li>
          <li><i style={{ background: "var(--amber-600)" }} />{t("Slow-mover")}</li>
          <li><i style={{ background: "var(--gray-200)" }} />{t("Other")}</li>
        </ul>
        <DrilldownPills rows={storeData} idKey="store_id" onSelect={onSelectStore} label="Store filter shortcuts" />
      </article>

      <article className="pricing-panel">
        <header className="pricing-panel-head">
          <h3>{t("At-risk value by cluster")}</h3>
          <span className="pricing-panel-note" title={t(GRAIN_NOTE)}>{t("Gross")}</span>
        </header>
        <ScopeCollapseNote data={clusterData} />
        <ValueBarChart data={clusterData} xKey="name" />
      </article>

      <article className="pricing-panel">
        <header className="pricing-panel-head">
          <h3>{t("At-risk value by channel")}</h3>
          <span className="pricing-panel-note" title={t(GRAIN_NOTE)}>{t("Gross")}</span>
        </header>
        <ScopeCollapseNote data={channelData} />
        <ValueBarChart data={channelData} xKey="name" />
      </article>

      <article className="pricing-panel">
        <PanelHead
          title="Inventory value by state"
          note={t("All states, not only markdown candidates")}
          selected={scope?.state}
          resetLabel="Back to all states"
          onSelect={onSelectState}
        />
        <ScopeCollapseNote data={stateData} />
        <div className="pricing-chart" role="img" aria-label={t("Inventory value by state")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stateData} margin={{ top: 6, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} interval={0} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={58} tickFormatter={(v) => formatIdr(v, language, { digits: 0 })} />
              <Tooltip formatter={(v) => formatIdr(v, language)} />
              <Bar
                dataKey="value"
                isAnimationActive={false}
                onClick={onSelectState ? (entry) => onSelectState(entry?.state ?? entry?.payload?.state) : undefined}
                cursor={onSelectState ? "pointer" : undefined}
              >
                {stateData.map((row) => (
                  <Cell key={row.state} fill={stateColor(row.state)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <DrilldownPills rows={stateData} idKey="state" onSelect={onSelectState} label="State filter shortcuts" />
      </article>

      <article className="pricing-panel">
        <PanelHead
          title="At-risk value by legal entity"
          note={t("Gross")}
          noteTitle={GRAIN_NOTE}
          selected={scope?.legal_entity_id}
          resetLabel="Back to all legal entities"
          onSelect={onSelectLegalEntity}
        />
        <ScopeCollapseNote data={entityData} />
        <ValueBarChart
          data={entityData}
          xKey="name"
          onSelect={onSelectLegalEntity ? (row) => onSelectLegalEntity(row.legal_entity_id) : undefined}
        />
        <DrilldownPills rows={entityData} idKey="legal_entity_id" onSelect={onSelectLegalEntity} label="Legal entity filter shortcuts" />
      </article>
    </section>
  );
}
