import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import AtRiskByStatePanel from "./components/AtRiskByStatePanel.jsx";
import CategoryValueDonut from "./components/CategoryValueDonut.jsx";
import DimensionCharts from "./components/DimensionCharts.jsx";
import ExpiryTimelinePanel from "./components/ExpiryTimelinePanel.jsx";
import InventoryRiskFilters from "./components/InventoryRiskFilters.jsx";
import InventoryRiskSkeleton from "./components/InventoryRiskSkeleton.jsx";
import RiskKpiGrid from "./components/RiskKpiGrid.jsx";
import RiskRegisterTable from "./components/RiskRegisterTable.jsx";
import { ALL, DEFAULT_SCOPE, GROSS_VS_NET_NOTE } from "./data/contract.js";
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

export default function InventoryRiskDashboard() {
  const { t } = useLanguage();
  const [scope, setScope] = useState({ ...DEFAULT_SCOPE });
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
        const result = await loadInventoryRiskDashboard(scope);
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
    // its five fields.
  }, [scope, refreshToken, t]);

  const patchScope = useCallback((patch) => {
    setScope((current) => ({ ...current, ...patch }));
  }, []);

  const clearScope = useCallback(() => {
    setScope({ ...DEFAULT_SCOPE });
  }, []);

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

      <RiskKpiGrid kpis={dashboard.kpis} />

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
    </section>
  );
}
