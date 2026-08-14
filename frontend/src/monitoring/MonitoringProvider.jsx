import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import { fetchAlerts, populateAlerts } from "../api/alerts.js";
import { useAgents } from "../agents/AgentsProvider.jsx";

// How many problem toasts to pop at once; the rest collapse into a "+N more".
const MAX_PROBLEM_TOASTS = 4;

// Persist which problems have already been announced. Identity is by CONTENT,
// not id, because alerts accumulate (fresh ids on every monitoring run, old
// ones never removed).
const SEEN_KEY = "ledgerline.seenProblems";

const MonitoringContext = createContext(null);

function problemKey(agentId, alert) {
  return `${agentId}::${(alert.name || "").trim()}::${(alert.issue || "").trim()}`
    .toLowerCase();
}

function readSeen() {
  try {
    const raw = window.localStorage.getItem(SEEN_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function writeSeen(keys) {
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify(keys));
  } catch {
    // ignore storage failures
  }
}

export function MonitoringProvider({ children }) {
  const { agentList } = useAgents();

  const monitoredAgentIds = useMemo(
    () =>
      agentList
        .filter((agent) => !agent.dashboardOnly)
        .map((agent) => agent.id),
    [agentList]
  );

  // Display names for toast copy, keyed by canonical `folder.agent` id.
  const agentMeta = useMemo(
    () =>
      Object.fromEntries(
        agentList.map((agent) => [agent.id, agent.name])
      ),
    [agentList]
  );

  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  // Per-agent, not one shared counter: only a board whose populate actually
  // completed gets its own entry bumped, so recalculating one board cannot
  // reset another board's open Agent Action wizard/selection. AlertsPanel
  // keys its reload effect off runVersions[agentId].
  const [runVersions, setRunVersions] = useState({});
  const [problems, setProblems] = useState([]);
  const [moreProblems, setMoreProblems] = useState(0);
  // The in-flight recalculate promise, so a duplicate click while one is
  // already running returns that same promise instead of starting a second.
  const runningTaskRef = useRef(null);

  // After a monitoring run, collect alerts across all boards and surface only
  // the ones we have never announced before as problem toasts.
  const refreshProblems = useCallback(async () => {
    const perAgent = await Promise.all(
      monitoredAgentIds.map(async (agentId) => {
        try {
          const payload = await fetchAlerts(agentId);
          return (payload.items || []).map((alert) => ({
            ...alert,
            agentId
          }));
        } catch {
          return [];
        }
      })
    );

    const all = perAgent.flat();
    const seen = readSeen();

    const fresh = all.filter(
      (alert) => !seen.has(problemKey(alert.agentId, alert))
    );

    // Everything currently present is now considered "seen".
    writeSeen(all.map((alert) => problemKey(alert.agentId, alert)));

    const shown = fresh.slice(0, MAX_PROBLEM_TOASTS).map((alert) => ({
      id: alert.id || problemKey(alert.agentId, alert),
      agentId: alert.agentId,
      agentName: agentMeta[alert.agentId] || alert.agentId,
      name: alert.name || "Issue detected",
      issue: alert.issue || ""
    }));

    setProblems(shown);
    setMoreProblems(Math.max(0, fresh.length - shown.length));
  }, [monitoredAgentIds, agentMeta]);

  const dismissProblem = useCallback((id) => {
    setProblems((current) => current.filter((item) => item.id !== id));
  }, []);

  // A returning user still gets toasts for issues an earlier manual
  // Recalculate already raised, in this tab or another. This is a pure read
  // of whatever monitoring already stored -- it never triggers a populate.
  useEffect(() => {
    if (monitoredAgentIds.length === 0) {
      return;
    }
    refreshProblems().catch(() => {
      // non-fatal: alerts still live in the bell
    });
    // Re-run only when the set of monitored agents actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monitoredAgentIds.join(",")]);

  // The only way monitoring ever runs now: the manual Recalculate button.
  // There is no auto-start on mount or on agent switch any more.
  const recalculate = useCallback(() => {
    if (monitoredAgentIds.length === 0) {
      return undefined;
    }

    if (runningTaskRef.current) {
      return runningTaskRef.current;
    }

    setStatus("running");
    setError("");
    setNote("Running monitoring agents across all boards…");

    const task = (async () => {
      // Each board's populate is independent: one domain's 409 or failure
      // must not sink the whole batch or keep the others from completing.
      const outcomes = await Promise.all(
        monitoredAgentIds.map(async (agentId) => {
          try {
            const result = await populateAlerts(agentId);
            return { agentId, ok: true, result };
          } catch (runError) {
            return {
              agentId,
              ok: false,
              alreadyRunning: runError.status === 409,
              error: runError.message || "Monitoring agent failed to run."
            };
          }
        })
      );

      const completed = outcomes.filter((item) => item.ok);
      const alreadyRunning = outcomes.filter(
        (item) => !item.ok && item.alreadyRunning
      );
      const failed = outcomes.filter(
        (item) => !item.ok && !item.alreadyRunning
      );

      if (completed.length > 0) {
        setRunVersions((current) => {
          const next = { ...current };
          for (const item of completed) {
            next[item.agentId] = (next[item.agentId] || 0) + 1;
          }
          return next;
        });
      }

      const created = completed.reduce(
        (sum, item) => sum + (item.result.created_count ?? 0),
        0
      );

      if (failed.length > 0) {
        setError(
          failed
            .map(
              (item) =>
                `${agentMeta[item.agentId] || item.agentId}: ${item.error}`
            )
            .join("; ")
        );
        setNote("");
        setStatus("error");
      } else {
        const parts = [
          `${created} alert${created === 1 ? "" : "s"} across ${
            completed.length
          } board${completed.length === 1 ? "" : "s"}`
        ];
        if (alreadyRunning.length > 0) {
          parts.push(
            `${alreadyRunning.length} board${
              alreadyRunning.length === 1 ? "" : "s"
            } already being recalculated elsewhere`
          );
        }
        setNote(`Monitoring complete — ${parts.join("; ")}.`);
        setStatus("done");
      }

      // Surface any newly detected problems as toasts (best-effort).
      try {
        await refreshProblems();
      } catch {
        // non-fatal: alerts still live in the bell
      }

      runningTaskRef.current = null;
    })();

    runningTaskRef.current = task;
    return task;
  }, [monitoredAgentIds, agentMeta, refreshProblems]);

  const value = useMemo(
    () => ({
      status,
      error,
      note,
      runVersions,
      isRunning: status === "running",
      recalculate,
      problems,
      moreProblems,
      dismissProblem
    }),
    [
      status,
      error,
      note,
      runVersions,
      recalculate,
      problems,
      moreProblems,
      dismissProblem
    ]
  );

  return (
    <MonitoringContext.Provider value={value}>
      {children}
    </MonitoringContext.Provider>
  );
}

export function useMonitoring() {
  const value = useContext(MonitoringContext);
  if (!value) {
    throw new Error("useMonitoring must be used within MonitoringProvider");
  }
  return value;
}
