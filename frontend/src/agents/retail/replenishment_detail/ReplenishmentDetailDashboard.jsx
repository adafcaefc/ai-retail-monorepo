import { useCallback, useEffect, useMemo, useState } from "react";

import { useLanguage } from "../../../LanguageProvider.jsx";
import LineInspector from "./components/LineInspector.jsx";
import ReplenishmentDetailFilters from "./components/ReplenishmentDetailFilters.jsx";
import ReplenishmentDetailGrid from "./components/ReplenishmentDetailGrid.jsx";
import ReplenishmentDetailKpiStrip from "./components/ReplenishmentDetailKpiStrip.jsx";
import ReplenishmentDetailSkeleton from "./components/ReplenishmentDetailSkeleton.jsx";
import UomBreakdownPanel from "./components/UomBreakdownPanel.jsx";
import {
  ALL,
  DEFAULT_SCOPE,
  DEFAULT_SORT,
  GRAIN_NOTE,
  PACK_ROUNDING_NOTE,
} from "./data/contract.js";
import { loadReplenishmentDetailDashboard } from "./data/dashboardData.js";
import {
  buildInspector,
  computeExceptionCounts,
  computeFilterFacets,
  computeKpis,
  computeUomBreakdown,
  scopeLines,
  sortLines,
} from "./data/selectors.js";

/**
 * Agent 3.1 · Replenishment Detail.
 *
 * The line-level evidence behind Agent 3's recommendations: one row per SKU,
 * all nineteen workbook columns, and an inspector that shows the arithmetic
 * rather than asserting the result.
 *
 * SCOPE LIVES HERE, and only two of its keys reach the server. Vertical and
 * Category narrow the SQL; the other eight narrow rows already on the page.
 * `serializeScope` decides what travels, so a filter added to `DEFAULT_SCOPE`
 * is client-side until somebody deliberately adds it to that list.
 *
 * NO FIXTURE FALLBACK. A failed request renders the error branch below rather
 * than silently swapping in demo data — see `dashboardData.js`.
 */
export default function ReplenishmentDetailDashboard() {
  const { t } = useLanguage();

  const [scope, setScope] = useState(DEFAULT_SCOPE);
  const [sort, setSort] = useState(DEFAULT_SORT);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [selectedSku, setSelectedSku] = useState(null);

  /*
   * Only the two server-side keys are in the dependency list. The rest are
   * applied by `useMemo` below over rows already in hand, so changing a vendor
   * filter must not cost a round trip — and listing them here would make every
   * keystroke-free filter change refetch 800 rows.
   */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    loadReplenishmentDetailDashboard({
      legal_entity_id: scope.legal_entity_id,
      category_group: scope.category_group,
    })
      .then((payload) => {
        if (cancelled) return;
        setDashboard(payload);
        setError("");
      })
      .catch((cause) => {
        if (cancelled) return;
        setError(cause.message || String(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [scope.legal_entity_id, scope.category_group, refreshToken]);

  // The client-side narrowing, recomputed from the rows the request returned.
  const view = useMemo(() => {
    if (!dashboard) return null;
    return rebuild(dashboard, scope, sort);
  }, [dashboard, scope, sort]);

  const patchScope = useCallback((patch) => {
    // A filter change makes an open inspector stale — the line it describes
    // may no longer be in the result.
    setSelectedSku(null);
    setScope((current) => ({ ...current, ...patch }));
  }, []);

  const toggleSort = useCallback((columnId) => {
    setSort((current) =>
      current.by === columnId
        ? { by: columnId, direction: current.direction === "asc" ? "desc" : "asc" }
        : // A new column starts descending, because every numeric column on
          // this board is one where "most" is what a planner is looking for.
          { by: columnId, direction: "desc" },
    );
  }, []);

  const onSelectTile = useCallback(
    (tileId) => {
      if (tileId === "reorder_sku_count") patchScope({ reorder_status: "YES" });
      if (tileId === "potential_saving") patchScope({ saving_only: true });
      if (tileId === "alternate_vendor_count") patchScope({ saving_only: true });
      if (tileId === "purchase_amount") setSort({ by: "amount", direction: "desc" });
      if (tileId === "order_qty_sales")
        setSort({ by: "order_qty_sales", direction: "desc" });
      if (tileId === "buy_uom_count") {
        document
          .querySelector('[data-testid="replenishment-detail-uom"]')
          ?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
      }
    },
    [patchScope],
  );

  const inspector = useMemo(() => {
    if (!view || !selectedSku) return null;
    const line = view.lines.find((item) => item.sku_id === selectedSku);
    return buildInspector(line, view.quotes_by_sku, view.quote_terms);
  }, [view, selectedSku]);

  if (!view && loading) {
    return (
      <section className="workboard rdet-dashboard">
        <ReplenishmentDetailSkeleton />
      </section>
    );
  }

  if (!view && error) {
    return (
      <section className="workboard rdet-dashboard">
        <div className="workboard-status error" role="alert">
          <p>{t("Replenishment Detail could not load.")}</p>
          <p className="rdet-error-detail">{error}</p>
          <button type="button" onClick={() => setRefreshToken((n) => n + 1)}>
            {t("Retry")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`workboard rdet-dashboard${loading ? " is-refreshing" : ""}`}
      aria-busy={loading}
      data-testid="replenishment-detail-dashboard"
    >
      <ReplenishmentDetailFilters
        scope={scope}
        options={view.filter_options}
        busy={loading}
        onPatch={patchScope}
        onSearch={(term) => patchScope({ sku: term })}
        onRefresh={() => setRefreshToken((n) => n + 1)}
        onClear={() => {
          setSelectedSku(null);
          setScope(DEFAULT_SCOPE);
          setSort(DEFAULT_SORT);
        }}
      />

      <div className="rdet-scope-row">
        <span className="rdet-source">
          {view.is_mock ? t("Workbook demonstration data") : t("Live data")}
        </span>
        <span className="rdet-note">{view.note}</span>
        <span className="rdet-note">{GRAIN_NOTE}</span>
      </div>

      {/*
        An inline strip rather than the full error branch: a refresh that fails
        should not blow away a board the reader is already using.
      */}
      {error ? (
        <p className="rdet-inline-error" role="status">
          {t("Refresh failed:")} {error}
        </p>
      ) : null}

      <ReplenishmentDetailKpiStrip kpis={view.kpis} onSelectTile={onSelectTile} />

      <p className="rdet-footnote">{PACK_ROUNDING_NOTE}</p>

      <ReplenishmentDetailGrid
        lines={view.lines}
        sort={sort}
        onSort={toggleSort}
        onSelect={(line) => setSelectedSku(line.sku_id)}
        selectedSku={selectedSku}
        scope={scope}
        asOf={view.as_of}
        currency={view.quote_terms?.currency}
      />

      <UomBreakdownPanel
        rows={view.by_uom}
        activeUom={scope.buy_uom === ALL ? null : scope.buy_uom}
        onSelectUom={(uom) =>
          patchScope({ buy_uom: scope.buy_uom === uom ? ALL : uom })
        }
      />

      <LineInspector inspector={inspector} onClose={() => setSelectedSku(null)} />
    </section>
  );
}

/**
 * Re-narrow and re-sort an already-fetched payload.
 *
 * `dashboard.lines` has already been narrowed by the two server-side filters;
 * everything else is pure work over those rows, using the same selectors the
 * tests exercise rather than a second copy of the rules.
 */
function rebuild(dashboard, scope, sort) {
  const all = dashboard.lines;
  const beforeStatus = scopeLines(all, { ...scope, reorder_status: ALL });
  const lines = scopeLines(all, scope);

  return {
    ...dashboard,
    filter_options: {
      ...dashboard.filter_options,
      ...computeFilterFacets(all),
    },
    kpis: computeKpis(lines, beforeStatus),
    lines: sortLines(lines, sort),
    by_uom: computeUomBreakdown(lines),
    exception_counts: computeExceptionCounts(beforeStatus),
  };
}
