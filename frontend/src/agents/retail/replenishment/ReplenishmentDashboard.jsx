import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import OrderDimensionCharts from "./components/OrderDimensionCharts.jsx";
import PurchaseOrderTable from "./components/PurchaseOrderTable.jsx";
import ReplenishmentFilters from "./components/ReplenishmentFilters.jsx";
import ReplenishmentKpiGrid from "./components/ReplenishmentKpiGrid.jsx";
import RouteBreakdownPanel from "./components/RouteBreakdownPanel.jsx";
import VendorSourcingPanel from "./components/VendorSourcingPanel.jsx";
import { ALL, DEFAULT_SCOPE, ORDER_VALUE_NOTE } from "./data/contract.js";
import { loadReplenishmentDashboard } from "./data/dashboardData.js";

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

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

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const result = await loadReplenishmentDashboard(scope);
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
  }, [scope, refreshToken, t]);

  const patchScope = useCallback((patch) => {
    setScope((current) => ({ ...current, ...patch }));
  }, []);

  const clearScope = useCallback(() => setScope({ ...DEFAULT_SCOPE }), []);

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
        <div className="workboard-status" role="status" aria-label={t("Loading Replenishment")}>
          <p>{t("Loading…")}</p>
        </div>
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
        <span className="po-data-note">
          {dashboard.is_mock ? t("Workbook data") : t("Live data")} · {t(dashboard.note)}
        </span>
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

      {error ? (
        <div className="po-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshToken((value) => value + 1)}>
            {t("Retry")}
          </button>
        </div>
      ) : null}

      <ReplenishmentKpiGrid
        kpis={dashboard.kpis}
        onDrillReorder={() => patchScope({ reorder_only: !scope.reorder_only })}
      />

      <p className="po-footnote">{t(ORDER_VALUE_NOTE)}</p>

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

      <OrderDimensionCharts
        byCategory={dashboard.by_category}
        byStore={dashboard.by_store}
        byCluster={dashboard.by_cluster}
        onSelectCategory={(categoryId) =>
          patchScope({
            category_group: scope.category_group === categoryId ? ALL : categoryId,
          })
        }
      />

      <PurchaseOrderTable
        rows={dashboard.purchase_order}
        onSelect={(sku) => patchScope({ sku })}
      />
    </section>
  );
}
