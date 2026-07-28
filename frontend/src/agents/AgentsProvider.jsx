// Fetches the enabled modules once and shares them with the whole app.
// The backend registry (agents/modules.py) is the single source of truth, so
// every consumer here waits for the same response instead of restating a list.

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

import { fetchAgents } from "../api/agents.js";
import { buildAgents, groupByFolder } from "./registry.js";

const AgentsContext = createContext(null);

const EMPTY = [];

export function AgentsProvider({ children }) {
  const [agentList, setAgentList] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const items = await fetchAgents();
        if (cancelled) {
          return;
        }
        setAgentList(buildAgents(items));
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError.message || "Could not load the agent list."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => {
    return {
      agentList,
      agents: Object.fromEntries(
        agentList.map((agent) => [agent.id, agent])
      ),
      agentIds: agentList.map((agent) => agent.id),
      groups: groupByFolder(agentList),
      loading,
      error
    };
  }, [agentList, loading, error]);

  return (
    <AgentsContext.Provider value={value}>
      {children}
    </AgentsContext.Provider>
  );
}

export function useAgents() {
  const value = useContext(AgentsContext);
  if (!value) {
    throw new Error("useAgents must be used within AgentsProvider");
  }
  return value;
}
