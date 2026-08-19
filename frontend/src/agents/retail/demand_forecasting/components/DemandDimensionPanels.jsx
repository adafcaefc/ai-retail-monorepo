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

import { useMemo } from "react";
import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import {
  takeTopForecastDimensions,
  TOP_FORECAST_DIMENSION_LIMIT,
} from "../data/topForecastDimensions.js";

function DimensionTooltip({ active, payload, label }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="demand-chart-tooltip">
      <strong>{row.label || label}</strong>
      <span>{t("Forecast units")}: {formatNumber(row.forecast_units, language, { maximumFractionDigits: 0 })}</span>
      {row.store_count != null ? <span>{t("Stores")}: {row.store_count}</span> : null}
      {row.cluster ? <span>{t("Cluster")}: {row.cluster}</span> : null}
      <span>{t("Share")}: {formatNumber(row.share_pct, language, { maximumFractionDigits: 1 })}%</span>
    </div>
  );
}

function SeasonalityTooltip({ active, payload }) {
  const { t } = useLanguage();
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="demand-chart-tooltip">
      <strong>{row.month}</strong>
      <span>{t("Seasonality index")}: {row.index}</span>
      {row.current ? <span>{t("Current mock month")}</span> : null}
    </div>
  );
}

function PanelHeader({ eyebrow, title, hint }) {
  const { t } = useLanguage();
  return (
    <header className="demand-panel-head">
      <div>
        <p>{t(eyebrow)}</p>
        <h2>{t(title)}</h2>
        {hint ? <span>{t(hint)}</span> : null}
      </div>
    </header>
  );
}

function VerticalDimensionChart({ rows, ariaLabel, onSelect, currentMonth = false }) {
  return (
    <div className="demand-dimension-chart" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 12, left: 0 }}>
          <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={currentMonth ? "month" : "label"} tick={{ fontSize: 9, fill: "var(--muted)" }} interval={0} angle={rows.length > 8 ? -24 : 0} textAnchor={rows.length > 8 ? "end" : "middle"} height={rows.length > 8 ? 54 : 30} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
          <YAxis tick={{ fontSize: 9, fill: "var(--muted)" }} width={54} tickLine={false} axisLine={false} tickFormatter={(value) => formatNumber(value, "en", { maximumFractionDigits: 0 })} />
          <Tooltip content={currentMonth ? <SeasonalityTooltip /> : <DimensionTooltip />} />
          <Bar
            dataKey={currentMonth ? "index" : "forecast_units"}
            fill="var(--demand-dimension)"
            radius={[5, 5, 0, 0]}
            isAnimationActive={false}
            onClick={(entry) => onSelect?.(entry?.id || entry?.payload?.id)}
          >
            {currentMonth ? rows.map((row) => (
              <Cell key={row.month} fill={row.current ? "var(--demand-current-month)" : "var(--demand-season)"} />
            )) : null}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RankedStoreChart({ rows, onSelect }) {
  const height = Math.max(240, rows.length * 30);
  return (
    <div className="demand-store-chart" style={{ height }} role="img" aria-label="Forecast by store chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 18, bottom: 4, left: 10 }}>
          <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} tickFormatter={(value) => formatNumber(value, "en", { maximumFractionDigits: 0 })} />
          <YAxis type="category" dataKey="label" width={118} tick={{ fontSize: 9, fill: "var(--muted)" }} tickLine={false} axisLine={false} />
          <Tooltip content={<DimensionTooltip />} />
          <Bar dataKey="forecast_units" fill="var(--demand-store)" radius={[0, 5, 5, 0]} isAnimationActive={false} onClick={(entry) => onSelect?.(entry?.id || entry?.payload?.id)} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function DrilldownButtons({ rows, onSelect, label, limit = 12 }) {
  const { t } = useLanguage();
  if (!onSelect || !rows.length) return null;
  return (
    <div className="demand-dimension-drilldowns" aria-label={t(label)}>
      {rows.slice(0, limit).map((row) => (
        <button key={row.id} type="button" onClick={() => onSelect(row.id)}>{row.label}</button>
      ))}
    </div>
  );
}

export default function DemandDimensionPanels({ dimensions, onCategory, onStore, onLegalEntity }) {
  const { language, t } = useLanguage();
  const categoryRows = useMemo(
    () => takeTopForecastDimensions(dimensions.categories),
    [dimensions.categories],
  );
  const storeRows = useMemo(
    () => takeTopForecastDimensions(dimensions.stores),
    [dimensions.stores],
  );

  return (
    <section className="demand-dimensions" aria-label={t("Demand forecast dimensions")}>
      <div className="demand-dimension-row">
        <article className="demand-panel demand-dimension-panel">
          <PanelHeader eyebrow="Demand dimensions" title="Forecast by category" hint="Next 7d forecast · Top 20 · Select a category to update the Demand scope" />
          <VerticalDimensionChart rows={categoryRows} ariaLabel={t("Forecast by category chart")} onSelect={onCategory} />
          <DrilldownButtons rows={categoryRows} onSelect={onCategory} limit={TOP_FORECAST_DIMENSION_LIMIT} label="Category filter shortcuts" />
        </article>
        <article className="demand-panel demand-dimension-panel">
          <PanelHeader eyebrow="Demand dimensions" title="Forecast by store" hint="Next 7d forecast · Top 20 highest forecast" />
          <RankedStoreChart rows={storeRows} onSelect={onStore} />
          <DrilldownButtons rows={storeRows} onSelect={onStore} limit={TOP_FORECAST_DIMENSION_LIMIT} label="Store filter shortcuts" />
        </article>
      </div>

      <div className="demand-dimension-row">
        <article className="demand-panel demand-dimension-panel">
          <PanelHeader eyebrow="Demand dimensions" title="Forecast by cluster" hint="Next 7d forecast · Flagship · Mall · Community · Express" />
          <VerticalDimensionChart rows={dimensions.clusters} ariaLabel={t("Forecast by cluster chart")} />
        </article>
        <article className="demand-panel demand-dimension-panel">
          <PanelHeader eyebrow="Demand pattern" title="Seasonality curve (12 mo)" hint="Index where 100 = average month" />
          <VerticalDimensionChart rows={dimensions.seasonality} ariaLabel={t("Seasonality curve chart")} currentMonth />
        </article>
      </div>

      <article className="demand-panel demand-dimension-panel demand-legal-entity-panel">
        <PanelHeader eyebrow="Store → Legal Entity → Chain" title="By legal entity" hint="Next 7d forecast · Current Demand scope" />
        <VerticalDimensionChart rows={dimensions.legal_entities} ariaLabel={t("Forecast by legal entity chart")} onSelect={onLegalEntity} />
        <DrilldownButtons rows={dimensions.legal_entities} onSelect={onLegalEntity} label="Legal entity filter shortcuts" />
        <div className="demand-chain-summary">
          {dimensions.legal_entities.map((row) => (
            <span key={row.id}>
              <b>{row.id}</b> {formatNumber(row.forecast_units, language, { maximumFractionDigits: 0 })} {t("units")} · {row.store_count} {t("stores")} · {formatNumber(row.share_pct, language, { maximumFractionDigits: 1 })}%
            </span>
          ))}
          <strong>{t("Chain Total")}: {formatNumber(dimensions.chain_total, language, { maximumFractionDigits: 0 })} {t("units")}</strong>
        </div>
      </article>
    </section>
  );
}
