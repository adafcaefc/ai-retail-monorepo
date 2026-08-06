import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  approveAction,
  fetchActions,
  fetchAlertsWithActions,
  fetchMonitoringAgents,
  simulateAction,
} from "../api/alerts.js";
import { useMonitoring } from "../monitoring/MonitoringProvider.jsx";
import BlockRenderer from "./BlockRenderer.jsx";
import { ListSkeleton, SkeletonLines } from "./Skeleton.jsx";

const STEPS = [
  { id: "recommendations", label: "Recommendations" },
  { id: "analysis", label: "Analysis" },
  { id: "approval", label: "Approval" },
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
    }),
  );
}

export default function AlertsPanel({
  agentId,
  agentName,
  backendEnabled = true,
  isChatOpen = false,
  onToggleChat,
}) {
  const monitoring = useMonitoring();
  const [alerts, setAlerts] = useState([]);
  // actionId -> { rank, score, confidence, confidence_basis, reason, impact }
  const [ranking, setRanking] = useState(() => new Map());
  const [monitors, setMonitors] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const wasRunningRef = useRef(false);
  const bellRef = useRef(null);
  const moreRef = useRef(null);

  const [subagentsOpen, setSubagentsOpen] = useState(false);
  const [actionOpen, setActionOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [step, setStep] = useState(0);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [actionBusyId, setActionBusyId] = useState("");
  const [simResults, setSimResults] = useState({});
  // Action ids whose simulation is still in flight. The Analysis step opens
  // straight away and each card resolves on its own, so this drives the
  // per-card placeholder rather than a modal-wide blocking spinner.
  const [simPending, setSimPending] = useState(() => new Set());

  useEffect(() => {
    if (!agentId) {
      return;
    }

    if (!backendEnabled) {
      setAlerts([]);
      setMonitors([]);
      setHistory([]);
      setLoading(false);
      setError("");
      setAlertsOpen(false);
      setSubagentsOpen(false);
      setActionOpen(false);
      setHistoryOpen(false);
      setStep(0);
      setSelectedIds(new Set());
      setSimResults({});
      setSimPending(new Set());
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
      setSimPending(new Set());
      setLoading(true);
      setError("");

      try {
        // The agent-wide action list is the only place the ranking is
        // meaningful. Per-alert fetches score each alert's one or two
        // actions against each other, so everything comes back rank 1 —
        // the backend normalises magnitudes within whatever list it is
        // handed (see impact/scoring.rank).
        const [payload, monitorsPayload, rankedPayload] = await Promise.all([
          fetchAlertsWithActions(agentId),
          fetchMonitoringAgents(agentId),
          fetchActions(agentId).catch(() => ({ items: [] })),
        ]);
        if (!cancelled) {
          setAlerts(payload.items || []);
          setRanking(indexByActionId(rankedPayload.items || []));
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
  }, [agentId, backendEnabled, monitoring.runId]);

  // Surface monitoring progress as a transient toast instead of a
  // dashboard-blocking banner. Only fire on the running -> settled
  // transition so switching agents does not re-announce old results.
  useEffect(() => {
    if (!backendEnabled) {
      wasRunningRef.current = false;
      setToast(null);
      return;
    }

    if (monitoring.isRunning) {
      wasRunningRef.current = true;
      setToast({
        kind: "running",
        text: "Running monitoring agents across all boards…",
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
          text: monitoring.note || "Monitoring complete.",
        });
      }
    }
  }, [backendEnabled, monitoring.isRunning, monitoring.error, monitoring.note]);

  useEffect(() => {
    if (!toast || toast.kind === "running") {
      return;
    }
    const timeout = window.setTimeout(
      () => setToast(null),
      toast.kind === "error" ? 7000 : 4000,
    );
    return () => window.clearTimeout(timeout);
  }, [toast]);

  // Close whichever header layer is open on Escape.
  useEffect(() => {
    if (!alertsOpen && !moreOpen) {
      return;
    }
    const onKey = (event) => {
      if (event.key === "Escape") {
        setAlertsOpen(false);
        setMoreOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [alertsOpen, moreOpen]);

  const alertsPos = useAnchoredPosition(alertsOpen, bellRef);
  const morePos = useAnchoredPosition(moreOpen, moreRef);

  const flatActions = useMemo(() => flattenActions(alerts), [alerts]);

  const monitorStatusRows = useMemo(
    () => buildMonitorStatusRows(monitors, alerts),
    [monitors, alerts],
  );

  const plannedCount = flatActions.filter(
    (item) => item.action.status === "planned",
  ).length;

  /**
   * `silent` refreshes the alert data without raising the modal-wide
   * skeleton. Any reload triggered from inside the action journey uses it:
   * the step already shows its own per-card progress, and swapping the whole
   * panel for a skeleton is exactly the stall we are trying to avoid.
   */
  async function reloadAlerts({ silent = false } = {}) {
    if (!backendEnabled) {
      return;
    }

    if (!silent) {
      setLoading(true);
    }
    setError("");
    try {
      const payload = await fetchAlertsWithActions(agentId);
      setAlerts(payload.items || []);
    } catch (loadError) {
      setError(loadError.message || "Unable to load alerts.");
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }

  async function handleRecalculate() {
    if (!backendEnabled || monitoring.isRunning) {
      return;
    }

    setError("");
    await monitoring.recalculate();
  }

  async function openHistory() {
    if (!backendEnabled) {
      return;
    }

    setMoreOpen(false);
    setHistoryOpen(true);
    setHistoryLoading(true);
    setError("");

    try {
      const payload = await fetchActions(agentId);
      setHistory(Array.isArray(payload.items) ? payload.items : []);
    } catch (historyError) {
      setHistory([]);
      setError(historyError.message || "Unable to load action history.");
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

  // Without this the only way to analyse everything is to scroll the whole
  // list and tick each card, which is the scrolling we are trying to remove.
  function toggleSelectAll() {
    setSelectedIds((prev) =>
      prev.size === flatActions.length
        ? new Set()
        : new Set(flatActions.map((item) => item.action.id)),
    );
  }

  function openActionModal() {
    if (!backendEnabled) {
      return;
    }

    setActionOpen(true);
    setStep(0);
    setError("");
  }

  function openSubagentsModal() {
    if (!backendEnabled) {
      return;
    }

    setMoreOpen(false);
    setSubagentsOpen(true);
    setError("");
  }

  const selectedItems = flatActions.filter((item) =>
    selectedIds.has(item.action.id),
  );

  async function runAnalysis() {
    if (!backendEnabled || selectedItems.length === 0 || actionBusyId) {
      return;
    }

    const items = selectedItems;
    setActionBusyId("batch-simulate");
    setError("");

    // Move to Analysis before any request goes out. Simulations are
    // multi-turn agent runs, so waiting for them all before switching left
    // the user staring at the recommendation list; instead the cards are
    // laid out immediately and each one fills in when its own run lands.
    setSimPending(new Set(items.map((item) => item.action.id)));
    setStep(1);

    // Each action is an independent agent run, so they overlap. The pool is
    // bounded to stay inside the Azure OpenAI request limit.
    const failed = [];

    await runPool(items, SIMULATE_CONCURRENCY, async (item) => {
      const actionId = item.action.id;
      try {
        const result = await simulateAction(actionId);
        setSimResults((prev) => ({ ...prev, [actionId]: result }));
      } catch (simulateError) {
        failed.push(item.action.action || actionId);
        console.error("Simulation failed", actionId, simulateError);
      } finally {
        setSimPending((prev) => {
          const next = new Set(prev);
          next.delete(actionId);
          return next;
        });
      }
    });

    try {
      await reloadAlerts({ silent: true });
      if (failed.length > 0) {
        setError(
          `Simulation failed for ${failed.length} of ` +
            `${items.length} actions: ${failed.join(", ")}`,
        );
      }
    } catch (reloadError) {
      setError(reloadError.message || "Simulation failed.");
    } finally {
      setActionBusyId("");
    }
  }

  async function approveSelected() {
    if (!backendEnabled || selectedItems.length === 0 || actionBusyId) {
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
      await reloadAlerts({ silent: true });
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
    if (!backendEnabled) {
      return;
    }

    setActionBusyId(actionId);
    setError("");
    setSimPending((prev) => new Set(prev).add(actionId));
    try {
      const result = await simulateAction(actionId);
      setSimResults((prev) => ({ ...prev, [actionId]: result }));
      await reloadAlerts({ silent: true });
    } catch (simulateError) {
      setError(simulateError.message || "Simulate failed.");
    } finally {
      setSimPending((prev) => {
        const next = new Set(prev);
        next.delete(actionId);
        return next;
      });
      setActionBusyId("");
    }
  }

  async function handleSingleApprove(actionId) {
    if (!backendEnabled) {
      return;
    }

    setActionBusyId(actionId);
    setError("");
    try {
      await approveAction(actionId);
      await reloadAlerts({ silent: true });
    } catch (approveError) {
      setError(approveError.message || "Approve failed.");
    } finally {
      setActionBusyId("");
    }
  }

  const monitoringBusy = backendEnabled && monitoring.isRunning;
  const displayError = backendEnabled ? error || monitoring.error : "";
  const displayNote = backendEnabled ? monitoring.note : "";
  const alertCount = alerts.length;

  return (
    <>
      <div className="alerts-block alerts-header-tools">
          <div className="alerts-toolbar">
            <button
              type="button"
              className="alerts-btn primary"
              title={
                plannedCount > 0
                  ? `${plannedCount} issue${plannedCount === 1 ? "" : "s"} found`
                  : "Review recommended actions"
              }
              disabled={!backendEnabled}
              onClick={openActionModal}
            >
              Agent Action
              {plannedCount > 0 ? (
                <span className="alerts-badge muted">{plannedCount}</span>
              ) : null}
            </button>

            {/* Icon-only from here on: Recalculate, alerts and the overflow
                menu are supporting controls, so they no longer compete with
                the primary action for width or attention. */}
            <button
              type="button"
              className={
                "alerts-btn alerts-icon-btn" + (monitoringBusy ? " is-busy" : "")
              }
              disabled={!backendEnabled || monitoringBusy}
              aria-label={
                monitoringBusy ? "Recalculating…" : "Recalculate this board"
              }
              title={monitoringBusy ? "Recalculating…" : "Recalculate"}
              onClick={handleRecalculate}
            >
              <RecalculateIcon />
            </button>

            {/* The bell keeps its icon while monitoring runs — the spinning
                Recalculate button already carries that state, and two
                spinners for one operation is the noise we are removing. */}
            {/* A dot, not a count. The bell and Agent Action tally different
                things, but two bare numbers side by side read as the same
                number repeated — so the actionable count stays on the
                actionable button and the bell just says "there is something
                here". The exact figure is one click away, and `aria-label`
                still announces it. */}
            <button
              type="button"
              ref={bellRef}
              className={
                "alerts-btn alerts-icon-btn alerts-bell" +
                (alertsOpen ? " on" : "")
              }
              aria-label={
                backendEnabled
                  ? `${alertCount} alert${alertCount === 1 ? "" : "s"}`
                  : `${agentName} notifications unavailable`
              }
              aria-expanded={alertsOpen}
              title="Alerts"
              disabled={!backendEnabled}
              onClick={() => setAlertsOpen((open) => !open)}
            >
              <BellIcon />

              {alertCount > 0 ? (
                <span className="alerts-bell-dot" aria-hidden="true" />
              ) : null}
            </button>

            {/* Everything behind this menu — Subagents, Audit History — talks
                to the backend, so a dashboard-only board has nothing to open
                here. Disabling the trigger says that once, rather than opening
                a menu of dead rows. */}
            <button
              type="button"
              ref={moreRef}
              className={
                "alerts-btn alerts-icon-btn" + (moreOpen ? " on" : "")
              }
              aria-label="More board tools"
              aria-expanded={moreOpen}
              aria-haspopup="menu"
              title="More"
              disabled={!backendEnabled}
              onClick={() => setMoreOpen((open) => !open)}
            >
              <MoreIcon />
            </button>

            <span className="alerts-toolbar-sep" aria-hidden="true" />

            <button
              type="button"
              className={
                "alerts-btn chat-toggle-btn" + (isChatOpen ? " on" : "")
              }
              aria-expanded={isChatOpen}
              aria-controls="agent-chat-panel"
              aria-label={
                isChatOpen ? `Close ${agentName} chat` : `Ask ${agentName}`
              }
              title={
                isChatOpen
                  ? `Close ${agentName} chat`
                  : `Open ${agentName} chat`
              }
              onClick={() => onToggleChat?.()}
            >
              <ChatSparkleIcon />

              <span className="chat-toggle-label">Ask {agentName}</span>
            </button>
          </div>

          {moreOpen ? (
            <>
              <button
                type="button"
                className="alerts-popover-scrim"
                aria-label="Close menu"
                onClick={() => setMoreOpen(false)}
              />
              <div
                className="alerts-more-menu"
                role="menu"
                aria-label="More board tools"
                style={anchoredStyle(morePos)}
              >
                <button
                  type="button"
                  role="menuitem"
                  className="alerts-more-item"
                  onClick={openSubagentsModal}
                >
                  <span>Subagents</span>
                  {monitorStatusRows.length > 0 ? (
                    <span className="alerts-badge">
                      {monitorStatusRows.length}
                    </span>
                  ) : null}
                </button>

                <button
                  type="button"
                  role="menuitem"
                  className="alerts-more-item"
                  onClick={openHistory}
                >
                  <span>Audit History</span>
                </button>
              </div>
            </>
          ) : null}

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
                style={anchoredStyle(alertsPos)}
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
                  <ListSkeleton rows={3} label="Loading alerts" />
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
          {displayNote ? <p className="alerts-note">{displayNote}</p> : null}
          {displayError ? (
            <p className="alerts-error" role="alert">
              {displayError}
            </p>
          ) : null}
          {loading || monitoringBusy ? (
            <ListSkeleton
              rows={3}
              label={
                monitoringBusy
                  ? "Running monitoring agents"
                  : "Loading subagents"
              }
            />
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
                    <span>action{row.actionCount === 1 ? "" : "s"}</span>
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
          subtitle="Review recommendations, analyze potential impact, and submit the preferred actions for approval."
          onClose={() => setActionOpen(false)}
          wide
          scrollResetKey={step}
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

          {displayNote ? <p className="alerts-note">{displayNote}</p> : null}
          {displayError ? (
            <p className="alerts-error" role="alert">
              {displayError}
            </p>
          ) : null}

          {loading || monitoringBusy ? (
            <ListSkeleton
              rows={3}
              label={
                monitoringBusy ? "Running monitoring agents" : "Loading actions"
              }
            />
          ) : null}

          {!loading && !monitoringBusy && step === 0 ? (
            <RecommendationsStep
              alerts={alerts}
              ranking={ranking}
              selectedIds={selectedIds}
              onToggle={toggleSelected}
              onToggleAll={toggleSelectAll}
              onContinue={runAnalysis}
              continueBusy={actionBusyId === "batch-simulate"}
              selectedCount={selectedItems.length}
            />
          ) : null}

          {!loading && !monitoringBusy && step === 1 ? (
            <AnalysisStep
              items={selectedItems}
              simResults={simResults}
              simPending={simPending}
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
            <ListSkeleton rows={4} label="Loading history" />
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
                      <td>{(action.routes || []).join(", ") || "—"}</td>
                      <td>
                        <span
                          className={
                            "status-pill status-" + (action.status || "planned")
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
    </>
  );
}

function RecommendationsStep({
  alerts,
  ranking,
  selectedIds,
  onToggle,
  onToggleAll,
  onContinue,
  continueBusy,
  selectedCount,
}) {
  // Order by the backend's rank, not by the order the last monitoring run
  // happened to write the rows in (QC-061). Alerts are kept as the grouping
  // because an action without the issue behind it is not reviewable — the
  // group simply leads with whichever of its actions ranks best, so the next
  // best action in the agent is the first thing on screen.
  const rankOf = (action) => rankingFor(ranking, action).rank ?? Infinity;
  const groups = alerts
    .filter((alert) => (alert.actions || []).length > 0)
    .map((alert) => ({
      ...alert,
      actions: [...(alert.actions || [])].sort(
        (a, b) => rankOf(a) - rankOf(b),
      ),
    }))
    .sort((a, b) => rankOf(a.actions[0]) - rankOf(b.actions[0]));
  const totalActions = groups.reduce(
    (sum, alert) => sum + (alert.actions || []).length,
    0,
  );
  // "One or two next best actions" is QC-061's own wording.
  const nextBestIds = new Set(
    groups
      .flatMap((alert) => alert.actions)
      .filter((action) => Number.isFinite(rankOf(action)))
      .slice(0, 2)
      .map((action) => action.id),
  );
  const allSelected = totalActions > 0 && selectedCount === totalActions;

  if (groups.length === 0) {
    return (
      <p className="alerts-empty">
        No recommended actions yet. Use Recalculate to run monitoring agents.
      </p>
    );
  }

  return (
    <div className="action-step-panel">
      <div className="action-step-head">
        <div>
          <strong>Select recommendations</strong>
          <p>
            Choose one or more recommendations for deeper analysis before
            approval.
          </p>
        </div>
        <div className="action-step-head-tools">
          <button
            type="button"
            className="alerts-mini-btn"
            onClick={onToggleAll}
          >
            {allSelected ? "Clear all" : `Select all (${totalActions})`}
          </button>
          <span className="selected-chip">{selectedCount} selected</span>
        </div>
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
                const graded = rankingFor(ranking, action);
                const band = graded.confidence;
                const isNextBest = nextBestIds.has(action.id);
                return (
                  <li key={action.id}>
                    <label
                      className={
                        "rec-action-card" +
                        (checked ? " selected" : "") +
                        (isNextBest ? " next-best" : "")
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
                          {isNextBest ? (
                            <span className="next-best-pill">
                              Next best action
                            </span>
                          ) : null}
                          {band ? (
                            <span
                              className={"confidence-pill confidence-" + band}
                              /* The basis is the whole point of QC-055: a
                                 confidence that will not say where it came
                                 from is decoration. */
                              title={graded.confidence_basis || ""}
                            >
                              {CONFIDENCE_WORD[band] || band}
                            </span>
                          ) : null}
                        </div>
                        {/* The agent's own judgement, in its own words. Any
                            figure it wrote was stripped server-side, so this
                            never argues with the computed line below it. */}
                        {graded.reason ? (
                          <p className="rec-action-reason">{graded.reason}</p>
                        ) : null}
                        <p>
                          {graded.impact ||
                            action.impact ||
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
          {continueBusy ? "Analyzing…" : "Analyze selected actions"}
        </button>
      </div>
    </div>
  );
}

function AnalysisStep({
  items,
  simResults,
  simPending,
  actionBusyId,
  onSimulate,
  onBack,
  onContinue,
}) {
  const pendingCount = items.filter(({ action }) =>
    simPending.has(action.id),
  ).length;
  const doneCount = items.length - pendingCount;

  return (
    <div className="action-step-panel">
      <div className="action-step-head">
        <div>
          <strong>Analysis</strong>
          <p>
            Review simulated impact for each selected action before approval.
          </p>
        </div>
        {pendingCount > 0 ? (
          <span className="selected-chip is-running">
            Simulating {doneCount}/{items.length}
          </span>
        ) : null}
      </div>

      <ul className="rec-action-list">
        {items.map(({ alert, action }) => {
          const pending = simPending.has(action.id);
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
            <li
              key={action.id}
              className={"rec-action-card static" + (pending ? " pending" : "")}
            >
              <div className="rec-action-body">
                <div className="rec-action-top">
                  <strong>{action.action}</strong>
                  {pending ? (
                    <span className="sim-pending-tag">
                      Simulating
                      <span className="thinking-dots" aria-hidden="true">
                        <i />
                        <i />
                        <i />
                      </span>
                    </span>
                  ) : (
                    <span className="alert-subagent">{alert.name}</span>
                  )}
                </div>
                {/* The card is laid out the moment Analysis opens; only the
                    body waits on the agent run, so nothing jumps when the
                    real summary replaces this. */}
                {pending ? (
                  <div className="sim-pending-body" role="status">
                    <SkeletonLines lines={3} />
                  </div>
                ) : (
                  <>
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
                  </>
                )}
                <div className="alert-action-btns">
                  <button
                    type="button"
                    className="alerts-mini-btn"
                    disabled={
                      pending || actionBusyId === action.id || !action.spec
                    }
                    onClick={() => onSimulate(action.id)}
                  >
                    {pending || actionBusyId === action.id
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
        {/* Deliberately not disabled while simulations run — approval shows
            each action's own state, so there is no reason to hold the user
            here waiting for every card to land. */}
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
  onDone,
}) {
  const pending = items.filter((item) => item.action.status === "planned");

  return (
    <div className="action-step-panel">
      <div className="action-step-head">
        <div>
          <strong>Approval</strong>
          <p>Confirm owner sign-off. Nothing executes without approval.</p>
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
                    {actionBusyId === action.id ? "Approving…" : "Approve"}
                  </button>
                </div>
              ) : null}
              <div className="rec-action-meta">
                <span>
                  <em>Alert</em> {alert.name}
                </span>
                <span>
                  <em>Owners</em> {(action.routes || []).join(", ") || "—"}
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

/**
 * Anchors a fixed-position layer directly under `anchorRef`.
 *
 * Header layers have to be `position: fixed` rather than absolute: the toolbar
 * scrolls horizontally (`.topbar-main { overflow-x: auto }`), which makes it a
 * clipping context, so an absolutely positioned layer gets cut off at the
 * header edge and reads as if it opened behind the board.
 */
function useAnchoredPosition(open, anchorRef) {
  const [position, setPosition] = useState(null);

  const place = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) {
      return;
    }

    const margin = 8;
    const rect = anchor.getBoundingClientRect();

    setPosition({
      top: rect.bottom + margin,
      right: Math.max(margin, window.innerWidth - rect.right),
    });
  }, [anchorRef]);

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }

    place();

    // The toolbar scrolls sideways and the board scrolls under it, so follow
    // the anchor rather than leaving the layer stranded off-position.
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, place]);

  return position;
}

// Hidden until the first measurement lands, so the layer never flashes in the
// corner before it is placed.
function anchoredStyle(position) {
  return {
    top: position ? `${position.top}px` : "-9999px",
    right: position ? `${position.right}px` : "-9999px",
    visibility: position ? "visible" : "hidden",
  };
}

function RecalculateIcon() {
  return (
    <svg
      className="alerts-recalc-icon"
      viewBox="0 0 24 24"
      width="15"
      height="15"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M12 5V2L8 6l4 4V7a5 5 0 11-5 5H5a7 7 0 107-7z"
      />
    </svg>
  );
}

function MoreIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M6 10a2 2 0 100 4 2 2 0 000-4zm6 0a2 2 0 100 4 2 2 0 000-4zm6 0a2 2 0 100 4 2 2 0 000-4z"
      />
    </svg>
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

function ChatSparkleIcon() {
  return (
    <svg
      className="chat-toggle-icon"
      viewBox="0 0 24 24"
      width="14"
      height="14"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M12 2.5l1.9 4.9 4.9 1.9-4.9 1.9L12 16l-1.9-4.8L5.2 9.3l4.9-1.9L12 2.5zm6.5 10l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9.9-2.3z"
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
  wide = false,
  scrollResetKey,
}) {
  const scrollRef = useRef(null);

  // The primary action is pinned to the bottom of the modal, so a step can
  // be advanced from halfway down a long list. Without this the next step
  // would open already scrolled past its own heading.
  useEffect(() => {
    if (scrollResetKey === undefined) {
      return;
    }
    scrollRef.current?.scrollTo({ top: 0 });
  }, [scrollResetKey]);

  return (
    <div
      className="alerts-modal-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        ref={scrollRef}
        className={"alerts-modal" + (wide ? " alerts-modal-wide" : "")}
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
    actionCounts[key] = (actionCounts[key] || 0) + (alert.actions || []).length;
  }

  if ((monitors || []).length > 0) {
    return monitors.map((monitor) => ({
      name: monitor.name,
      order: monitor.order,
      actionCount: actionCounts[monitor.name] || 0,
    }));
  }

  return Object.keys(actionCounts)
    .sort()
    .map((name, index) => ({
      name,
      order: index + 1,
      actionCount: actionCounts[name],
    }));
}

function formatMonitorName(name) {
  return String(name || "")
    .replace(/_monitoring_agent$/i, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Rank/confidence/reason keyed by action id.
 *
 * The alert-grouped payload and the agent-wide ranked payload are the same
 * rows fetched two ways, so they join cleanly on id.
 */
function indexByActionId(items) {
  return new Map((items || []).map((item) => [item.id, item]));
}

/**
 * What the ranked list says about one action, or a safe blank.
 *
 * A blank is normal rather than an error: an action with no cash lever the
 * agent can size keeps its stored wording and carries no confidence, because
 * grading how a number was computed is meaningless when none was.
 */
function rankingFor(ranking, action) {
  return ranking.get(action.id) || {};
}

// Deliberately not a guess. This used to read keywords out of the action text
// ("fraud" or "margin" meant High), which is the invented confidence QC-055
// reports; the band now comes from the backend, which derives it from how the
// figure was produced, and `confidence_basis` carries the justification.
const CONFIDENCE_WORD = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

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
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}
