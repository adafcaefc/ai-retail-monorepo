import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import AgentHandoffInbox from "../../../components/AgentHandoffInbox.jsx";
import OrderDimensionCharts from "./components/OrderDimensionCharts.jsx";
import PurchaseOrderTable from "./components/PurchaseOrderTable.jsx";
import ReplenishmentAppliedScenarioBanner from "./components/ReplenishmentAppliedScenarioBanner.jsx";
import ReplenishmentFilters from "./components/ReplenishmentFilters.jsx";
import ReplenishmentKpiDrilldown from "./components/ReplenishmentKpiDrilldown.jsx";
import ReplenishmentKpiGrid from "./components/ReplenishmentKpiGrid.jsx";
import ReplenishmentScenarioComparison from "./components/ReplenishmentScenarioComparison.jsx";
import ReplenishmentSkeleton from "./components/ReplenishmentSkeleton.jsx";
import ReplenishmentWhatIfSimulator from "./components/ReplenishmentWhatIfSimulator.jsx";
import RequirementVsInboundPanel from "./components/RequirementVsInboundPanel.jsx";
import RouteBreakdownPanel from "./components/RouteBreakdownPanel.jsx";
import VendorQuotePanel from "./components/VendorQuotePanel.jsx";
import VendorSourcingPanel from "./components/VendorSourcingPanel.jsx";
import {
  ALL,
  BASELINE_LEVERS,
  DEFAULT_SCOPE,
  MAX_SAVED_SCENARIOS,
} from "./data/contract.js";
import {
  DATA_SOURCE,
  loadReplenishmentDashboard,
  loadReplenishmentDrilldown,
} from "./data/dashboardData.js";

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

/*
 * Frozen at module scope rather than built inline in the render. An object
 * literal in the render body is a new identity every pass, which would make the
 * scope-label memo below recompute on every render for no reason.
 */
const EMPTY_OPTIONS = Object.freeze({
  legal_entities: [],
  categories: [],
  stores: [],
  routes: [],
});

export default function ReplenishmentDashboard() {
  const { t } = useLanguage();
  const [scope, setScope] = useState({ ...DEFAULT_SCOPE });
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  /*
   * Draft levers are what the sliders hold; applied levers are what the board
   * was built from. Separating them is what makes Run mean something — moving a
   * slider re-runs the workbook's formulas over 800 lines, and doing that on
   * every pixel of a drag would make the control fight the user.
   */
  const [draftLevers, setDraftLevers] = useState({ ...BASELINE_LEVERS });
  const [appliedLevers, setAppliedLevers] = useState({ ...BASELINE_LEVERS });
  const [driveWholePage, setDriveWholePage] = useState(true);
  const [scenarios, setScenarios] = useState([]);
  // The KPI tile currently broken down, or null. Built on demand rather than
  // carried on the payload — see `loadReplenishmentDrilldown`.
  const [drilldown, setDrilldown] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadReplenishmentDashboard(scope, {
          levers: appliedLevers,
          driveWholePage,
        });
        if (!cancelled) setDashboard(result);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || t("Unable to load Replenishment."));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
    // `scope` is state, so its identity only changes when a filter actually
    // moves. The same holds for `appliedLevers`, which changes on Run or Reset
    // and never mid-drag.
  }, [scope, appliedLevers, driveWholePage, refreshToken, t]);

  const patchScope = useCallback((patch) => {
    setScope((current) => ({ ...current, ...patch }));
    // A filter change makes an open drawer describe lines that are no longer
    // on screen, so it closes rather than going quietly stale.
    setDrilldown(null);
  }, []);

  const clearScope = useCallback(() => {
    setScope({ ...DEFAULT_SCOPE });
    setDrilldown(null);
  }, []);

  const openDrilldown = useCallback(
    async (metricId) => {
      setDrilldown(
        await loadReplenishmentDrilldown(scope, metricId, {
          levers: appliedLevers,
          driveWholePage,
        }),
      );
    },
    [appliedLevers, driveWholePage, scope],
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
        requirement: dashboard.simulation.requirement,
      };
      // Oldest out first: the chart has five colours, and reading a sixth line
      // is worse than losing the one saved longest ago.
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
    if (scope.route !== ALL) labels.push(optionLabel(options.routes, scope.route));
    if (scope.sku) labels.push(scope.sku);
    return labels;
  }, [options, scope]);

  if (!dashboard && loading) {
    return (
      <section
        className="workboard replenishment-dashboard"
        data-testid="replenishment-dashboard"
      >
        <ReplenishmentSkeleton />
      </section>
    );
  }

  if (!dashboard && error) {
    return (
      <section
        className="workboard replenishment-dashboard"
        data-testid="replenishment-dashboard"
      >
        <div className="workboard-status error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="po-button"
            onClick={() => setRefreshToken((value) => value + 1)}
          >
            {t("Retry")}
          </button>
        </div>
      </section>
    );
  }

  const { simulation } = dashboard;

  return (
    <section
      className={`workboard replenishment-dashboard${loading ? " is-refreshing" : ""}`}
      data-testid="replenishment-dashboard"
      aria-label={t("Replenishment dashboard")}
      aria-busy={loading}
    >
      <ReplenishmentFilters
        scope={scope}
        options={options}
        busy={loading}
        onPatch={patchScope}
        onSearch={(sku) => patchScope({ sku })}
        onClear={clearScope}
      />

      <div className="po-scope-row">
        <div className="po-scope-summary">
          <span>{t("Scope")}:</span>
          {scopeLabels.length ? (
            scopeLabels.map((label) => <b key={label}>{label}</b>)
          ) : (
            <b>{t("Whole chain")}</b>
          )}
          {scopeLabels.length ? (
            <button type="button" onClick={clearScope}>
              {t("Clear all")}
            </button>
          ) : null}
        </div>
      </div>

      {/* Only when levers actually reach the board. A2 spec 8b, A3 spec 9b. */}
      {simulation.applied && driveWholePage ? (
        <ReplenishmentAppliedScenarioBanner
          levers={simulation.levers}
          onClear={resetLevers}
        />
      ) : null}

      {error ? (
        <div className="po-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)}>
            {t("Retry")}
          </button>
        </div>
      ) : null}

      <AgentHandoffInbox
        agentId="retail.replenishment"
        title={t("Received forecast baskets")}
        enabled={DATA_SOURCE === "api"}
      />

      <ReplenishmentKpiGrid
        kpis={dashboard.kpis}
        sparklines={dashboard.kpi_sparklines}
        onDrillReorder={() => patchScope({ reorder_only: !scope.reorder_only })}
        onOpenDrilldown={openDrilldown}
      />

      <ReplenishmentKpiDrilldown
        drilldown={drilldown}
        onClose={() => setDrilldown(null)}
        onSelectSku={(sku) => patchScope({ sku })}
      />

      <RequirementVsInboundPanel
        requirement={dashboard.requirement}
      />

      <div className="po-chart-grid">
        <RouteBreakdownPanel
          routes={dashboard.by_route}
          activeRoute={scope.route === ALL ? null : scope.route}
          onSelect={(route) =>
            patchScope({ route: scope.route === route ? ALL : route })
          }
        />
        <VendorSourcingPanel
          split={dashboard.vendor_split}
          vendors={dashboard.vendors ?? []}
        />
      </div>

      {/* Directly under the per-vendor totals: the same money, itemised. */}
      <VendorQuotePanel sourcing={dashboard.sourcing} />

      <OrderDimensionCharts
        byCategory={dashboard.by_category}
        byStore={dashboard.by_store}
        byCluster={dashboard.by_cluster}
        byLegalEntity={dashboard.by_legal_entity}
        onSelectCategory={(categoryId) =>
          patchScope({
            category_group: scope.category_group === categoryId ? ALL : categoryId,
          })
        }
        onSelectLegalEntity={(legalEntityId) =>
          // A category or store from the previous vertical cannot exist under
          // the new one, so reset both rather than load an empty scope — the
          // same reset the filter bar's entity select performs.
          patchScope(
            scope.legal_entity_id === legalEntityId
              ? { legal_entity_id: ALL }
              : {
                  legal_entity_id: legalEntityId,
                  category_group: ALL,
                  store_id: ALL,
                },
          )
        }
      />

      <PurchaseOrderTable
        rows={dashboard.purchase_order}
        routes={dashboard.routes}
        asOf={dashboard.as_of}
        onSelect={(sku) => patchScope({ sku })}
      />

      <ReplenishmentWhatIfSimulator
        simulation={simulation}
        draftLevers={draftLevers}
        onLeverChange={(id, value) =>
          setDraftLevers((current) => ({ ...current, [id]: value }))
        }
        onRun={() => setAppliedLevers({ ...draftLevers })}
        onSave={saveScenario}
        onReset={resetLevers}
        driveWholePage={driveWholePage}
        onDriveWholePageChange={setDriveWholePage}
        canSave={simulation.applied}
        busy={loading}
      />

      <ReplenishmentScenarioComparison
        baseline={simulation.baseline_requirement}
        scenarios={scenarios}
        onRemove={(id) =>
          setScenarios((current) => current.filter((entry) => entry.id !== id))
        }
      />
    </section>
  );
}
