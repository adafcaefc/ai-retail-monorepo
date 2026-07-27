import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import {
  fetchAlerts,
  resetAndRepopulateAlerts
} from "../api/alerts.js";
import { AGENT_IDS, AGENT_LIST } from "../agents/registry.js";

// Display names for toast copy, keyed by canonical `folder.agent` id.
const AGENT_META = Object.fromEntries(
  AGENT_LIST.map((agent) => [agent.id, agent.name])
);

// How many problem toasts to pop at once; the rest collapse into a "+N more".
const MAX_PROBLEM_TOASTS = 4;

// Persist which problems have already been announced. Identity is by CONTENT,
// not id, because alerts are re-populated (fresh ids) on every monitoring run.
const SEEN_KEY = "ledgerline.seenProblems";

const MonitoringContext = createContext(null);

/** Page-session lock so StrictMode remounts do not double-start. */
let pageAutoStartPromise = null;

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
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [runId, setRunId] = useState(0);
  const [problems, setProblems] = useState([]);
  const [moreProblems, setMoreProblems] = useState(0);
  const runningRef = useRef(false);

  // After a monitoring run, collect alerts across all boards and surface only
  // the ones we have never announced before as problem toasts.
  const refreshProblems = useCallback(async () => {
    const perAgent = await Promise.all(
      AGENT_IDS.map(async (agentId) => {
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
      agentName: AGENT_META[alert.agentId] || alert.agentId,
      name: alert.name || "Issue detected",
      issue: alert.issue || ""
    }));

    setProblems(shown);
    setMoreProblems(Math.max(0, fresh.length - shown.length));
  }, []);

  const dismissProblem = useCallback((id) => {
    setProblems((current) => current.filter((item) => item.id !== id));
  }, []);

  const runMonitoring = useCallback(async ({ force = false } = {}) => {
    if (runningRef.current) {
      return pageAutoStartPromise;
    }

    if (!force && pageAutoStartPromise) {
      return pageAutoStartPromise;
    }

    runningRef.current = true;
    setStatus("running");
    setError("");
    setNote("Running monitoring agents across all boards…");

    const task = (async () => {
      try {
        const results = await Promise.all(
          AGENT_IDS.map((agentId) => resetAndRepopulateAlerts(agentId))
        );
        const created = results.reduce(
          (sum, result) => sum + (result.created_count ?? 0),
          0
        );
        setNote(
          `Monitoring complete — ${created} alert${
            created === 1 ? "" : "s"
          } across all boards.`
        );
        setStatus("done");
        setRunId((value) => value + 1);

        // Surface any newly detected problems as toasts (best-effort).
        try {
          await refreshProblems();
        } catch {
          // non-fatal: alerts still live in the bell
        }
      } catch (runError) {
        setError(
          runError.message || "Monitoring agents failed to run."
        );
        setNote("");
        setStatus("error");
        if (!force) {
          pageAutoStartPromise = null;
        }
      } finally {
        runningRef.current = false;
      }
    })();

    if (!force) {
      pageAutoStartPromise = task;
    }

    return task;
  }, [refreshProblems]);

  useEffect(() => {
    runMonitoring({ force: false });
  }, [runMonitoring]);

  const recalculate = useCallback(() => {
    pageAutoStartPromise = null;
    return runMonitoring({ force: true });
  }, [runMonitoring]);

  const value = useMemo(
    () => ({
      status,
      error,
      note,
      runId,
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
      runId,
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
