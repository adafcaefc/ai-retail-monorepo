import { useEffect, useMemo, useRef, useState } from "react";

import {
  approveAction,
  fetchActions,
  fetchAlertsWithActions,
  fetchMonitoringAgents,
  simulateAction
} from "../api/alerts.js";
import { useMonitoring } from "../monitoring/MonitoringProvider.jsx";
import BlockRenderer from "./BlockRenderer.jsx";

const STEPS = [
  { id: "recommendations", label: "Recommendations" },
  { id: "analysis", label: "Analysis" },
  { id: "approval", label: "Approval" }
];

// How many simulations may be in flight at once. Each one is a multi-turn
// agent run, so this trades wall time against the Azure request budget.
const SIMULATE_CONCURRENCY = 3;

async function runPool(items, limit, worker) {
  const queue = [...items];
  const workerCount = Math.min(limit, queue.length);

  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (queue.length > 0) {
        await worker(queue.shift());
      }
    })
  );
}

export default function AlertsPanel({
  agentId,
  agentName,
  header = null
}) {
  const monitoring = useMonitoring();
  const [alerts, setAlerts] = useState([]);
  const [monitors, setMonitors] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const wasRunningRef = useRef(false);

  const [subagentsOpen, setSubagentsOpen] = useState(false);
  const [actionOpen, setActionOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [step, setStep] = useState(0);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [actionBusyId, setActionBusyId] = useState("");
  const [simResults, setSimResults] = useState({});

  useEffect(() => {
    if (!agentId) {
      return;
    }

    let cancelled = false;

    async function loadAlerts() {
      setSubagentsOpen(false);
      setActionOpen(false);
      setHistoryOpen(false);
      setStep(0);
      setSelectedIds(new Set());
      setSimResults({});
      setLoading(true);
      setError("");

      try {
        const [payload, monitorsPayload] = await Promise.all([
          fetchAlertsWithActions(agentId),
          fetchMonitoringAgents(agentId)
        ]);
        if (!cancelled) {
          setAlerts(payload.items || []);
          const domain = monitorsPayload.items?.[0];
          setMonitors(domain?.monitoring_agents || []);
        }
      } catch (loadError) {
        if (!cancelled) {
          setAlerts([]);
          setMonitors([]);
          setError(loadError.message || "Unable to load alerts.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadAlerts();
    return () => {
      cancelled = true;
    };
  }, [agentId, monitoring.runId]);

  // Surface monitoring progress as a transient toast instead of a
  // dashboard-blocking banner. Only fire on the running -> settled
  // transition so switching agents does not re-announce old results.
  useEffect(() => {
    if (monitoring.isRunning) {
      wasRunningRef.current = true;
      setToast({
        kind: "running",
        text: "Running monitoring agents across all boards…"
      });
      return;
    }

    if (wasRunningRef.current) {
      wasRunningRef.current = false;
      if (monitoring.error) {
        setToast({ kind: "error", text: monitoring.error });
      } else {
        setToast({
          kind: "done",
          text: monitoring.note || "Monitoring complete."
        });
      }
    }
  }, [monitoring.isRunning, monitoring.error, monitoring.note]);

  useEffect(() => {
    if (!toast || toast.kind === "running") {
      return;
    }
    const timeout = window.setTimeout(
      () => setToast(null),
      toast.kind === "error" ? 7000 : 4000
    );
    return () => window.clearTimeout(timeout);
  }, [toast]);

  // Close the alerts popover on Escape.
  useEffect(() => {
    if (!alertsOpen) {
      return;
    }
    const onKey = (event) => {
      if (event.key === "Escape") {
        setAlertsOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [alertsOpen]);

  const flatActions = useMemo(
    () => flattenActions(alerts),
    [alerts]
  );

  const monitorStatusRows = useMemo(
    () => buildMonitorStatusRows(monitors, alerts),
    [monitors, alerts]
  );

  const plannedCount = flatActions.filter(
    (item) => item.action.status === "planned"
  ).length;

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

  async function handleRecalculate() {
    if (monitoring.isRunning) {
      return;
    }
    setNotifDismissed(false);
    setError("");
    await monitoring.recalculate();
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


  function toggleSelected(actionId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(actionId)) {
        next.delete(actionId);
      } else {
        next.add(actionId);
      }
      return next;
    });
  }

  function openActionModal() {
    setActionOpen(true);
    setStep(0);
    setError("");
  }

  function openSubagentsModal() {
    setSubagentsOpen(true);
    setError("");
  }

  const selectedItems = flatActions.filter((item) =>
    selectedIds.has(item.action.id)
  );

  async function runAnalysis() {
    if (selectedItems.length === 0 || actionBusyId) {
      return;
    }

    setActionBusyId("batch-simulate");
    setError("");

    // Each action is an independent agent run, so they overlap. The pool is
    // bounded to stay inside the Azure OpenAI request limit.
    const nextResults = {};
    const failed = [];

    await runPool(selectedItems, SIMULATE_CONCURRENCY, async (item) => {
      try {
        nextResults[item.action.id] = await simulateAction(item.action.id);
      } catch (simulateError) {
        failed.push(item.action.action || item.action.id);
        console.error("Simulation failed", item.action.id, simulateError);
      }
    });

    try {
      setSimResults((prev) => ({ ...prev, ...nextResults }));
      await reloadAlerts();
      setStep(1);
      if (failed.length > 0) {
        setError(
          `Simulation failed for ${failed.length} of ` +
            `${selectedItems.length} actions: ${failed.join(", ")}`
        );
      }
    } catch (reloadError) {
      setError(reloadError.message || "Simulation failed.");
    } finally {
      setActionBusyId("");
    }
  }

  async function approveSelected() {
    if (selectedItems.length === 0 || actionBusyId) {
      return;
    }

    setActionBusyId("batch-approve");
    setError("");

    try {
      for (const item of selectedItems) {
        if (item.action.status === "planned") {
          await approveAction(item.action.id);
        }
      }
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

  async function handleSingleSimulate(actionId) {
    setActionBusyId(actionId);
    setError("");
    try {
      const result = await simulateAction(actionId);
      setSimResults((prev) => ({ ...prev, [actionId]: result }));
      await reloadAlerts();
    } catch (simulateError) {
      setError(simulateError.message || "Simulate failed.");
    } finally {
      setActionBusyId("");
    }
  }

  async function handleSingleApprove(actionId) {
    setActionBusyId(actionId);
    setError("");
    try {
      await approveAction(actionId);
      await reloadAlerts();
    } catch (approveError) {
      setError(approveError.message || "Approve failed.");
    } finally {
      setActionBusyId("");
    }
  }

  const monitoringBusy = monitoring.isRunning;
  const displayError = error || monitoring.error;
  const displayNote = monitoring.note;
  const alertCount = alerts.length;

  return (
    <div className="workboard-top-stack">
      <header className="workboard-header">
        <div>{header}</div>
        <div className="alerts-block alerts-header-tools">
          <div className="alerts-toolbar">
            <button
              type="button"
              className="alerts-btn primary"
              onClick={openActionModal}
            >
              <span aria-hidden="true">⚡</span>
              Agent Action
              {plannedCount > 0 ? (
                <span className="alerts-badge muted">{plannedCount}</span>
              ) : null}
            </button>

            <button
              type="button"
              className="alerts-btn"
              disabled={monitoringBusy}
              onClick={handleRecalculate}
            >
              {monitoringBusy ? "Recalculating…" : "Recalculate"}
            </button>

            <button
              type="button"
              className={"alerts-btn" + (subagentsOpen ? " on" : "")}
              onClick={openSubagentsModal}
            >
              Subagents
              {monitorStatusRows.length > 0 ? (
                <span className="alerts-badge">
                  {monitorStatusRows.length}
                </span>
              ) : null}
            </button>

            <button
              type="button"
              className="alerts-btn"
              onClick={openHistory}
            >
              Audit History
            </button>

            <button
              type="button"
              className={
                "alerts-btn alerts-bell" +
                (alertsOpen ? " on" : "") +
                (monitoringBusy ? " is-busy" : "")
              }
              aria-label={`${alertCount} alert${
                alertCount === 1 ? "" : "s"
              }`}
              aria-expanded={alertsOpen}
              onClick={() => setAlertsOpen((open) => !open)}
            >
              {monitoringBusy ? (
                <span
                  className="workboard-spinner alerts-bell-spinner"
                  aria-hidden="true"
                />
              ) : (
                <BellIcon />
              )}
              {alertCount > 0 ? (
                <span className="alerts-bell-badge">{alertCount}</span>
              ) : null}
            </button>
          </div>

          {alertsOpen ? (
            <>
              <button
                type="button"
                className="alerts-popover-scrim"
                aria-label="Close alerts"
                onClick={() => setAlertsOpen(false)}
              />
              <div
                className="alerts-popover"
                role="dialog"
                aria-label={`${agentName} alerts`}
              >
                <div className="alerts-popover-head">
                  <div>
                    <strong>
                      {alertCount} alert{alertCount === 1 ? "" : "s"}
                    </strong>
                    <span>{agentName}</span>
                  </div>
                  <button
                    type="button"
                    className="alerts-popover-close"
                    aria-label="Close"
                    onClick={() => setAlertsOpen(false)}
                  >
                    ×
                  </button>
                </div>

                {loading ? (
                  <div className="alerts-popover-empty">
                    <span
                      className="workboard-spinner"
                      aria-hidden="true"
                    />
                    <span>Loading alerts…</span>
                  </div>
                ) : displayError ? (
                  <p className="alerts-popover-empty" role="alert">
                    {displayError}
                  </p>
                ) : alertCount === 0 ? (
                  <div className="alerts-popover-empty">
                    <BellIcon />
                    <span>No alerts detected. You&apos;re all clear.</span>
                  </div>
                ) : (
                  <ul className="status-alert-list alerts-popover-list">
                    {alerts.map((alert) => (
                      <StatusAlertCard key={alert.id} alert={alert} />
                    ))}
                  </ul>
                )}
              </div>
            </>
          ) : null}
        </div>
      </header>

      {toast ? (
        <div
          className={"monitoring-toast " + toast.kind}
          role="status"
          data-testid="monitoring-toast"
        >
          {toast.kind === "running" ? (
            <span
              className="workboard-spinner monitoring-toast-spinner"
              aria-hidden="true"
            />
          ) : (
            <span className="monitoring-toast-icon" aria-hidden="true">
              {toast.kind === "error" ? "!" : "✓"}
            </span>
          )}
          <span className="monitoring-toast-text">{toast.text}</span>
          {toast.kind !== "running" ? (
            <button
              type="button"
              className="monitoring-toast-close"
              aria-label="Dismiss"
              onClick={() => setToast(null)}
            >
              ×
            </button>
          ) : null}
        </div>
      ) : null}

      {subagentsOpen ? (
        <Modal
          title={`${agentName} Subagents`}
          icon="🤖"
          subtitle="Monitoring subagents and how many actions each suggested."
          onClose={() => setSubagentsOpen(false)}
          wide={false}
        >
          {displayNote ? (
            <p className="alerts-note">{displayNote}</p>
          ) : null}
          {displayError ? (
            <p className="alerts-error" role="alert">
              {displayError}
            </p>
          ) : null}
          {loading || monitoringBusy ? (
            <div className="alerts-loading">
              <span className="workboard-spinner" aria-hidden="true" />
              <span>
                {monitoringBusy
                  ? "Running monitoring agents…"
                  : "Loading subagents…"}
              </span>
            </div>
          ) : monitorStatusRows.length === 0 ? (
            <p className="alerts-empty">
              No monitoring subagents configured for this board.
            </p>
          ) : (
            <ul className="monitor-status-list">
              {monitorStatusRows.map((row) => (
                <li key={row.name} className="monitor-status-card">
                  <div className="monitor-status-main">
                    <strong>{formatMonitorName(row.name)}</strong>
                    <span className="monitor-status-order">
                      Pass {row.order}
                    </span>
                  </div>
                  <div className="monitor-status-count">
                    <strong>{row.actionCount}</strong>
                    <span>
                      action{row.actionCount === 1 ? "" : "s"}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      ) : null}

      {actionOpen ? (
        <Modal
          title={`${agentName} Agent Action`}
          icon="⚡"
          subtitle="Review recommendations, analyze potential impact, and submit the preferred actions for approval."
          onClose={() => setActionOpen(false)}
          wide
        >
          <ol className="action-stepper" aria-label="Action journey">
            {STEPS.map((item, index) => (
              <li
                key={item.id}
                className={
                  "action-step" +
                  (index === step ? " on" : "") +
                  (index < step ? " done" : "")
                }
              >
                <span className="action-step-num">{index + 1}</span>
                <span>{item.label}</span>
              </li>
            ))}
          </ol>

          {displayNote ? (
            <p className="alerts-note">{displayNote}</p>
          ) : null}
          {displayError ? (
            <p className="alerts-error" role="alert">
              {displayError}
            </p>
          ) : null}

          {loading || monitoringBusy ? (
            <div className="alerts-loading">
              <span className="workboard-spinner" aria-hidden="true" />
              <span>
                {monitoringBusy
                  ? "Running monitoring agents…"
                  : "Loading actions…"}
              </span>
            </div>
          ) : null}

          {!loading && !monitoringBusy && step === 0 ? (
            <RecommendationsStep
              alerts={alerts}
              selectedIds={selectedIds}
              onToggle={toggleSelected}
              onContinue={runAnalysis}
              continueBusy={actionBusyId === "batch-simulate"}
              selectedCount={selectedItems.length}
            />
          ) : null}

          {!loading && !monitoringBusy && step === 1 ? (
            <AnalysisStep
              items={selectedItems}
              simResults={simResults}
              actionBusyId={actionBusyId}
              onSimulate={handleSingleSimulate}
              onBack={() => setStep(0)}
              onContinue={() => setStep(2)}
            />
          ) : null}

          {!loading && !monitoringBusy && step === 2 ? (
            <ApprovalStep
              items={selectedItems}
              actionBusyId={actionBusyId}
              onApprove={handleSingleApprove}
              onApproveAll={approveSelected}
              onBack={() => setStep(1)}
              onDone={() => {
                setActionOpen(false);
                setSelectedIds(new Set());
                setStep(0);
              }}
            />
          ) : null}
        </Modal>
      ) : null}

      {historyOpen ? (
        <Modal
          title="Action history"
          subtitle={`All ${agentName} actions with their current status.`}
          onClose={() => setHistoryOpen(false)}
        >
          {historyLoading ? (
            <div className="alerts-loading">
              <span className="workboard-spinner" aria-hidden="true" />
              <span>Loading history…</span>
            </div>
          ) : history.length === 0 ? (
            <p className="alerts-empty">No actions recorded yet.</p>
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
                      <td>{formatWhen(action.created_at)}</td>
                      <td>{action.action}</td>
                      <td>
                        {(action.routes || []).join(", ") || "—"}
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
        </Modal>
      ) : null}
    </div>
  );
}

function RecommendationsStep({
  alerts,
  selectedIds,
  onToggle,
  onContinue,
  continueBusy,
  selectedCount
}) {
  const groups = alerts.filter(
    (alert) => (alert.actions || []).length > 0
  );
  const totalActions = groups.reduce(
    (sum, alert) => sum + (alert.actions || []).length,
    0
  );

  if (groups.length === 0) {
    return (
      <p className="alerts-empty">
        No recommended actions yet. Use Recalculate to run monitoring
        agents.
      </p>
    );
  }

  return (
    <div className="action-step-panel">
      <div className="action-step-head">
        <div>
          <strong>Select recommendations</strong>
          <p>
            Choose one or more recommendations for deeper analysis
            before approval.
          </p>
        </div>
        <span className="selected-chip">{selectedCount} selected</span>
      </div>

      <ul className="action-group-list">
        {groups.map((alert) => (
          <li key={alert.id} className="action-group">
            <div className="action-group-head">
              <strong>{alert.name || "Alert"}</strong>
              <span>{alert.issue}</span>
            </div>
            <ul className="rec-action-list">
              {(alert.actions || []).map((action) => {
                const checked = selectedIds.has(action.id);
                const priority = priorityFor(action);
                return (
                  <li key={action.id}>
                    <label
                      className={
                        "rec-action-card" + (checked ? " selected" : "")
                      }
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggle(action.id)}
                      />
                      <div className="rec-action-body">
                        <div className="rec-action-top">
                          <strong>{action.action}</strong>
                          <span
                            className={
                              "priority-pill " + priority.toLowerCase()
                            }
                          >
                            {priority} Priority
                          </span>
                        </div>
                        <p>
                          {action.impact ||
                            action.spec ||
                            "Review this recommendation before approval."}
                        </p>
                        <div className="rec-action-meta">
                          <span>
                            <em>Why</em> Generated from{" "}
                            {alert.subagent || "monitoring"}
                          </span>
                          <span>
                            <em>Analysis</em> Impact simulation
                          </span>
                          <span>
                            <em>Owner</em>{" "}
                            {(action.routes && action.routes[0]) ||
                              "Not assigned"}
                          </span>
                          <span>
                            <em>Approval</em>{" "}
                            {(action.routes || []).join(", ") ||
                              "Pending owner"}
                          </span>
                        </div>
                      </div>
                    </label>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>

      <div className="action-step-footer">
        <span>
          {selectedCount} of {totalActions} selected
        </span>
        <button
          type="button"
          className="alerts-btn primary"
          disabled={selectedCount === 0 || continueBusy}
          onClick={onContinue}
        >
          {continueBusy
            ? "Analyzing…"
            : "Analyze selected actions"}
        </button>
      </div>
    </div>
  );
}

function AnalysisStep({
  items,
  simResults,
  actionBusyId,
  onSimulate,
  onBack,
  onContinue
}) {
  return (
    <div className="action-step-panel">
      <div className="action-step-head">
        <div>
          <strong>Analysis</strong>
          <p>
            Review simulated impact for each selected action before
            approval.
          </p>
        </div>
      </div>

      <ul className="rec-action-list">
        {items.map(({ alert, action }) => {
          const sim = simResults[action.id];
          const simulation =
            sim?.simulation || action.simulation_summary || null;
          const summary =
            simulation?.summary ||
            action.impact ||
            "No simulation summary yet.";
          const blocks = Array.isArray(simulation?.blocks)
            ? simulation.blocks
            : [];
          return (
            <li key={action.id} className="rec-action-card static">
              <div className="rec-action-body">
                <div className="rec-action-top">
                  <strong>{action.action}</strong>
                  <span className="alert-subagent">{alert.name}</span>
                </div>
                <p>{summary}</p>
                {blocks.length > 0 ? (
                  <div className="sim-blocks">
                    {blocks.map((block, index) => (
                      <BlockRenderer
                        key={`${action.id}-block-${index}`}
                        block={block}
                      />
                    ))}
                  </div>
                ) : null}
                <div className="alert-action-btns">
                  <button
                    type="button"
                    className="alerts-mini-btn"
                    disabled={
                      actionBusyId === action.id || !action.spec
                    }
                    onClick={() => onSimulate(action.id)}
                  >
                    {actionBusyId === action.id
                      ? "Simulating…"
                      : "Re-simulate"}
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="action-step-footer">
        <button type="button" className="alerts-btn" onClick={onBack}>
          Back
        </button>
        <button
          type="button"
          className="alerts-btn primary"
          disabled={items.length === 0}
          onClick={onContinue}
        >
          Continue to approval
        </button>
      </div>
    </div>
  );
}

function ApprovalStep({
  items,
  actionBusyId,
  onApprove,
  onApproveAll,
  onBack,
  onDone
}) {
  const pending = items.filter(
    (item) => item.action.status === "planned"
  );

  return (
    <div className="action-step-panel">
      <div className="action-step-head">
        <div>
          <strong>Approval</strong>
          <p>
            Confirm owner sign-off. Nothing executes without approval.
          </p>
        </div>
      </div>

      <ul className="rec-action-list">
        {items.map(({ alert, action }) => (
          <li key={action.id} className="rec-action-card static">
            <div className="rec-action-body">
              <div className="rec-action-top">
                <strong>{action.action}</strong>
                <span
                  className={
                    "status-pill status-" + (action.status || "planned")
                  }
                >
                  {action.status || "planned"}
                </span>
              </div>
              <p>
                {action.impact ||
                  `Route to ${(action.routes || []).join(", ") || "owner"}.`}
              </p>
              {action.status === "planned" ? (
                <div className="alert-action-btns">
                  <button
                    type="button"
                    className="alerts-mini-btn"
                    disabled={
                      actionBusyId === action.id ||
                      actionBusyId === "batch-approve"
                    }
                    onClick={() => onApprove(action.id)}
                  >
                    {actionBusyId === action.id
                      ? "Approving…"
                      : "Approve"}
                  </button>
                </div>
              ) : null}
              <div className="rec-action-meta">
                <span>
                  <em>Alert</em> {alert.name}
                </span>
                <span>
                  <em>Owners</em>{" "}
                  {(action.routes || []).join(", ") || "—"}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>

      <div className="action-step-footer">
        <button type="button" className="alerts-btn" onClick={onBack}>
          Back
        </button>
        <div className="action-step-footer-actions">
          {pending.length > 0 ? (
            <button
              type="button"
              className="alerts-btn primary"
              disabled={actionBusyId === "batch-approve"}
              onClick={onApproveAll}
            >
              {actionBusyId === "batch-approve"
                ? "Approving…"
                : `Approve all (${pending.length})`}
            </button>
          ) : (
            <button
              type="button"
              className="alerts-btn primary"
              onClick={onDone}
            >
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function BellIcon() {
  return (
    <svg
      className="alerts-bell-icon"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M12 3a5 5 0 00-5 5v3l-2 3h14l-2-3V8a5 5 0 00-5-5zm0 18a2.5 2.5 0 002.4-2h-4.8A2.5 2.5 0 0012 21z"
      />
    </svg>
  );
}

function StatusAlertCard({ alert }) {
  const [open, setOpen] = useState(false);
  const actions = alert.actions || [];
  const actionCount = actions.length;

  return (
    <li className="status-alert-card">
      <div className="status-alert-icon" aria-hidden="true">
        !
      </div>
      <div className="status-alert-body">
        <div className="status-alert-top">
          <strong>{alert.name || "Alert"}</strong>
          <span className="priority-pill high">High</span>
        </div>
        <p>{alert.issue}</p>
        <div className="status-alert-meta">
          <span>{formatWhen(alert.date_created)}</span>
          <span className="alert-subagent">{alert.subagent}</span>
        </div>

        <button
          type="button"
          className={"status-actions-toggle" + (open ? " on" : "")}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <span>
            {actionCount} action{actionCount === 1 ? "" : "s"}
          </span>
          <span aria-hidden="true">{open ? "▴" : "▾"}</span>
        </button>

        {open ? (
          actionCount === 0 ? (
            <p className="status-actions-empty">No actions suggested.</p>
          ) : (
            <ul className="status-actions-dropdown">
              {actions.map((action) => (
                <li key={action.id}>{action.action}</li>
              ))}
            </ul>
          )
        ) : null}
      </div>
    </li>
  );
}

function Modal({
  title,
  subtitle,
  icon,
  onClose,
  children,
  wide = false
}) {
  return (
    <div
      className="alerts-modal-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        className={
          "alerts-modal" + (wide ? " alerts-modal-wide" : "")
        }
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="alerts-panel-head">
          <div>
            <h2>
              {icon ? (
                <span className="modal-title-icon" aria-hidden="true">
                  {icon}
                </span>
              ) : null}
              {title}
            </h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button
            type="button"
            className="alerts-close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function flattenActions(alerts) {
  const items = [];
  for (const alert of alerts || []) {
    for (const action of alert.actions || []) {
      items.push({ alert, action });
    }
  }
  return items;
}

function buildMonitorStatusRows(monitors, alerts) {
  const actionCounts = {};
  for (const alert of alerts || []) {
    const key = String(alert.subagent || "").trim();
    if (!key) {
      continue;
    }
    actionCounts[key] =
      (actionCounts[key] || 0) + (alert.actions || []).length;
  }

  if ((monitors || []).length > 0) {
    return monitors.map((monitor) => ({
      name: monitor.name,
      order: monitor.order,
      actionCount: actionCounts[monitor.name] || 0
    }));
  }

  return Object.keys(actionCounts)
    .sort()
    .map((name, index) => ({
      name,
      order: index + 1,
      actionCount: actionCounts[name]
    }));
}

function formatMonitorName(name) {
  return String(name || "")
    .replace(/_monitoring_agent$/i, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function priorityFor(action) {
  const text = `${action.impact || ""} ${action.spec || ""}`.toLowerCase();
  if (
    text.includes("critical") ||
    text.includes("urgent") ||
    text.includes("fraud") ||
    text.includes("margin")
  ) {
    return "High";
  }
  if (text.includes("watch") || text.includes("monitor")) {
    return "Low";
  }
  return "Medium";
}

function formatWhen(value) {
  if (!value) {
    return "—";
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit"
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}
