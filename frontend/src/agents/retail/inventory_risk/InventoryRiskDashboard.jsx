import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import AgentHandoffInbox from "../../../components/AgentHandoffInbox.jsx";
import AtRiskByStatePanel from "./components/AtRiskByStatePanel.jsx";
import CategoryValueDonut from "./components/CategoryValueDonut.jsx";
import DimensionCharts from "./components/DimensionCharts.jsx";
import InventoryRiskFilters from "./components/InventoryRiskFilters.jsx";
import InventoryRiskSkeleton from "./components/InventoryRiskSkeleton.jsx";
import ProjectedOnHandPanel from "./components/ProjectedOnHandPanel.jsx";
import RiskAppliedScenarioBanner from "./components/RiskAppliedScenarioBanner.jsx";
import RiskKpiDrilldown from "./components/RiskKpiDrilldown.jsx";
import RiskKpiGrid from "./components/RiskKpiGrid.jsx";
import RiskRegisterTable from "./components/RiskRegisterTable.jsx";
import RiskScenarioComparison from "./components/RiskScenarioComparison.jsx";
import RiskWhatIfSimulator from "./components/RiskWhatIfSimulator.jsx";
import SuggestedBestAction from "./components/SuggestedBestAction.jsx";
import {
  ALL,
  BASELINE_LEVERS,
  DEFAULT_HORIZON_WEEKS,
  DEFAULT_SCOPE,
  GROSS_VS_NET_NOTE,
  PROJECTION_HORIZONS_WEEKS,
} from "./data/contract.js";
import {
  DATA_SOURCE,
  loadInventoryRiskDashboard,
  loadInventoryRiskDrilldown,
  loadInventoryRiskRows,
} from "./data/dashboardData.js";
import {
  buildDashboardFromFixture,
  computeLiveSimulation,
} from "./data/selectors.js";

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

/*
 * Frozen at module scope rather than built inline in the render. An object
 * literal in the render body is a new identity every pass, which would make
 * the scope-label memo below recompute on every render for no reason.
 */
const EMPTY_OPTIONS = Object.freeze({
  legal_entities: [],
  categories: [],
  stores: [],
  states: [],
  // Empty for everything the payload supplies, but the horizons are this
  // board's own and are known before any row arrives — an empty array here
  // would blank the control for one frame on every load.
  horizons_weeks: PROJECTION_HORIZONS_WEEKS,
});

/** A2 spec section 8d overlays the baseline plus at most four scenarios. */
const MAX_SAVED_SCENARIOS = 4;

export default function InventoryRiskDashboard() {
  const { t } = useLanguage();
  const [scope, setScope] = useState({ ...DEFAULT_SCOPE });
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);

  /*
   * Draft levers are what the sliders hold; applied levers are what the board
   * was built from. Separating them is what makes Run mean something — moving
   * a slider re-runs the workbook's formulas over 800 SKUs, and doing that on
   * every pixel of a drag would make the control fight the user.
   */
  const [draftLevers, setDraftLevers] = useState({ ...BASELINE_LEVERS });
  const [appliedLevers, setAppliedLevers] = useState({ ...BASELINE_LEVERS });
  const [driveWholePage, setDriveWholePage] = useState(true);
  /*
   * How far the projection runs (A2 spec section 7a). Held beside the levers
   * rather than inside `scope` for the reason the filter bar records: it
   * selects no rows. It is not cleared by Clear either — that button drops a
   * scope, and the horizon is not one.
   */
  const [horizonWeeks, setHorizonWeeks] = useState(DEFAULT_HORIZON_WEEKS);
  const [scenarios, setScenarios] = useState([]);
  // The KPI tile currently broken down, or null. Built on demand — see
  // `loadInventoryRiskDrilldown` for why it is not part of the board payload.
  const [drilldown, setDrilldown] = useState(null);
  /*
   * Raw rows for the current scope, held only so the What-If panel can
   * recompute its own live preview on every slider tick without a fetch per
   * tick — see `computeLiveSimulation`. Not the dashboard payload: these rows
   * commit to no lever position.
   */
  const [rawRows, setRawRows] = useState(null);

  useEffect(() => {
    let cancelled = false;
    loadInventoryRiskRows(scope).then((rows) => {
      if (!cancelled) setRawRows(rows);
    });
    return () => {
      cancelled = true;
    };
  }, [scope]);

  /*
   * Recomputed on every slider tick, not on Run — this is what makes the
   * panel's own chart and KPI strip dynamic while a lever is still being
   * dragged. It never touches the network (`rawRows` is already in hand) and
   * never rebuilds the rest of the board, which is exactly why it can afford
   * to run on every tick when `computeSimulation` over 800+ SKUs on every Run
   * cannot.
   */
  const liveSimulation = useMemo(() => {
    if (!rawRows) return null;
    return computeLiveSimulation(rawRows, scope, draftLevers, { horizonWeeks });
  }, [rawRows, scope, draftLevers, horizonWeeks]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadInventoryRiskDashboard(scope, {
          levers: appliedLevers,
          driveWholePage,
          horizonWeeks,
        });
        if (!cancelled) setDashboard(result);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || t("Unable to load Inventory Risk."));
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
    // moves — depending on the object is both correct and simpler than listing
    // its five fields. The same holds for `appliedLevers`, which only changes
    // on Run or Reset, never mid-drag.
  }, [scope, appliedLevers, driveWholePage, horizonWeeks, refreshToken, t]);

  const patchScope = useCallback((patch) => {
    setScope((current) => ({ ...current, ...patch }));
    // A filter change makes an open drawer describe rows that are no longer on
    // screen, so it closes rather than going quietly stale.
    setDrilldown(null);
  }, []);

  const clearScope = useCallback(() => {
    setScope({ ...DEFAULT_SCOPE });
    setDrilldown(null);
  }, []);

  const openDrilldown = useCallback(
    async (metricId) => {
      const built = await loadInventoryRiskDrilldown(scope, metricId, {
        levers: appliedLevers,
        driveWholePage,
        horizonWeeks,
      });
      setDrilldown(built);
    },
    [appliedLevers, driveWholePage, horizonWeeks, scope],
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
        projection: dashboard.simulation.projection,
      };
      // Oldest out first: the chart has five colours and reading a sixth line
      // is worse than losing the one saved longest ago.
      return [...current, next].slice(-MAX_SAVED_SCENARIOS);
    });
  }, [dashboard, t]);

  const activeDashboard = useMemo(() => {
    if (!rawRows) return dashboard;
    const effectiveLevers = driveWholePage ? draftLevers : appliedLevers;
    return buildDashboardFromFixture(rawRows, scope, {
      levers: effectiveLevers,
      driveWholePage,
      horizonWeeks,
    });
  }, [rawRows, scope, driveWholePage, draftLevers, appliedLevers, horizonWeeks, dashboard]);

  const display = activeDashboard || dashboard;

  const options = display?.filter_options ?? EMPTY_OPTIONS;

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

  if (!display && loading) {
    return (
      <section
        className="workboard inventory-risk-dashboard"
        data-testid="inventory-risk-dashboard"
      >
        <InventoryRiskSkeleton />
      </section>
    );
  }

  if (!display && error) {
    return (
      <section
        className="workboard inventory-risk-dashboard"
        data-testid="inventory-risk-dashboard"
      >
        <div className="workboard-status error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="risk-button"
            onClick={() => setRefreshToken((value) => value + 1)}
          >
            {t("Retry")}
          </button>
        </div>
      </section>
    );
  }

  const inventoryValue = display.kpis.inventory_value;

  return (
    <section
      className={`workboard inventory-risk-dashboard${loading ? " is-refreshing" : ""}`}
      data-testid="inventory-risk-dashboard"
      aria-label={t("Inventory Risk dashboard")}
      aria-busy={loading}
    >
      <InventoryRiskFilters
        scope={scope}
        options={options}
        horizonWeeks={horizonWeeks}
        busy={loading}
        onPatch={patchScope}
        /*
         * Not routed through `patchScope`: that closes the drill-down drawer,
         * which is correct for a filter that changes which rows exist and
         * wrong for a horizon, which changes none of them.
         */
        onHorizon={setHorizonWeeks}
        onSearch={(sku) => patchScope({ sku })}
        onRefresh={() => setRefreshToken((value) => value + 1)}
        onClear={clearScope}
      />

      <div className="risk-scope-row">
        <span className="risk-data-note">
          {display.is_mock ? t("Workbook data") : t("Live data")} · {t(display.note)}
        </span>
        <div className="risk-scope-summary">
          <span>{t("Scope")}:</span>
          {scopeLabels.length ? (
            scopeLabels.map((label) => <b key={label}>{label}</b>)
          ) : (
            <b>{t("All retail inventory")}</b>
          )}
          {scopeLabels.length ? (
            <button type="button" onClick={clearScope}>
              {t("Clear all")}
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="risk-inline-error" role="alert">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setRefreshToken((value) => value + 1)}
          >
            {t("Retry")}
          </button>
        </div>
      ) : null}

      <AgentHandoffInbox
        agentId="retail.inventory_risk"
        title={t("Demand Forecasting flags")}
        enabled={DATA_SOURCE === "api"}
      />

      {/*
        Above the KPIs on purpose. Every tile below is a simulated figure once
        levers drive the page, and a reader scrolling to a number should meet
        the warning before the number, not after it.
      */}
      <RiskAppliedScenarioBanner
        levers={display.simulation.levers}
        onClear={resetLevers}
      />

      <RiskKpiGrid
        kpis={display.kpis}
        sparklines={display.kpi_sparklines}
        // The reorder zone is Stockout plus Low, and the state filter takes one
        // value — so the drill lands on Stockout, the more urgent half, rather
        // than inventing a compound filter the contract does not carry.
        onDrillStockoutRisk={() =>
          patchScope({ state: scope.state === "Stockout" ? ALL : "Stockout" })
        }
        onOpenDrilldown={openDrilldown}
      />

      <RiskKpiDrilldown
        drilldown={drilldown}
        onClose={() => setDrilldown(null)}
        onSelectSku={(sku) => patchScope({ sku })}
      />

      <ProjectedOnHandPanel projection={display.projection} />

      <div className="risk-chart-grid">
        <AtRiskByStatePanel rows={display.at_risk_by_state} />
        <CategoryValueDonut
          rows={display.value_by_category}
          total={inventoryValue}
        />
      </div>

      <RiskRegisterTable
        rows={display.risk_register}
        onSelect={(sku) => patchScope({ sku })}
      />

      <DimensionCharts
        byCategory={display.at_risk_by_category}
        byStore={display.stockout_by_store}
        byCluster={display.at_risk_by_cluster}
        byLegalEntity={display.at_risk_by_legal_entity}
        expiryTimeline={display.expiry_timeline}
        scope={scope}
        onSelectCategory={(categoryId) =>
          patchScope({
            category_group:
              scope.category_group === categoryId ? ALL : categoryId,
          })
        }
        onSelectLegalEntity={(entityId) =>
          patchScope({
            legal_entity_id:
              scope.legal_entity_id === entityId ? ALL : entityId,
            category_group: ALL,
            store_id: ALL,
          })
        }
        onSelectExpirySku={(sku) => patchScope({ sku })}
      />

      <p className="risk-footnote">{t(GROSS_VS_NET_NOTE)}</p>

      <RiskWhatIfSimulator
        // The panel's own chart and KPI strip: recomputed on every tick, from
        // `draftLevers`, so they move while the slider is still being dragged.
        liveSimulation={liveSimulation}
        draftLevers={draftLevers}
        onLeverChange={(id, value) =>
          setDraftLevers((current) => ({ ...current, [id]: value }))
        }
        onRun={() => setAppliedLevers({ ...draftLevers })}
        onSave={saveScenario}
        onReset={resetLevers}
        driveWholePage={driveWholePage}
        onDriveWholePageChange={setDriveWholePage}
        canSave={display.simulation.applied && scenarios.length < MAX_SAVED_SCENARIOS}
        busy={loading}
      />

      <RiskScenarioComparison
        // The workbook's own curve, never the simulated one: a comparison
        // whose reference line moves with the sliders compares nothing.
        baseline={display.simulation.baseline_projection}
        scenarios={scenarios}
        onRemove={(id) =>
          setScenarios((current) => current.filter((entry) => entry.id !== id))
        }
      />

      {/*
        Last on the page, as in the mockup. The board diagnoses first and hands
        off second: a reader should arrive at the routing panel having already
        seen what it is routing.
      */}
      <SuggestedBestAction
        routes={display.best_actions}
        onSelect={(sku) => patchScope({ sku })}
      />
    </section>
  );
}
