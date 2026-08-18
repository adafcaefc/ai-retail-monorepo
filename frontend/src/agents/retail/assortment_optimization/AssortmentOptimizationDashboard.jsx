import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import ActionPreviewTable from "./components/ActionPreviewTable.jsx";
import AssortmentAppliedScenarioBanner from "./components/AssortmentAppliedScenarioBanner.jsx";
import {
  ContributionByCategoryChart,
  ContributionByVerticalChart,
  DelistVsGrowQuadrant,
} from "./components/AssortmentCharts.jsx";
import AssortmentFilters from "./components/AssortmentFilters.jsx";
import AssortmentKpiDrilldown from "./components/AssortmentKpiDrilldown.jsx";
import AssortmentKpiGrid from "./components/AssortmentKpiGrid.jsx";
import AssortmentScenarioComparison from "./components/AssortmentScenarioComparison.jsx";
import AssortmentSkeleton from "./components/AssortmentSkeleton.jsx";
import AssortmentWhatIfSimulator from "./components/AssortmentWhatIfSimulator.jsx";
import DimensionCharts from "./components/DimensionCharts.jsx";
import SuggestedBestAction from "./components/SuggestedBestAction.jsx";
import {
  ALL,
  BASELINE_LEVERS,
  CAPITAL_FREED_NOTE,
  DEFAULT_SCOPE,
  GMROI_NOTE,
  GRAIN_NOTE,
} from "./data/contract.js";
import { loadAssortmentDashboard, loadAssortmentDrilldown } from "./data/dashboardData.js";

const MAX_SAVED_SCENARIOS = 4;

const EMPTY_OPTIONS = Object.freeze({
  legal_entities: [],
  categories: [],
  stores: [],
  classifications: [],
});

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

/**
 * Agent 6 · Assortment Optimization board.
 *
 * Renders the six assortment KPIs, the delist-vs-grow quadrant, the
 * contribution charts, the action preview table, the four best-action tabs,
 * the store/cluster/channel/state/legal-entity dimension charts, and the
 * What-If simulator with compare-scenarios.
 */
export default function AssortmentOptimizationDashboard() {
  const { t } = useLanguage();
  const [scope, setScope] = useState({ ...DEFAULT_SCOPE });
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  const [draftLevers, setDraftLevers] = useState({ ...BASELINE_LEVERS });
  const [appliedLevers, setAppliedLevers] = useState({ ...BASELINE_LEVERS });
  const [driveWholePage, setDriveWholePage] = useState(true);
  const [scenarios, setScenarios] = useState([]);
  const [drilldown, setDrilldown] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadAssortmentDashboard(scope, {
          levers: appliedLevers,
          driveWholePage,
        });
        if (!cancelled) setDashboard(result);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || t("Unable to load Assortment Optimization."));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [scope, appliedLevers, driveWholePage, refreshToken, t]);

  const patchScope = useCallback((patch) => {
    setScope((current) => ({ ...current, ...patch }));
    setDrilldown(null);
  }, []);

  const clearScope = useCallback(() => {
    setScope({ ...DEFAULT_SCOPE });
    setDrilldown(null);
  }, []);

  const openDrilldown = useCallback(
    async (metricId) => {
      try {
        const built = await loadAssortmentDrilldown(scope, metricId, {
          levers: appliedLevers,
          driveWholePage,
        });
        setDrilldown(built);
      } catch (loadError) {
        // Counts and tail share have no row-level decomposition; clicking
        // those tiles is a no-op rather than an error.
        if (loadError.message?.includes("not drillable")) return;
        setError(loadError.message || t("Unable to open the drill-down."));
      }
    },
    [appliedLevers, driveWholePage, scope, t],
  );

  const resetLevers = useCallback(() => {
    setDraftLevers({ ...BASELINE_LEVERS });
    setAppliedLevers({ ...BASELINE_LEVERS });
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
    if (scope.classification !== ALL) labels.push(t(scope.classification));
    if (scope.sku) labels.push(scope.sku);
    return labels;
  }, [options, scope, t]);

  if (!dashboard && loading) {
    return (
      <section
        className="workboard assortment-optimization-dashboard"
        data-testid="assortment-optimization-dashboard"
      >
        <AssortmentSkeleton />
      </section>
    );
  }

  if (!dashboard && error) {
    return (
      <section
        className="workboard assortment-optimization-dashboard"
        data-testid="assortment-optimization-dashboard"
      >
        <div className="workboard-status error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="assortment-button"
            onClick={() => setRefreshToken((v) => v + 1)}
          >
            {t("Retry")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`workboard assortment-optimization-dashboard${loading ? " is-refreshing" : ""}`}
      data-testid="assortment-optimization-dashboard"
      aria-label={t("Assortment Optimization dashboard")}
      aria-busy={loading}
    >
      <AssortmentFilters
        scope={scope}
        options={options}
        busy={loading}
        onPatch={patchScope}
        onSearch={(sku) => patchScope({ sku })}
        onRefresh={() => setRefreshToken((v) => v + 1)}
        onClear={clearScope}
      />

      <div className="assortment-scope-row">
        <span className="assortment-data-note">
          {dashboard.is_mock ? t("Workbook data") : t("Live data")} · {t(dashboard.note)}
        </span>
        <div className="assortment-scope-summary">
          <span>{t("Scope")}:</span>
          {scopeLabels.length ? (
            scopeLabels.map((label) => <b key={label}>{label}</b>)
          ) : (
            <b>{t("Whole range")}</b>
          )}
          {scopeLabels.length ? (
            <button type="button" onClick={clearScope}>
              {t("Clear all")}
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="assortment-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshToken((v) => v + 1)}>
            {t("Retry")}
          </button>
        </div>
      ) : null}

      <AssortmentAppliedScenarioBanner
        levers={dashboard.simulation.levers}
        onClear={resetLevers}
      />

      <AssortmentKpiGrid
        kpis={dashboard.kpis}
        sparklines={dashboard.kpi_sparklines}
        onOpenDrilldown={openDrilldown}
      />

      <AssortmentKpiDrilldown
        drilldown={drilldown}
        onClose={() => setDrilldown(null)}
        onSelectSku={(sku) => patchScope({ sku })}
      />

      <p className="assortment-footnote">{t(CAPITAL_FREED_NOTE)}</p>

      <DelistVsGrowQuadrant
        points={dashboard.quadrant}
        thresholds={dashboard.classification_thresholds}
        onSelectSku={(sku) => (sku ? patchScope({ sku }) : undefined)}
      />

      <p className="assortment-footnote">{t(GMROI_NOTE)}</p>

      <div className="assortment-chart-grid">
        <ContributionByVerticalChart rows={dashboard.by_vertical} />
        <ContributionByCategoryChart rows={dashboard.by_category} />
      </div>

      <ActionPreviewTable
        rows={dashboard.action_preview}
        onSelect={(sku) => patchScope({ sku })}
      />

      <SuggestedBestAction
        groups={dashboard.best_actions}
        onSelect={(sku) => patchScope({ sku })}
      />

      <DimensionCharts
        byStore={dashboard.by_store}
        byCluster={dashboard.by_cluster}
        byChannel={dashboard.by_channel}
        byState={dashboard.by_state}
        byLegalEntity={dashboard.by_legal_entity}
      />

      <p className="assortment-footnote">{t(GRAIN_NOTE)}</p>

      <AssortmentWhatIfSimulator
        simulation={dashboard.simulation}
        draftLevers={draftLevers}
        onLeverChange={(id, value) =>
          setDraftLevers((current) => ({ ...current, [id]: value }))
        }
        onRun={() => setAppliedLevers({ ...draftLevers })}
        onSave={saveScenario}
        onReset={resetLevers}
        driveWholePage={driveWholePage}
        onDriveWholePageChange={setDriveWholePage}
        canSave={dashboard.simulation.applied && scenarios.length < MAX_SAVED_SCENARIOS}
        busy={loading}
      />

      <AssortmentScenarioComparison
        baseline={dashboard.simulation.baseline}
        scenarios={scenarios}
        onRemove={(id) => setScenarios((current) => current.filter((entry) => entry.id !== id))}
      />
    </section>
  );
}
