// Fetches the enabled modules once and shares them with the whole app.
// The backend registry (agents/modules.py) is the single source of truth for
// agents, so every consumer here waits for the same response instead of
// restating a list.
//
// Static pages (pages/registry.js) are prepended to that list. They are
// frontend-only screens with no backend module, so they are available before
// the fetch resolves and remain available if it fails.

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

import { fetchAgents } from "../api/agents.js";
import { buildPages } from "../pages/registry.js";
import { buildAgents, groupByFolder } from "./registry.js";

const AgentsContext = createContext(null);

// Discovered at build time and never changes, so one stable array serves as
// both the initial state and the prefix of every later one.
const PAGES = buildPages();

export function AgentsProvider({ children }) {
  const [agentList, setAgentList] = useState(PAGES);
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
        setAgentList([...PAGES, ...buildAgents(items)]);
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          // `agentList` is left at PAGES on purpose: the static pages own the
          // default screen, so they must survive a backend outage.
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
