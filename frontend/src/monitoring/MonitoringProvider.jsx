import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import { resetAndRepopulateAlerts } from "../api/alerts.js";
import { AGENT_IDS } from "../agents/registry.js";

const MonitoringContext = createContext(null);

/** Page-session lock so StrictMode remounts do not double-start. */
let pageAutoStartPromise = null;

export function MonitoringProvider({ children }) {
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [runId, setRunId] = useState(0);
  const runningRef = useRef(false);

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
  }, []);

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
      recalculate
    }),
    [status, error, note, runId, recalculate]
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
