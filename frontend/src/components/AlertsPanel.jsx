import { useEffect, useState } from "react";

import {
  approveAction,
  fetchActions,
  fetchAlertsWithActions,
  resetAndRepopulateAlerts,
  simulateAction
} from "../api/alerts.js";

export default function AlertsPanel({
  agentId,
  agentName
}) {
  const [open, setOpen] = useState(true);
  const [alerts, setAlerts] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [actionBusyId, setActionBusyId] = useState("");

  useEffect(() => {
    if (!agentId) {
      return;
    }

    let cancelled = false;

    async function loadOnOpen() {
      setOpen(true);
      setHistoryOpen(false);
      setLoading(true);
      setError("");
      setStatusNote("");

      try {
        const payload = await fetchAlertsWithActions(agentId);
        if (cancelled) {
          return;
        }
        setAlerts(payload.items || []);
      } catch (loadError) {
        if (!cancelled) {
          setAlerts([]);
          setError(
            loadError.message || "Unable to load alerts."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadOnOpen();
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  async function reloadAlerts() {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchAlertsWithActions(agentId);
      setAlerts(payload.items || []);
    } catch (loadError) {
      setError(loadError.message || "Unable to load alerts.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResetAndRepopulate() {
    if (busy) {
      return;
    }

    setBusy("repopulate");
    setError("");
    setStatusNote(
      `Resetting and recalculating ${agentName} alerts… this can take up to a minute.`
    );
    setOpen(true);

    try {
      const result = await resetAndRepopulateAlerts(agentId);
      const created = result.created_count ?? 0;
      setStatusNote(
        `Created ${created} alert${created === 1 ? "" : "s"} from ${
          result.monitoring_passes ?? 0
        } monitoring passes.`
      );
      await reloadAlerts();
    } catch (repopulateError) {
      setError(
        repopulateError.message ||
          "Reset and repopulate failed."
      );
      setStatusNote("");
    } finally {
      setBusy("");
    }
  }

  async function openHistory() {
    setHistoryOpen(true);
    setHistoryLoading(true);
    setError("");

    try {
      const payload = await fetchActions(agentId);
      setHistory(Array.isArray(payload.items) ? payload.items : []);
    } catch (historyError) {
      setHistory([]);
      setError(
        historyError.message || "Unable to load action history."
      );
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleApprove(actionId) {
    setActionBusyId(actionId);
    setError("");
    try {
      await approveAction(actionId);
      await reloadAlerts();
      if (historyOpen) {
        const payload = await fetchActions(agentId);
        setHistory(Array.isArray(payload.items) ? payload.items : []);
      }
    } catch (approveError) {
      setError(approveError.message || "Approve failed.");
    } finally {
      setActionBusyId("");
    }
  }

  async function handleSimulate(actionId) {
    setActionBusyId(actionId);
    setError("");
    try {
      await simulateAction(actionId);
      await reloadAlerts();
    } catch (simulateError) {
      setError(simulateError.message || "Simulate failed.");
    } finally {
      setActionBusyId("");
    }
  }

  const plannedCount = alerts.reduce(
    (sum, alert) =>
      sum +
      (alert.actions || []).filter(
        (action) => action.status === "planned"
      ).length,
    0
  );

  return (
    <div className="alerts-block">
      <div className="alerts-toolbar">
        <button
          type="button"
          className={"alerts-btn" + (open ? " on" : "")}
          onClick={() => setOpen((value) => !value)}
        >
          Alerts
          {alerts.length > 0 ? (
            <span className="alerts-badge">{alerts.length}</span>
          ) : null}
        </button>

        <button
          type="button"
          className="alerts-btn"
          onClick={openHistory}
        >
          History
          {plannedCount > 0 ? (
            <span className="alerts-badge muted">
              {plannedCount}
            </span>
          ) : null}
        </button>

        <button
          type="button"
          className="alerts-btn primary"
          disabled={Boolean(busy)}
          onClick={handleResetAndRepopulate}
        >
          {busy === "repopulate"
            ? "Recalculating…"
            : "Reset & repopulate"}
        </button>
      </div>

      {open ? (
        <section
          className="alerts-panel"
          data-testid="alerts-panel"
          aria-label={`${agentName} alerts`}
        >
          <div className="alerts-panel-head">
            <div>
              <strong>Alert calculation</strong>
              <p>
                Monitoring results for {agentName}. Opens
                automatically when you enter this board.
              </p>
            </div>
            <button
              type="button"
              className="alerts-close"
              aria-label="Close alerts"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </div>

          {statusNote ? (
            <p className="alerts-note">{statusNote}</p>
          ) : null}

          {error ? (
            <p className="alerts-error" role="alert">
              {error}
            </p>
          ) : null}

          {loading || busy === "repopulate" ? (
            <div className="alerts-loading">
              <span
                className="workboard-spinner"
                aria-hidden="true"
              />
              <span>
                {busy === "repopulate"
                  ? "Running monitoring agents…"
                  : "Loading alerts…"}
              </span>
            </div>
          ) : alerts.length === 0 ? (
            <p className="alerts-empty">
              No alerts yet. Use Reset &amp; repopulate to run
              monitoring agents.
            </p>
          ) : (
            <ul className="alerts-list">
              {alerts.map((alert) => (
                <li key={alert.id} className="alert-card">
                  <div className="alert-card-top">
                    <strong>{alert.name}</strong>
                    <span className="alert-subagent">
                      {alert.subagent}
                    </span>
                  </div>
                  <p className="alert-issue">{alert.issue}</p>
                  {(alert.actions || []).length === 0 ? (
                    <p className="alert-no-actions">
                      No actions attached.
                    </p>
                  ) : (
                    <ul className="alert-actions">
                      {alert.actions.map((action) => (
                        <li key={action.id}>
                          <div className="alert-action-row">
                            <div>
                              <span className="alert-action-name">
                                {action.action}
                              </span>
                              <span
                                className={
                                  "status-pill status-" +
                                  (action.status || "planned")
                                }
                              >
                                {action.status || "planned"}
                              </span>
                            </div>
                            <div className="alert-action-btns">
                              {action.status === "planned" ? (
                                <button
                                  type="button"
                                  className="alerts-mini-btn"
                                  disabled={
                                    actionBusyId === action.id
                                  }
                                  onClick={() =>
                                    handleApprove(action.id)
                                  }
                                >
                                  Approve
                                </button>
                              ) : null}
                              <button
                                type="button"
                                className="alerts-mini-btn"
                                disabled={
                                  actionBusyId === action.id ||
                                  !action.spec
                                }
                                onClick={() =>
                                  handleSimulate(action.id)
                                }
                              >
                                Simulate
                              </button>
                            </div>
                          </div>
                          {action.impact ? (
                            <p className="alert-impact">
                              {action.impact}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {historyOpen ? (
        <div
          className="alerts-modal-backdrop"
          role="presentation"
          onClick={() => setHistoryOpen(false)}
        >
          <div
            className="alerts-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="history-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="alerts-panel-head">
              <div>
                <h2 id="history-title">Action history</h2>
                <p>
                  All {agentName} actions with their current
                  status.
                </p>
              </div>
              <button
                type="button"
                className="alerts-close"
                aria-label="Close history"
                onClick={() => setHistoryOpen(false)}
              >
                ×
              </button>
            </div>

            {historyLoading ? (
              <div className="alerts-loading">
                <span
                  className="workboard-spinner"
                  aria-hidden="true"
                />
                <span>Loading history…</span>
              </div>
            ) : history.length === 0 ? (
              <p className="alerts-empty">
                No actions recorded yet.
              </p>
            ) : (
              <div className="history-table-wrap">
                <table className="history-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Action</th>
                      <th>Owners</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((action) => (
                      <tr key={action.id}>
                        <td>
                          {formatWhen(action.created_at)}
                        </td>
                        <td>{action.action}</td>
                        <td>
                          {(action.routes || []).join(", ") ||
                            "—"}
                        </td>
                        <td>
                          <span
                            className={
                              "status-pill status-" +
                              (action.status || "planned")
                            }
                          >
                            {action.status || "planned"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function formatWhen(value) {
  if (!value) {
    return "—";
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}
