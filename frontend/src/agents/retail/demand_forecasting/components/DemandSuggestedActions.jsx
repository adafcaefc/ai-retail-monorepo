import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import {
  createAgentHandoff,
  updateAgentHandoffStatus,
} from "../../../../api/agentHandoffs.js";
import {
  buildForecastBasketCsv,
  forecastBasketFilename,
} from "../data/csv.js";
import { fetchForecastBasket } from "../data/forecastBasket.js";

const PAGE_SIZE = 100;
const BASKET_SCOPE_KEYS = ["legal_entity_id", "category_group", "store_id", "sku"];

function scopeSnapshot(query = {}) {
  return Object.fromEntries(BASKET_SCOPE_KEYS.map((key) => {
    const value = query[key];
    return [key, value == null || value === "" || value === "ALL" ? null : String(value)];
  }));
}

function scopeKey(scope) {
  return JSON.stringify(scope);
}

function scopeDescription(scope, t) {
  const parts = [];
  if (scope.legal_entity_id) parts.push(scope.legal_entity_id);
  if (scope.category_group) parts.push(scope.category_group);
  if (scope.store_id) parts.push(scope.store_id);
  if (scope.sku) parts.push(`${t("SKU")} ${scope.sku}`);
  return parts.length ? parts.join(" · ") : t("All Stores");
}

function quantity(value, language, maximumFractionDigits = 1) {
  return formatNumber(value, language, { maximumFractionDigits });
}

function targetLabel(target, language, t) {
  if (!target || !Number.isFinite(Number(target.value))) return "—";
  const unit = target.unit || t("units/day");
  return `${quantity(target.value, language)} ${unit}`;
}

function unavailableEta(row, t) {
  return row.eta == null || row.eta_status === "unavailable"
    ? t("Unavailable")
    : row.eta;
}

function downloadCsv(content, filename) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const hasObjectUrl = typeof window.URL?.createObjectURL === "function";
  const url = hasObjectUrl
    ? window.URL.createObjectURL(blob)
    : `data:text/csv;charset=utf-8,${encodeURIComponent(content)}`;
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  if (hasObjectUrl) window.URL.revokeObjectURL(url);
}

function handoffFromResponse(payload) {
  return payload?.handoff || payload;
}

function statusLabel(status, t) {
  const labels = {
    approved: t("Approved"),
    rejected: t("Rejected"),
    cancelled: t("Cancelled"),
    reopened: t("Reopened"),
    sent: t("Sent"),
  };
  return labels[status] || t("Pending decision");
}

function expectedSnapshot(basket) {
  return {
    as_of: basket.as_of,
    source_import_batch_id: basket.source_import_batch_id,
    row_count: basket.row_count,
    basket_forecast_7d: basket.basket_forecast_7d,
    dashboard_forecast_7d: basket.dashboard_forecast_7d,
  };
}

export default function DemandSuggestedActions({ query = {} }) {
  const { language, t } = useLanguage();
  const currentScope = useMemo(() => scopeSnapshot(query), [
    query.legal_entity_id,
    query.category_group,
    query.store_id,
    query.sku,
  ]);
  const currentScopeKey = scopeKey(currentScope);
  const [basket, setBasket] = useState(null);
  const [generatedScopeKey, setGeneratedScopeKey] = useState("");
  const [basketLoading, setBasketLoading] = useState(false);
  const [basketError, setBasketError] = useState("");
  const [basketOpen, setBasketOpen] = useState(false);
  const [tableMode, setTableMode] = useState("actionable");
  const [page, setPage] = useState(1);
  const [handoff, setHandoff] = useState(null);
  const [riskHandoff, setRiskHandoff] = useState(null);
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [riskBusy, setRiskBusy] = useState(false);
  const [handoffError, setHandoffError] = useState("");
  const requestId = useRef(0);

  // A generated basket is a snapshot of its four operational filters. Clear it
  // as soon as that scope changes; the dashboard's Horizon/grain controls are
  // intentionally absent because this basket is always fixed at seven days.
  useEffect(() => {
    requestId.current += 1;
    setBasket(null);
    setGeneratedScopeKey("");
    setBasketLoading(false);
    setBasketError("");
    setBasketOpen(false);
    setTableMode("actionable");
    setPage(1);
    setHandoff(null);
    setRiskHandoff(null);
    setHandoffBusy(false);
    setRiskBusy(false);
    setHandoffError("");
  }, [currentScopeKey]);

  const generateBasket = useCallback(async () => {
    const thisRequest = ++requestId.current;
    setBasketLoading(true);
    setBasketError("");
    // A new generation is a new decision snapshot. If an older handoff exists
    // for this scope it remains immutable in the server history, but it must
    // not remain attached to the newly generated basket in this view.
    setBasket(null);
    setGeneratedScopeKey("");
    setBasketOpen(false);
    setHandoff(null);
    setRiskHandoff(null);
    setHandoffError("");
    try {
      const result = await fetchForecastBasket(currentScope);
      if (thisRequest !== requestId.current) return;
      if (result.reconciles !== true) {
        throw new Error(
          "Forecast basket is not ready because its Forecast 7d does not reconcile to the dashboard KPI.",
        );
      }
      setBasket(result);
      setGeneratedScopeKey(currentScopeKey);
      setBasketOpen(true);
      setTableMode("actionable");
      setPage(1);
    } catch (error) {
      if (thisRequest === requestId.current) {
        setBasket(null);
        setBasketOpen(false);
        setBasketError(error.message || t("Unable to generate the forecast basket."));
      }
    } finally {
      if (thisRequest === requestId.current) setBasketLoading(false);
    }
  }, [currentScope, t]);

  const activeBasket = basket && generatedScopeKey === currentScopeKey ? basket : null;

  const persistDecision = useCallback(async (nextStatus) => {
    if (!activeBasket || handoffBusy) return;
    const version = requestId.current;
    setHandoffBusy(true);
    setHandoffError("");
    try {
      const result = handoff
        ? await updateAgentHandoffStatus(handoff.handoff_id, nextStatus)
        : await createAgentHandoff({
          source_agent: "retail.demand_forecasting",
          target_agent: "retail.replenishment",
          handoff_type: "forecast_basket",
          status: nextStatus,
          scope: activeBasket.scope,
          expected: expectedSnapshot(activeBasket),
        });
      if (version !== requestId.current) return;
      setHandoff(handoffFromResponse(result));
    } catch (error) {
      if (version === requestId.current) {
        setHandoffError(error.message || t("Unable to persist the handoff decision."));
      }
    } finally {
      if (version === requestId.current) setHandoffBusy(false);
    }
  }, [activeBasket, handoff, handoffBusy, t]);

  const flagInventoryRisk = useCallback(async () => {
    if (!activeBasket || riskHandoff || riskBusy) return;
    const version = requestId.current;
    setRiskBusy(true);
    setHandoffError("");
    try {
      const result = await createAgentHandoff({
        source_agent: "retail.demand_forecasting",
        target_agent: "retail.inventory_risk",
        handoff_type: "risk_flag",
        status: "sent",
        scope: activeBasket.scope,
        expected: expectedSnapshot(activeBasket),
      });
      if (version !== requestId.current) return;
      setRiskHandoff(handoffFromResponse(result));
    } catch (error) {
      if (version === requestId.current) {
        setHandoffError(error.message || t("Unable to flag Agent 2."));
      }
    } finally {
      if (version === requestId.current) setRiskBusy(false);
    }
  }, [activeBasket, riskBusy, riskHandoff, t]);

  const visibleRows = useMemo(() => {
    if (!activeBasket) return [];
    return tableMode === "actionable"
      ? activeBasket.rows.filter((row) => row.suggestion > 0)
      : activeBasket.rows;
  }, [activeBasket, tableMode]);
  const pageCount = Math.max(1, Math.ceil(visibleRows.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageRows = visibleRows.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );
  const selectedStore = Boolean(activeBasket?.scope?.store_id);
  const exportLabel = tableMode === "actionable" ? t("Actionable only") : t("All rows");
  const generatedScope = activeBasket?.scope || currentScope;
  const workflowStatus = activeBasket
    ? statusLabel(handoff?.status, t)
    : t("Not generated");
  const decisionStatus = handoff?.status;
  const canDecide = Boolean(activeBasket)
    && !basketLoading
    && !handoffBusy
    && (!handoff || decisionStatus === "reopened");
  const canReopen = Boolean(activeBasket)
    && !basketLoading
    && !handoffBusy
    && (decisionStatus === "rejected" || decisionStatus === "cancelled");
  const canSend = Boolean(activeBasket)
    && !basketLoading
    && !handoffBusy
    && decisionStatus === "approved";

  const exportBasket = useCallback(() => {
    if (!activeBasket) return;
    downloadCsv(
      buildForecastBasketCsv(visibleRows),
      forecastBasketFilename(generatedScope, activeBasket.as_of, tableMode),
    );
  }, [activeBasket, generatedScope, tableMode, visibleRows]);

  return (
    <section className="demand-panel demand-suggested-actions" aria-labelledby="demand-actions-title">
      <header className="demand-panel-head">
        <div>
          <p>{t("Operational recommendation")}</p>
          <h2 id="demand-actions-title">{t("Suggested Best Action")}</h2>
          <span>{t("Generate a fixed 7-day basket for the current Demand Forecasting scope")}</span>
        </div>
        <span className="demand-pending-badge">
          {workflowStatus}
        </span>
      </header>

      <div className="demand-action-grid">
        <article className="demand-action-card demand-action-card--primary">
          <span>{t("Primary")}</span>
          <h3>{t("Send 7-day forecast basket to Replenishment")}</h3>
          <p>{t("Generate the live SKU × Store basket first, then decide whether to deliver its frozen snapshot to Replenishment.")}</p>
          <button
            type="button"
            className="demand-button"
            onClick={generateBasket}
            disabled={basketLoading}
            aria-busy={basketLoading}
          >
            {basketLoading ? t("Generating forecast basket…") : t("Generate forecast basket")}
          </button>
        </article>

        <article className="demand-action-card">
          <span>{t("Agent handoff")}</span>
          <h3>{t("Flag to Agent 2 · Inventory Risk")}</h3>
          <p>{riskHandoff ? t("Delivered to the Inventory Risk inbox for review.") : t("Send the same immutable basket snapshot to Inventory Risk for review.")}</p>
          <button
            type="button"
            className="demand-button demand-button--quiet"
            onClick={flagInventoryRisk}
            disabled={!activeBasket || basketLoading || Boolean(riskHandoff) || riskBusy}
            aria-busy={riskBusy}
            title={!activeBasket ? t("Generate the forecast basket first") : undefined}
          >
            {t("Flag to Agent 2 · Inventory Risk")}
          </button>
        </article>
      </div>

      <div className="demand-workflow-status" aria-label={t("Suggested action status")}>
        <div>
          <span>{t("Status")}</span>
          <strong>{workflowStatus}</strong>
          <small>
            {activeBasket
              ? t("Status is confirmed by the persisted handoff service.")
              : t("Generate a basket before making a decision.")}
          </small>
        </div>
        <div className="demand-workflow-buttons">
          <button type="button" className="demand-workflow-button" onClick={() => persistDecision("approved")} disabled={!canDecide}>
            {t("Approve")}
          </button>
          <button type="button" className="demand-workflow-button" onClick={() => persistDecision("rejected")} disabled={!canDecide}>
            {t("Reject")}
          </button>
          <button type="button" className="demand-workflow-button" onClick={() => persistDecision("cancelled")} disabled={!canDecide}>
            {t("Cancel")}
          </button>
          <button type="button" className="demand-workflow-button" onClick={() => persistDecision("reopened")} disabled={!canReopen}>
            {t("Reopen")}
          </button>
          <button type="button" className="demand-workflow-button" onClick={() => persistDecision("sent")} disabled={!canSend}>
            {t("Send to Agent 3 · Replenishment")}
          </button>
        </div>
      </div>

      {basketError ? (
        <div className="demand-inline-error demand-basket-error" role="alert">
          <span>{basketError}</span>
          <button type="button" onClick={generateBasket}>{t("Retry")}</button>
        </div>
      ) : null}

      {handoffError ? (
        <div className="demand-inline-error demand-basket-error" role="alert">
          <span>{handoffError}</span>
        </div>
      ) : null}

      {activeBasket ? (
        <div className="demand-forecast-basket">
          <div className="demand-basket-summary" aria-label={t("Forecast basket summary")}>
            <div>
              <span>{t("Forecast 7d")}</span>
              <strong>{quantity(activeBasket.basket_forecast_7d, language)}</strong>
            </div>
            <div>
              <span>{t("SKU × Store rows")}</span>
              <strong>{quantity(activeBasket.row_count, language, 0)}</strong>
            </div>
            <div>
              <span>{t("Actionable rows")}</span>
              <strong>{quantity(activeBasket.action_row_count, language, 0)}</strong>
            </div>
            <div>
              <span>{t("Suggested units")}</span>
              <strong>{quantity(activeBasket.suggestion_units, language)}</strong>
            </div>
          </div>

          <div className="demand-basket-reconciliation" role="status">
            <strong>{t("Forecast KPI reconciled")}</strong>
            <span>
              {t("Basket Forecast 7d matches Forecast Next 7 Days")}: {quantity(activeBasket.dashboard_forecast_7d, language)}
            </span>
          </div>

          <div className="demand-basket-toolbar">
            <div>
              <strong>{t("Forecast basket")}</strong>
              <span>{t("Generated for")} {scopeDescription(generatedScope, t)} · {t("full-basket totals")}</span>
            </div>
            <div className="demand-basket-controls">
              <div className="demand-segmented" aria-label={t("Basket row mode")}>
                <button
                  type="button"
                  aria-pressed={tableMode === "actionable"}
                  onClick={() => { setTableMode("actionable"); setPage(1); }}
                >
                  {t("Actionable only")}
                </button>
                <button
                  type="button"
                  aria-pressed={tableMode === "all"}
                  onClick={() => { setTableMode("all"); setPage(1); }}
                >
                  {t("All rows")}
                </button>
              </div>
              <button
                type="button"
                className="demand-button demand-button--quiet"
                aria-label={t("Export forecast basket")}
                onClick={exportBasket}
              >
                {t("Export forecast basket")} · {exportLabel}
              </button>
              <button
                type="button"
                className="demand-button demand-button--quiet"
                aria-expanded={basketOpen}
                onClick={() => setBasketOpen((open) => !open)}
              >
                {basketOpen ? t("Hide forecast basket") : t("Show forecast basket")}
              </button>
            </div>
          </div>

          {basketOpen ? (
            <>
              <div className="demand-basket-table-note">
                {t("Showing")} {quantity(pageRows.length, language, 0)} {t("of")} {quantity(visibleRows.length, language, 0)} {t("visible rows")} · {t(exportLabel)}. {t("Summary totals use all scoped rows.")}
              </div>
              <div className="demand-forecast-basket-scroll">
                <table className="demand-forecast-basket-table">
                  <thead>
                    <tr>
                      {!selectedStore ? <th scope="col">{t("Store")}</th> : null}
                      <th scope="col">{t("SKU")}</th>
                      <th scope="col">{t("Item")}</th>
                      <th scope="col">{t("Category")}</th>
                      <th scope="col" className="num">{t("Target")}</th>
                      <th scope="col" className="num">{t("Forecast 7d")}</th>
                      <th scope="col" className="num">{t("ROP")}</th>
                      <th scope="col" className="num">{t("Max")}</th>
                      <th scope="col" className="num">{t("Position")}</th>
                      <th scope="col" className="num">{t("Suggestion")}</th>
                      <th scope="col">{t("Signal")}</th>
                      <th scope="col">{t("Route")}</th>
                      <th scope="col">{t("ETA")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.map((row) => (
                      <tr
                        key={`${row.store_id}-${row.sku_id}`}
                        className={row.suggestion > 0 ? "demand-forecast-basket-row--actionable" : undefined}
                      >
                        {!selectedStore ? (
                          <td>
                            <strong>{row.store_name}</strong>
                            <small>{row.store_id}</small>
                          </td>
                        ) : null}
                        <td>
                          <strong>{row.sku_id}</strong>
                        </td>
                        <td>{row.item_name}</td>
                        <td>
                          <span>{row.category}</span>
                          <small>{row.category_id}</small>
                        </td>
                        <td className="num">{targetLabel(row.target, language, t)}</td>
                        <td className="num">{quantity(row.forecast_7d, language)}</td>
                        <td className="num">{quantity(row.rop, language)}</td>
                        <td className="num">{quantity(row.max, language)}</td>
                        <td className="num">{quantity(row.position, language)}</td>
                        <td className={`num ${row.suggestion > 0 ? "demand-basket-suggestion" : ""}`}>
                          {quantity(row.suggestion, language)}
                        </td>
                        <td>
                          <span className="demand-signal-list">
                            {row.signal.length
                              ? row.signal.map((signal) => <i key={signal}>{t(signal)}</i>)
                              : "—"}
                          </span>
                        </td>
                        <td><span className={`demand-basket-route demand-basket-route--${row.route}`}>{t(row.route)}</span></td>
                        <td>{unavailableEta(row, t)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {visibleRows.length ? (
                <div className="demand-basket-pagination" aria-label={t("Forecast basket pagination")}>
                  <button
                    type="button"
                    className="demand-button demand-button--quiet"
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    disabled={currentPage <= 1}
                  >
                    {t("Previous")}
                  </button>
                  <span>{t("Page")} {currentPage} {t("of")} {pageCount}</span>
                  <button
                    type="button"
                    className="demand-button demand-button--quiet"
                    onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                    disabled={currentPage >= pageCount}
                  >
                    {t("Next")}
                  </button>
                </div>
              ) : (
                <p className="workboard-empty">{t("No rows match the selected table mode.")}</p>
              )}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
