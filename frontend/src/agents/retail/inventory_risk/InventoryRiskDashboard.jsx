import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import AtRiskByStatePanel from "./components/AtRiskByStatePanel.jsx";
import CategoryValueDonut from "./components/CategoryValueDonut.jsx";
import DimensionCharts from "./components/DimensionCharts.jsx";
import ExpiryTimelinePanel from "./components/ExpiryTimelinePanel.jsx";
import InventoryRiskFilters from "./components/InventoryRiskFilters.jsx";
import InventoryRiskSkeleton from "./components/InventoryRiskSkeleton.jsx";
import ProjectedOnHandPanel from "./components/ProjectedOnHandPanel.jsx";
import RiskAppliedScenarioBanner from "./components/RiskAppliedScenarioBanner.jsx";
import RiskKpiGrid from "./components/RiskKpiGrid.jsx";
import RiskRegisterTable from "./components/RiskRegisterTable.jsx";
import RiskScenarioComparison from "./components/RiskScenarioComparison.jsx";
import RiskWhatIfSimulator from "./components/RiskWhatIfSimulator.jsx";
import SuggestedBestAction from "./components/SuggestedBestAction.jsx";
import {
  ALL,
  BASELINE_LEVERS,
  DEFAULT_SCOPE,
  GROSS_VS_NET_NOTE,
} from "./data/contract.js";
import { loadInventoryRiskDashboard } from "./data/dashboardData.js";

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
  const [scenarios, setScenarios] = useState([]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadInventoryRiskDashboard(scope, {
          levers: appliedLevers,
          driveWholePage,
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
  }, [scope, appliedLevers, driveWholePage, refreshToken, t]);

  const patchScope = useCallback((patch) => {
    setScope((current) => ({ ...current, ...patch }));
  }, []);

  const clearScope = useCallback(() => {
    setScope({ ...DEFAULT_SCOPE });
  }, []);

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
      <section
        className="workboard inventory-risk-dashboard"
        data-testid="inventory-risk-dashboard"
      >
        <InventoryRiskSkeleton />
      </section>
    );
  }

  if (!dashboard && error) {
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

  const inventoryValue = dashboard.kpis.inventory_value;

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
        busy={loading}
        onPatch={patchScope}
        onSearch={(sku) => patchScope({ sku })}
        onRefresh={() => setRefreshToken((value) => value + 1)}
        onClear={clearScope}
      />

      <div className="risk-scope-row">
        <span className="risk-data-note">
          {dashboard.is_mock ? t("Workbook data") : t("Live data")} · {t(dashboard.note)}
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

      {/*
        Above the KPIs on purpose. Every tile below is a simulated figure once
        levers drive the page, and a reader scrolling to a number should meet
        the warning before the number, not after it.
      */}
      <RiskAppliedScenarioBanner
        levers={dashboard.simulation.levers}
        onClear={resetLevers}
      />

      <RiskKpiGrid
        kpis={dashboard.kpis}
        // The reorder zone is Stockout plus Low, and the state filter takes one
        // value — so the drill lands on Stockout, the more urgent half, rather
        // than inventing a compound filter the contract does not carry.
        onDrillStockoutRisk={() =>
          patchScope({ state: scope.state === "Stockout" ? ALL : "Stockout" })
        }
      />

      <ProjectedOnHandPanel projection={dashboard.projection} />

      <SuggestedBestAction
        routes={dashboard.best_actions}
        onSelect={(sku) => patchScope({ sku })}
      />

      <div className="risk-chart-grid">
        <AtRiskByStatePanel rows={dashboard.at_risk_by_state} />
        <CategoryValueDonut
          rows={dashboard.value_by_category}
          total={inventoryValue}
        />
      </div>

      <DimensionCharts
        byCategory={dashboard.at_risk_by_category}
        byStore={dashboard.stockout_by_store}
        byCluster={dashboard.at_risk_by_cluster}
        byLegalEntity={dashboard.at_risk_by_legal_entity}
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
      />

      <p className="risk-footnote">{t(GROSS_VS_NET_NOTE)}</p>

      <ExpiryTimelinePanel
        timeline={dashboard.expiry_timeline}
        onSelect={(sku) => patchScope({ sku })}
      />

      <RiskRegisterTable
        rows={dashboard.risk_register}
        onSelect={(sku) => patchScope({ sku })}
      />

      <RiskWhatIfSimulator
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

      <RiskScenarioComparison
        // The workbook's own curve, never the simulated one: a comparison
        // whose reference line moves with the sliders compares nothing.
        baseline={dashboard.simulation.baseline_projection}
        scenarios={scenarios}
        onRemove={(id) =>
          setScenarios((current) => current.filter((entry) => entry.id !== id))
        }
      />
    </section>
  );
}
