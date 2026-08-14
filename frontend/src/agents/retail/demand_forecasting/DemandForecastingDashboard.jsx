import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import DemandForecastFilters from "./components/DemandForecastFilters.jsx";
import DemandForecastingSkeleton from "./components/DemandForecastingSkeleton.jsx";
import DemandKpiDrilldown from "./components/DemandKpiDrilldown.jsx";
import DemandKpiGrid from "./components/DemandKpiGrid.jsx";
import DemandAppliedScenarioBanner from "./components/DemandAppliedScenarioBanner.jsx";
import DemandDimensionPanels from "./components/DemandDimensionPanels.jsx";
import DemandScenarioComparison from "./components/DemandScenarioComparison.jsx";
import DemandSuggestedActions from "./components/DemandSuggestedActions.jsx";
import DemandWhatIfSimulator from "./components/DemandWhatIfSimulator.jsx";
import ForecastConfidencePanel from "./components/ForecastConfidencePanel.jsx";
import ForecastDetailTable from "./components/ForecastDetailTable.jsx";
import ForecastOverviewPanel from "./components/ForecastOverviewPanel.jsx";
import PredictedTrendPanel from "./components/PredictedTrendPanel.jsx";
import {
  DEFAULT_DEMAND_LEVERS,
  DEFAULT_DEMAND_QUERY,
  demandScenarioContext,
  isDemandScenarioCompatible,
} from "./data/contract.js";
import {
  loadDemandForecastingDashboard,
  loadDemandForecastingDrilldown,
  loadDemandForecastingScenario,
} from "./data/dashboardData.js";

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
  const [draftLevers, setDraftLevers] = useState({ ...DEFAULT_DEMAND_LEVERS });
  const [appliedLevers, setAppliedLevers] = useState({ ...DEFAULT_DEMAND_LEVERS });
  const [driveWholePage, setDriveWholePage] = useState(true);
  const [scenarioResult, setScenarioResult] = useState(null);
  const [scenarioDirty, setScenarioDirty] = useState(false);
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const [scenarioError, setScenarioError] = useState("");
  const [savedScenarios, setSavedScenarios] = useState([]);
  const nextScenarioId = useRef(1);
  // The KPI tile currently broken down, or null. Built on demand — see
  // `loadDemandForecastingDrilldown`.
  const [drilldown, setDrilldown] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadDemandForecastingDashboard(query, appliedLevers, {
          driveWholePage,
        });
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
    appliedLevers.demand,
    appliedLevers.promo,
    appliedLevers.markdown,
    appliedLevers.inbound,
    appliedLevers.lead,
    appliedLevers.safety,
    driveWholePage,
    refreshToken,
    t,
  ]);

  const patchQuery = useCallback((patch) => {
    setQuery((current) => ({ ...current, ...patch, detail_offset: 0 }));
    setScenarioResult(null);
    // A filter change makes an open drawer describe rows that are no longer on
    // screen, so it closes rather than going quietly stale.
    setDrilldown(null);
  }, []);

  const clearQuery = useCallback(() => {
    setQuery({ ...DEFAULT_DEMAND_QUERY });
    setScenarioResult(null);
    setDrilldown(null);
  }, []);

  const openDrilldown = useCallback(
    async (metricId) => {
      setDrilldown(
        await loadDemandForecastingDrilldown(query, metricId, {
          levers: appliedLevers,
          driveWholePage,
        }),
      );
    },
    [appliedLevers, driveWholePage, query],
  );

  const runScenario = useCallback(async (levers = draftLevers, scenarioQuery = query) => {
    setScenarioBusy(true);
    setScenarioError("");
    try {
      const result = await loadDemandForecastingScenario(scenarioQuery, levers);
      setScenarioResult(result);
      setDraftLevers({ ...result.simulation.scenario_levers });
      setScenarioDirty(false);
      if (driveWholePage) {
        setAppliedLevers({ ...result.simulation.scenario_levers });
      }
      return result;
    } catch (runError) {
      setScenarioError(runError.message || t("Unable to run scenario."));
      return null;
    } finally {
      setScenarioBusy(false);
    }
  }, [draftLevers, driveWholePage, query, t]);

  const saveScenario = useCallback(() => {
    if (!scenarioResult || scenarioDirty) return;
    const number = nextScenarioId.current;
    nextScenarioId.current += 1;
    setSavedScenarios((current) => [...current, {
      id: `scenario-${number}`,
      name: `S${number}`,
      levers: { ...scenarioResult.simulation.scenario_levers },
      context: demandScenarioContext(scenarioResult.scope),
      baselineForecast: scenarioResult.simulation.baseline_forecast,
      forecast: scenarioResult.forecast,
      metrics: scenarioResult.simulation.scenario,
      savedAt: new Date().toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    }]);
  }, [scenarioDirty, scenarioResult]);

  const loadLatestScenario = useCallback(async () => {
    const latest = savedScenarios[savedScenarios.length - 1];
    if (!latest) return;
    const restoredQuery = {
      ...query,
      ...latest.context,
      detail_offset: 0,
    };
    setQuery(restoredQuery);
    setDraftLevers({ ...latest.levers });
    await runScenario(latest.levers, restoredQuery);
  }, [query, runScenario, savedScenarios]);

  const resetScenario = useCallback(() => {
    setDraftLevers({ ...DEFAULT_DEMAND_LEVERS });
    setAppliedLevers({ ...DEFAULT_DEMAND_LEVERS });
    setScenarioResult(null);
    setScenarioDirty(false);
    setScenarioError("");
  }, []);

  const changeDriveWholePage = useCallback((enabled) => {
    setDriveWholePage(enabled);
    if (!enabled) {
      setAppliedLevers({ ...DEFAULT_DEMAND_LEVERS });
    } else if (scenarioResult) {
      setAppliedLevers({ ...scenarioResult.simulation.scenario_levers });
    }
  }, [scenarioResult]);

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

  const compatibleSavedScenarios = useMemo(
    () => savedScenarios.filter((scenario) => isDemandScenarioCompatible(scenario, query)),
    [query, savedScenarios],
  );
  const hiddenScenarioCount = savedScenarios.length - compatibleSavedScenarios.length;
  const appliedScenarioVisible = driveWholePage && Object.keys(DEFAULT_DEMAND_LEVERS).some(
    (key) => appliedLevers[key] !== DEFAULT_DEMAND_LEVERS[key],
  );

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

      {dashboard.scope_limitations.length ? (
        <aside className="demand-scope-limitations" role="note" aria-label={t("Store scope limitations")}>
          <strong>{t("Store scope limitations")}</strong>
          <ul>
            {dashboard.scope_limitations.map((limitation) => <li key={limitation}>{t(limitation)}</li>)}
          </ul>
        </aside>
      ) : null}

      {appliedScenarioVisible ? (
        <DemandAppliedScenarioBanner
          levers={appliedLevers}
          definitions={dashboard.simulation.levers}
          onReset={resetScenario}
        />
      ) : null}

      {error ? (
        <div className="demand-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)}>{t("Retry")}</button>
        </div>
      ) : null}

      <DemandKpiGrid kpis={dashboard.kpis} onOpenDrilldown={openDrilldown} />

      <DemandKpiDrilldown
        drilldown={drilldown}
        onClose={() => setDrilldown(null)}
        onSelectSku={(sku) => patchQuery({ sku })}
      />

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

      <DemandDimensionPanels
        dimensions={dashboard.dimensions}
        onCategory={(category_group) => patchQuery({ category_group })}
        onStore={(store_id) => patchQuery({ store_id })}
        onLegalEntity={(legal_entity_id) => patchQuery({
          legal_entity_id,
          category_group: "ALL",
          store_id: "ALL",
        })}
      />

      {scenarioError ? <div className="demand-inline-error" role="alert">{scenarioError}</div> : null}
      <DemandWhatIfSimulator
        simulation={scenarioResult?.simulation || dashboard.simulation}
        draftLevers={draftLevers}
        onLeverChange={(id, value) => {
          setDraftLevers((current) => ({ ...current, [id]: value }));
          setScenarioDirty(true);
        }}
        onRun={() => runScenario()}
        onSave={saveScenario}
        onLoad={loadLatestScenario}
        onReset={resetScenario}
        driveWholePage={driveWholePage}
        onDriveWholePageChange={changeDriveWholePage}
        savedCount={savedScenarios.length}
        busy={scenarioBusy}
        canSave={Boolean(scenarioResult) && !scenarioDirty}
      />

      <DemandScenarioComparison
        baselineForecast={dashboard.simulation.baseline_forecast}
        scenarios={compatibleSavedScenarios}
        hiddenCount={hiddenScenarioCount}
        onRemove={(id) => setSavedScenarios((current) => current.filter((scenario) => scenario.id !== id))}
      />

      <DemandSuggestedActions actions={dashboard.suggested_actions} />
    </section>
  );
}
