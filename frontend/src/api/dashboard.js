/*
 * `serverFilters` values are real re-aggregations, not a client-side
 * re-filter — see `_server_filter` in dashboard_blocks.py — so each has to
 * round-trip here rather than narrow the payload already on the page. "ALL",
 * empty and omitted all mean "everything"; a key is left off the query
 * string entirely for that case rather than sent as a literal "ALL" the
 * backend has to special-case back out.
 *
 * Every key must be a field of `DashboardScope` (backend
 * `llm/agents/common/dashboard_scope.py`). A key outside that set is now a
 * 400 rather than a silent drop, which is deliberate: the Retail boards send
 * `store_id`, `state`, `route`, `sku` and `reorder_only`, and until the scope
 * became an object those five were discarded by a route that accepted three
 * positional parameters — filters that appeared to work over figures that had
 * not moved.
 *
 * A filter the agent's data cannot narrow by is still answered, and named in
 * `ignored_filters` on the response.
 */
export async function fetchDashboard(agent, serverFilters = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(serverFilters)) {
    if (value && value !== "ALL") {
      params.set(key, value);
    }
  }
  const query = params.toString() ? `?${params.toString()}` : "";

  const response = await fetch(
    `/api/html/dashboard/${encodeURIComponent(agent)}${query}`
  );

  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(
      detail || `Dashboard request failed (${response.status})`
    );
  }

  return response.json();
}

export async function recalculateDashboardSimulation(
  action,
  body
) {
  const pathByAction = {
    calculate_collection_scenario:
      "/api/html/simulations/collection/recalculate",
    simulate_cashflow:
      "/api/html/simulations/treasury/recalculate",
    simulate_finance:
      "/api/html/simulations/finance/recalculate",
    simulate_leakage:
      "/api/html/simulations/leakage/recalculate"
  };

  const path = pathByAction[action];
  if (!path) {
    throw new Error(`Unsupported simulation action: ${action}`);
  }

  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(
      detail || `Simulation failed (${response.status})`
    );
  }

  return response.json();
}

async function safeDetail(response) {
  try {
    const payload = await response.json();
    return payload.detail || payload.error || "";
  } catch {
    return "";
  }
}
