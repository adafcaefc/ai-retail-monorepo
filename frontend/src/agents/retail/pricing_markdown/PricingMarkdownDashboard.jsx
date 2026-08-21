import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import DimensionCharts from "./components/DimensionCharts.jsx";
import MarkdownCandidateTable from "./components/MarkdownCandidateTable.jsx";
import {
  AtRiskByCategoryChart,
  AtRiskByVerticalChart,
  AtRiskVsRecoverableChart,
} from "./components/PricingCharts.jsx";
import PricingAppliedScenarioBanner from "./components/PricingAppliedScenarioBanner.jsx";
import PricingKpiDrilldown from "./components/PricingKpiDrilldown.jsx";
import PricingKpiGrid from "./components/PricingKpiGrid.jsx";
import PricingMarkdownFilters from "./components/PricingMarkdownFilters.jsx";
import PricingMarkdownSkeleton from "./components/PricingMarkdownSkeleton.jsx";
import {
  // ElasticityVsDepthChart, RescueWaterfallChart -- commented out below,
  // per request, alongside their JSX. Keep the exports intact so this is a
  // one-line uncomment away from coming back.
  // ElasticityVsDepthChart,
  MarkdownLadderChart,
  // RescueWaterfallChart,
} from "./components/PricingRescueCharts.jsx";
import PricingScenarioComparison from "./components/PricingScenarioComparison.jsx";
import PricingWhatIfSimulator from "./components/PricingWhatIfSimulator.jsx";
import SuggestedBestAction from "./components/SuggestedBestAction.jsx";
import {
  ALL,
  BASELINE_LEVERS,
  CANDIDATE_SCOPE_NOTE,
  DEFAULT_LADDER_HORIZON,
  DEFAULT_SCOPE,
  GRAIN_NOTE,
} from "./data/contract.js";
import {
  buildPricingMarkdownDashboard,
  loadPricingMarkdownDrilldown,
  loadPricingMarkdownRows,
} from "./data/dashboardData.js";

const MAX_SAVED_SCENARIOS = 4;

const EMPTY_OPTIONS = Object.freeze({
  legal_entities: [],
  categories: [],
  stores: [],
  states: [],
});

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

/**
 * Agent 5 · Pricing & Markdown board.
 *
 * Renders the six markdown KPIs, the at-risk-vs-recoverable combo chart, the
 * by-vertical and by-category charts, the markdown candidate table, the
 * suggested best action tabs, the store/cluster/channel/state/legal-entity
 * dimension charts, and the What-If simulator with compare-scenarios.
 * Mirrors PromotionEffectivenessDashboard.jsx's data-load contract.
 */
export default function PricingMarkdownDashboard() {
  const { t } = useLanguage();
  const [scope, setScope] = useState({ ...DEFAULT_SCOPE });
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  const [levers, setLevers] = useState({ ...BASELINE_LEVERS });
  const [driveWholePage, setDriveWholePage] = useState(true);
  const [scenarios, setScenarios] = useState([]);
  const [drilldown, setDrilldown] = useState(null);
  // The ladder chart's Horizon control (filter bar) -- a pure client-side
  // slice of dashboard.ladder_history, never a refetch; see contract.js's
  // LADDER_HORIZONS docstring.
  const [ladderHorizon, setLadderHorizon] = useState(DEFAULT_LADDER_HORIZON);

  // Fetch depends only on scope: serializeScope never encodes levers, so a
  // slider move never needs a network round-trip (see dashboardData.js).
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadPricingMarkdownRows(scope);
        if (!cancelled) setRows(result);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || t("Unable to load Pricing & Markdown."));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [scope, refreshToken, t]);

  // Deferred so dragging a lever stays smooth even though the rebuild below
  // touches up to 16,000 rows — the simulator and (with "Drive whole page")
  // the rest of the dashboard still update live, no Run click, just a frame
  // behind the input rather than blocking it.
  const deferredLevers = useDeferredValue(levers);

  const { dashboard, buildError } = useMemo(() => {
    if (!rows) return { dashboard: null, buildError: null };
    try {
      return {
        dashboard: buildPricingMarkdownDashboard(rows, scope, { levers: deferredLevers, driveWholePage }),
        buildError: null,
      };
    } catch (buildErr) {
      return { dashboard: null, buildError: buildErr.message || t("Unable to load Pricing & Markdown.") };
    }
  }, [rows, scope, deferredLevers, driveWholePage, t]);

  useEffect(() => {
    if (buildError) setError(buildError);
  }, [buildError]);

  const patchScope = useCallback((patch) => {
    setScope((current) => ({ ...current, ...patch }));
    setDrilldown(null);
  }, []);

  const clearScope = useCallback(() => {
    setScope({ ...DEFAULT_SCOPE });
    setDrilldown(null);
  }, []);

  // Chart-click filtering, mirroring demand_forecasting's onCategory/onStore/
  // onLegalEntity: each dimension chart's bar or filter-shortcut pill calls
  // one of these (also with ALL, from that chart's own "Back to all X"
  // reset button). selectVertical resets category/store too, same as
  // demand_forecasting's onLegalEntity — a category or store valid under one
  // vertical can be meaningless (or simply absent) under another.
  const selectCategory = useCallback((category_group) => patchScope({ category_group }), [patchScope]);
  const selectStore = useCallback((store_id) => patchScope({ store_id }), [patchScope]);
  const selectState = useCallback((state) => patchScope({ state }), [patchScope]);
  const selectVertical = useCallback(
    (legal_entity_id) => patchScope({ legal_entity_id, category_group: ALL, store_id: ALL }),
    [patchScope],
  );

  const openDrilldown = useCallback(
    async (metricId) => {
      try {
        const built = await loadPricingMarkdownDrilldown(scope, metricId, {
          levers: deferredLevers,
          driveWholePage,
        });
        setDrilldown(built);
      } catch (loadError) {
        if (loadError.message?.includes("not drillable")) return;
        setError(loadError.message || t("Unable to open the drill-down."));
      }
    },
    [deferredLevers, driveWholePage, scope, t],
  );

  const resetLevers = useCallback(() => {
    setLevers({ ...BASELINE_LEVERS });
  }, []);

  const saveScenario = useCallback(() => {
    if (!dashboard?.simulation?.applied) return;
    setScenarios((current) => {
      const next = {
        id: `sc-${Date.now()}`,
        name: `${t("Scenario")} ${current.length + 1}`,
        levers: { ...dashboard.simulation.levers },
        kpis: dashboard.simulation.scenario,
      };
      return [...current, next].slice(-MAX_SAVED_SCENARIOS);
    });
  }, [dashboard, t]);

  const options = dashboard?.filter_options ?? EMPTY_OPTIONS;

  const scopeLabels = useMemo(() => {
    const labels = [];
    if (scope.legal_entity_id !== ALL) {
      labels.push(optionLabel(options.legal_entities, scope.legal_entity_id));
    }
    if (scope.category_group !== ALL) {
      labels.push(optionLabel(options.categories, scope.category_group));
    }
    if (scope.state !== ALL) labels.push(t(scope.state));
    if (scope.sku) labels.push(scope.sku);
    return labels;
  }, [options, scope, t]);

  if (!dashboard && loading) {
    return (
      <section className="workboard pricing-markdown-dashboard" data-testid="pricing-markdown-dashboard">
        <PricingMarkdownSkeleton />
      </section>
    );
  }

  if (!dashboard && error) {
    return (
      <section className="workboard pricing-markdown-dashboard" data-testid="pricing-markdown-dashboard">
        <div className="workboard-status error" role="alert">
          <p>{error}</p>
          <button type="button" className="pricing-button" onClick={() => setRefreshToken((v) => v + 1)}>
            {t("Retry")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`workboard pricing-markdown-dashboard${loading ? " is-refreshing" : ""}`}
      data-testid="pricing-markdown-dashboard"
      aria-label={t("Pricing & Markdown dashboard")}
      aria-busy={loading}
    >
      <PricingMarkdownFilters
        scope={scope}
        options={options}
        busy={loading}
        onPatch={patchScope}
        onSearch={(sku) => patchScope({ sku })}
        onRefresh={() => setRefreshToken((v) => v + 1)}
        onClear={clearScope}
        ladderHorizon={ladderHorizon}
        onLadderHorizonChange={setLadderHorizon}
      />

      <div className="pricing-scope-row">
        <div className="pricing-scope-summary">
          <span>{t("Scope")}:</span>
          {scopeLabels.length ? (
            scopeLabels.map((label) => <b key={label}>{label}</b>)
          ) : (
            <b>{t("All markdown candidates")}</b>
          )}
          {scopeLabels.length ? (
            <button type="button" onClick={clearScope}>
              {t("Clear all")}
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="pricing-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshToken((v) => v + 1)}>
            {t("Retry")}
          </button>
        </div>
      ) : null}

      <PricingAppliedScenarioBanner levers={dashboard.simulation.levers} onClear={resetLevers} />

      <PricingKpiGrid kpis={dashboard.kpis} sparklines={dashboard.kpi_sparklines} onOpenDrilldown={openDrilldown} />

      <PricingKpiDrilldown drilldown={drilldown} onClose={() => setDrilldown(null)} onSelectSku={(sku) => patchScope({ sku })} />

      <p className="pricing-footnote">{t(CANDIDATE_SCOPE_NOTE)}</p>

      <AtRiskVsRecoverableChart rows={dashboard.by_vertical} />

      <MarkdownLadderChart rows={dashboard.ladder_history} horizon={ladderHorizon} kpis={dashboard.kpis} />

      {/* Rescue waterfall / Elasticity vs depth — commented out per request.
      <div className="pricing-chart-grid">
        <RescueWaterfallChart kpis={dashboard.kpis} />
        <ElasticityVsDepthChart rows={dashboard.candidates} />
      </div>
      */}

      <div className="pricing-chart-grid">
        <AtRiskByVerticalChart rows={dashboard.by_vertical} selected={scope.legal_entity_id} onSelect={selectVertical} />
        <AtRiskByCategoryChart rows={dashboard.by_category} selected={scope.category_group} onSelect={selectCategory} />
      </div>

      <p className="pricing-footnote">{t(GRAIN_NOTE)}</p>

      <MarkdownCandidateTable candidates={dashboard.candidates} onSelect={(sku) => patchScope({ sku })} />

      <SuggestedBestAction groups={dashboard.best_actions} onSelect={(sku) => patchScope({ sku })} />

      <DimensionCharts
        byStore={dashboard.by_store}
        byCluster={dashboard.by_cluster}
        byChannel={dashboard.by_channel}
        byState={dashboard.by_state}
        byLegalEntity={dashboard.by_legal_entity}
        scope={scope}
        onSelectStore={selectStore}
        onSelectState={selectState}
        onSelectLegalEntity={selectVertical}
      />

      <PricingWhatIfSimulator
        simulation={dashboard.simulation}
        levers={levers}
        onLeverChange={(id, value) => setLevers((current) => ({ ...current, [id]: value }))}
        onSave={saveScenario}
        onReset={resetLevers}
        driveWholePage={driveWholePage}
        onDriveWholePageChange={setDriveWholePage}
        canSave={dashboard.simulation.applied && scenarios.length < MAX_SAVED_SCENARIOS}
        busy={loading}
      />

      <PricingScenarioComparison
        baseline={dashboard.simulation.baseline}
        scenarios={scenarios}
        onRemove={(id) => setScenarios((current) => current.filter((entry) => entry.id !== id))}
      />
    </section>
  );
}
