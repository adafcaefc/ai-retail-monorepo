import { useEffect, useState } from "react";

import { formatNumber } from "../format.js";
import { useLanguage } from "../LanguageProvider.jsx";
import { fetchAgentHandoff, fetchAgentInbox } from "../api/agentHandoffs.js";

function quantity(value, language) {
  return formatNumber(value, language, { maximumFractionDigits: 1 });
}

function scopeLabel(scope, t) {
  const values = [
    scope?.legal_entity_id,
    scope?.category_group,
    scope?.store_id,
    scope?.sku ? `${t("SKU")} ${scope.sku}` : null,
  ].filter(Boolean);
  return values.length ? values.join(" · ") : t("All Stores");
}

function handoffTypeLabel(type, t) {
  return type === "risk_flag" ? t("Risk flag") : t("Forecast Basket");
}

function shortHash(hash) {
  return hash ? `${String(hash).slice(0, 12)}…` : "—";
}

function detailRows(payload) {
  return Array.isArray(payload?.rows) ? payload.rows.slice(0, 25) : [];
}

export default function AgentHandoffInbox({
  agentId,
  title,
  emptyText,
  enabled = true,
}) {
  const { language, t } = useLanguage();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState("");
  const [details, setDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState("");

  useEffect(() => {
    if (!enabled || typeof fetch !== "function") return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");

    fetchAgentInbox(agentId)
      .then((payload) => {
        if (!cancelled) setItems(Array.isArray(payload?.items) ? payload.items : []);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError.message || t("Unable to load agent inbox."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [agentId, enabled, t]);

  async function toggleDetails(handoffId) {
    if (openId === handoffId) {
      setOpenId("");
      return;
    }
    setOpenId(handoffId);
    if (details[handoffId]) return;
    setDetailLoading(handoffId);
    try {
      const result = await fetchAgentHandoff(handoffId);
      setDetails((current) => ({
        ...current,
        [handoffId]: result?.handoff || result,
      }));
    } catch (detailError) {
      setError(detailError.message || t("Unable to load the frozen handoff."));
    } finally {
      setDetailLoading("");
    }
  }

  if (!enabled) return null;

  return (
    <section className="agent-handoff-inbox" aria-labelledby={`${agentId}-inbox-title`}>
      <div className="agent-handoff-inbox-head">
        <div>
          <p>{t("Received handoffs")}</p>
          <h2 id={`${agentId}-inbox-title`}>{title || t("Agent inbox")}</h2>
        </div>
        {loading ? <span className="agent-handoff-inbox-status">{t("Loading…")}</span> : null}
      </div>

      {error ? <p className="agent-handoff-inbox-error" role="alert">{error}</p> : null}
      {!loading && !error && !items.length ? (
        <p className="agent-handoff-inbox-empty">{emptyText || t("No delivered handoffs.")}</p>
      ) : null}

      <div className="agent-handoff-inbox-list">
        {items.map((item) => {
          const detail = details[item.handoff_id];
          const rows = detailRows(detail?.payload);
          return (
            <article className="agent-handoff-card" key={item.handoff_id}>
              <div className="agent-handoff-card-head">
                <div>
                  <span>{handoffTypeLabel(item.handoff_type, t)}</span>
                  <h3>{t("Demand Forecasting")}</h3>
                </div>
                <strong>{t("Sent")}</strong>
              </div>
              <dl className="agent-handoff-card-metrics">
                <div><dt>{t("Scope")}</dt><dd>{scopeLabel(item.scope, t)}</dd></div>
                <div><dt>{t("Forecast 7d")}</dt><dd>{quantity(item.basket_forecast_7d, language)}</dd></div>
                <div><dt>{t("Actionable rows")}</dt><dd>{quantity(item.action_row_count, language)}</dd></div>
                <div><dt>{t("Suggested units")}</dt><dd>{quantity(item.suggestion_units, language)}</dd></div>
              </dl>
              <p className="agent-handoff-card-meta">
                {item.created_at || item.updated_at || item.as_of || "—"} · {t("ID")} {String(item.handoff_id).slice(0, 12)} · {t("Hash")} {shortHash(item.basket_hash)}
              </p>
              <button
                type="button"
                className="agent-handoff-detail-button"
                onClick={() => toggleDetails(item.handoff_id)}
                aria-expanded={openId === item.handoff_id}
              >
                {openId === item.handoff_id ? t("Hide frozen basket") : t("Inspect frozen basket")}
              </button>

              {openId === item.handoff_id ? (
                <div className="agent-handoff-detail">
                  {detailLoading === item.handoff_id ? <p>{t("Loading frozen snapshot…")}</p> : null}
                  {detail ? (
                    <>
                      <p>
                        {t("Snapshot")} {detail.source_snapshot_date || detail.as_of || "—"} · {t("Grain")} {detail.payload?.grain || detail.grain || "sku_store"} · {t("Rows")} {quantity(detail.payload?.row_count, language)}
                      </p>
                      {rows.length ? (
                        <div className="agent-handoff-detail-scroll">
                          <table>
                            <thead>
                              <tr><th>{t("Store")}</th><th>{t("SKU")}</th><th>{t("Suggestion")}</th><th>{t("Forecast 7d")}</th></tr>
                            </thead>
                            <tbody>
                              {rows.map((row) => (
                                <tr key={`${row.store_id}-${row.sku_id}`}>
                                  <td>{row.store_id}</td>
                                  <td>{row.sku_id}</td>
                                  <td>{quantity(row.suggestion, language)}</td>
                                  <td>{quantity(row.forecast_7d, language)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {detail.payload?.rows?.length > rows.length ? (
                            <small>{t("Showing the first 25 frozen rows; the persisted snapshot contains all rows.")}</small>
                          ) : null}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
