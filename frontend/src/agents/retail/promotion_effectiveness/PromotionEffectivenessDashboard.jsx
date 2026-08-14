import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import {
  MarginByCategoryChart,
  MarginByVerticalChart,
  SeasonMixChart,
  UpliftVsMarginChart,
} from "./components/PromoCharts.jsx";
import MarginLeadersTable from "./components/MarginLeadersTable.jsx";
import PromoAppliedScenarioBanner from "./components/PromoAppliedScenarioBanner.jsx";
import PromoCalendarTable from "./components/PromoCalendarTable.jsx";
import PromoEffectivenessFilters from "./components/PromotionEffectivenessFilters.jsx";
import PromoEffectivenessSkeleton from "./components/PromotionEffectivenessSkeleton.jsx";
import PromoKpiDrilldown from "./components/PromoKpiDrilldown.jsx";
import PromoKpiGrid from "./components/PromoKpiGrid.jsx";
import PromoScenarioComparison from "./components/PromoScenarioComparison.jsx";
import PromoWhatIfSimulator from "./components/PromoWhatIfSimulator.jsx";
import SuggestedBestAction from "./components/SuggestedBestAction.jsx";
import { ALL, BASELINE_LEVERS, DEFAULT_SCOPE, GRAIN_NOTE, UPLIFT_NOTE } from "./data/contract.js";
import { loadPromotionDashboard, loadPromotionDrilldown } from "./data/dashboardData.js";

const MAX_SAVED_SCENARIOS = 4;

const EMPTY_OPTIONS = Object.freeze({
  legal_entities: [],
  categories: [],
  stores: [],
});

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

/**
 * Agent 4 · Promotion Effectiveness board.
 *
 * Renders the six promo KPIs, the uplift-vs-margin combo chart, the by-vertical
 * and by-category margin charts, the campaign calendar preview, the suggested
 * best action tabs, the margin leaders list, and the What-If simulator with
 * compare-scenarios. Mirrors the Inventory Risk board's data-load contract.
 */
export default function PromotionEffectivenessDashboard() {
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
        const result = await loadPromotionDashboard(scope, {
          levers: appliedLevers,
          driveWholePage,
        });
        if (!cancelled) setDashboard(result);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || t("Unable to load Promotion Effectiveness."));
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
        const built = await loadPromotionDrilldown(scope, metricId, {
          levers: appliedLevers,
          driveWholePage,
        });
        setDrilldown(built);
      } catch (loadError) {
        // Non-drillable tiles (uplift, ROI — stored KPIs) have no row-level
        // decomposition; clicking them is a no-op rather than an error.
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
    if (scope.sku) labels.push(scope.sku);
    return labels;
  }, [options, scope]);

  if (!dashboard && loading) {
    return (
      <section
        className="workboard promotion-effectiveness-dashboard"
        data-testid="promotion-effectiveness-dashboard"
      >
        <PromoEffectivenessSkeleton />
      </section>
    );
  }

  if (!dashboard && error) {
    return (
      <section
        className="workboard promotion-effectiveness-dashboard"
        data-testid="promotion-effectiveness-dashboard"
      >
        <div className="workboard-status error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="promo-button"
            onClick={() => setRefreshToken((value) => value + 1)}
          >
            {t("Retry")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`workboard promotion-effectiveness-dashboard${loading ? " is-refreshing" : ""}`}
      data-testid="promotion-effectiveness-dashboard"
      aria-label={t("Promotion Effectiveness dashboard")}
      aria-busy={loading}
    >
      <PromoEffectivenessFilters
        scope={scope}
        options={options}
        busy={loading}
        onPatch={patchScope}
        onSearch={(sku) => patchScope({ sku })}
        onRefresh={() => setRefreshToken((value) => value + 1)}
        onClear={clearScope}
      />

      <div className="promo-scope-row">
        <span className="promo-data-note">
          {dashboard.is_mock ? t("Workbook data") : t("Live data")} · {t(dashboard.note)}
        </span>
        <div className="promo-scope-summary">
          <span>{t("Scope")}:</span>
          {scopeLabels.length ? (
            scopeLabels.map((label) => <b key={label}>{label}</b>)
          ) : (
            <b>{t("All retail promotions")}</b>
          )}
          {scopeLabels.length ? (
            <button type="button" onClick={clearScope}>
              {t("Clear all")}
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="promo-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)}>
            {t("Retry")}
          </button>
        </div>
      ) : null}

      <PromoAppliedScenarioBanner levers={dashboard.simulation.levers} onClear={resetLevers} />

      <PromoKpiGrid
        kpis={dashboard.kpis}
        sparklines={dashboard.kpi_sparklines}
        onOpenDrilldown={openDrilldown}
      />

      <PromoKpiDrilldown
        drilldown={drilldown}
        onClose={() => setDrilldown(null)}
        onSelectSku={(sku) => patchScope({ sku })}
      />

      <UpliftVsMarginChart rows={dashboard.by_vertical} />

      <div className="promo-chart-grid">
        <MarginByVerticalChart rows={dashboard.by_vertical} />
        <MarginByCategoryChart rows={dashboard.by_category} />
      </div>

      <p className="promo-footnote">{t(UPLIFT_NOTE)}</p>

      <PromoCalendarTable
        campaigns={dashboard.campaigns}
        onSelect={(promoId) => patchScope({ sku: promoId })}
      />

      <SuggestedBestAction
        groups={dashboard.best_actions}
        onSelect={(promoId) => patchScope({ sku: promoId })}
      />

      <SeasonMixChart rows={dashboard.by_season} />

      <MarginLeadersTable
        rows={dashboard.largest_margin_skus}
        onSelect={(sku) => patchScope({ sku })}
      />

      <p className="promo-footnote">{t(GRAIN_NOTE)}</p>

      <PromoWhatIfSimulator
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

      <PromoScenarioComparison
        baseline={dashboard.simulation.baseline}
        scenarios={scenarios}
        onRemove={(id) =>
          setScenarios((current) => current.filter((entry) => entry.id !== id))
        }
      />
    </section>
  );
}
