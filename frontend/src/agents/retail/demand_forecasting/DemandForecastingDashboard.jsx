import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import DemandForecastFilters from "./components/DemandForecastFilters.jsx";
import DemandForecastingSkeleton from "./components/DemandForecastingSkeleton.jsx";
import DemandKpiGrid from "./components/DemandKpiGrid.jsx";
import ForecastConfidencePanel from "./components/ForecastConfidencePanel.jsx";
import ForecastDetailTable from "./components/ForecastDetailTable.jsx";
import ForecastOverviewPanel from "./components/ForecastOverviewPanel.jsx";
import PredictedTrendPanel from "./components/PredictedTrendPanel.jsx";
import { DEFAULT_DEMAND_QUERY } from "./data/contract.js";
import { loadDemandForecastingDashboard } from "./data/dashboardData.js";

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

export default function DemandForecastingDashboard() {
  const { t } = useLanguage();
  const [query, setQuery] = useState({ ...DEFAULT_DEMAND_QUERY });
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadDemandForecastingDashboard(query);
        if (!cancelled) setDashboard(result);
      } catch (loadError) {
        if (!cancelled) setError(loadError.message || t("Unable to load Demand Forecasting."));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [
    query.legal_entity_id,
    query.category_group,
    query.store_id,
    query.sku,
    query.grain,
    query.horizon_weeks,
    query.detail_offset,
    query.detail_limit,
    refreshToken,
    t,
  ]);

  const patchQuery = useCallback((patch) => {
    setQuery((current) => ({ ...current, ...patch, detail_offset: 0 }));
  }, []);

  const clearQuery = useCallback(() => {
    setQuery({ ...DEFAULT_DEMAND_QUERY });
  }, []);

  const options = dashboard?.filter_options || {
    legal_entities: [], categories: [], stores: [], grains: ["daily", "weekly", "monthly", "quarterly", "yearly"], horizons_weeks: [4, 8, 12, 16],
  };

  const scopeLabels = useMemo(() => {
    const labels = [];
    if (query.legal_entity_id !== "ALL") labels.push(optionLabel(options.legal_entities, query.legal_entity_id));
    if (query.category_group !== "ALL") labels.push(optionLabel(options.categories, query.category_group));
    if (query.store_id !== "ALL") labels.push(optionLabel(options.stores, query.store_id));
    if (query.sku) labels.push(query.sku);
    return labels;
  }, [options, query]);

  if (!dashboard && loading) {
    return (
      <section className="workboard demand-forecasting-dashboard" data-testid="demand-forecasting-dashboard">
        <DemandForecastingSkeleton />
      </section>
    );
  }

  if (!dashboard && error) {
    return (
      <section className="workboard demand-forecasting-dashboard" data-testid="demand-forecasting-dashboard">
        <div className="workboard-status error" role="alert">
          <p>{error}</p>
          <button type="button" className="demand-button" onClick={() => setRefreshToken((value) => value + 1)}>{t("Retry")}</button>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`workboard demand-forecasting-dashboard${loading ? " is-refreshing" : ""}`}
      data-testid="demand-forecasting-dashboard"
      aria-label={t("Demand Forecasting dashboard")}
      aria-busy={loading}
    >
      <DemandForecastFilters
        query={query}
        options={options}
        busy={loading}
        onPatch={patchQuery}
        onSearch={(sku) => patchQuery({ sku })}
        onRefresh={() => setRefreshToken((value) => value + 1)}
        onClear={clearQuery}
      />

      <div className="demand-scope-row">
        <span className="demand-data-note">{dashboard.is_mock ? t("Synthetic data") : t("Live data")} · {t(dashboard.note)}</span>
        <div className="demand-scope-summary">
          <span>{t("Scope")}:</span>
          {scopeLabels.length ? scopeLabels.map((label) => <b key={label}>{label}</b>) : <b>{t("All retail demand")}</b>}
          {scopeLabels.length ? <button type="button" onClick={clearQuery}>{t("Clear all")}</button> : null}
        </div>
      </div>

      {error ? (
        <div className="demand-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)}>{t("Retry")}</button>
        </div>
      ) : null}

      <DemandKpiGrid kpis={dashboard.kpis} />

      <div className="demand-chart-grid">
        <ForecastOverviewPanel
          forecast={dashboard.forecast}
          grains={options.grains}
          onGrainChange={(grain) => patchQuery({ grain })}
        />
        <ForecastConfidencePanel confidence={dashboard.confidence} />
      </div>

      <PredictedTrendPanel items={dashboard.trending_items} onSelect={(sku) => patchQuery({ sku })} />
      <ForecastDetailTable details={dashboard.details} grain={dashboard.forecast.grain} onSelect={(sku) => patchQuery({ sku })} />
    </section>
  );
}

