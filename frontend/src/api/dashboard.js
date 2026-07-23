export async function fetchDashboard(agent) {
  const response = await fetch(
    `/api/html/dashboard/${encodeURIComponent(agent)}`
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
      "/api/html/simulations/collections/recalculate",
    simulate_cashflow:
      "/api/html/simulations/cashflow/recalculate",
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
