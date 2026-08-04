/*
 * `serverFilters` values are real re-aggregations, not a client-side
 * re-filter — see `_server_filter` in dashboard_blocks.py — so each has to
 * round-trip here rather than narrow the payload already on the page. "ALL",
 * empty and omitted all mean "everything"; a key is left off the query
 * string entirely for that case rather than sent as a literal "ALL" the
 * backend has to special-case back out.
 *
 * The three keys match `server_filters[].id` on every dashboard response
 * (`legal_entity_id`, `period`, `category_group`) — an agent that does not
 * offer one of them simply never has that key set, and the backend ignores
 * a key it does not recognise for that agent (see each `build()`'s
 * docstring for which filters it actually reads).
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
