/**
 * Map frontend agent IDs to alerts/actions API domain names.
 * Backend also accepts aliases (collections→collection, treasury→cashflow).
 */
export function toAlertsAgent(agentId) {
  const aliases = {
    collections: "collection",
    treasury: "cashflow"
  };
  return aliases[agentId] || agentId;
}

export async function fetchMonitoringAgents(agentId) {
  const agent = toAlertsAgent(agentId);
  const response = await fetch(
    `/api/monitoring-agents?agent=${encodeURIComponent(agent)}`
  );
  return parseJson(response, "Monitoring agents request failed");
}

export async function fetchAlerts(agentId) {
  const agent = toAlertsAgent(agentId);
  const response = await fetch(
    `/api/alerts?agent=${encodeURIComponent(agent)}`
  );
  return parseJson(response, "Alerts request failed");
}

export async function fetchAlertActions(alertId) {
  const response = await fetch(
    `/api/alerts/${encodeURIComponent(alertId)}/actions`
  );
  return parseJson(response, "Alert actions request failed");
}

export async function fetchActions(agentId) {
  const agent = toAlertsAgent(agentId);
  const response = await fetch(
    `/api/actions?agent=${encodeURIComponent(agent)}`
  );
  return parseJson(response, "Actions history request failed");
}

export async function clearAlerts(agentId) {
  const agent = toAlertsAgent(agentId);
  const response = await fetch(
    `/api/alerts?agent=${encodeURIComponent(agent)}`,
    { method: "DELETE" }
  );
  return parseJson(response, "Clear alerts request failed");
}

export async function populateAlerts(agentId) {
  const agent = toAlertsAgent(agentId);
  const response = await fetch(
    `/api/alerts/populate?agent=${encodeURIComponent(agent)}`,
    { method: "POST" }
  );
  return parseJson(response, "Populate alerts request failed");
}

export async function resetAndRepopulateAlerts(agentId) {
  await clearAlerts(agentId);
  return populateAlerts(agentId);
}

export async function approveAction(actionId) {
  const response = await fetch(
    `/api/actions/${encodeURIComponent(actionId)}/approve`,
    { method: "POST" }
  );
  return parseJson(response, "Approve action request failed");
}

export async function simulateAction(actionId) {
  const response = await fetch(
    `/api/actions/${encodeURIComponent(actionId)}/simulate`,
    { method: "POST" }
  );
  return parseJson(response, "Simulate action request failed");
}

/**
 * Load alerts for an agent and attach each alert's actions.
 */
export async function fetchAlertsWithActions(agentId) {
  const payload = await fetchAlerts(agentId);
  const alerts = Array.isArray(payload.items) ? payload.items : [];

  const withActions = await Promise.all(
    alerts.map(async (alert) => {
      try {
        const actionsPayload = await fetchAlertActions(alert.id);
        return {
          ...alert,
          actions: Array.isArray(actionsPayload.items)
            ? actionsPayload.items
            : []
        };
      } catch {
        return {
          ...alert,
          actions: []
        };
      }
    })
  );

  return {
    items: withActions,
    count: withActions.length
  };
}

async function parseJson(response, fallback) {
  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(detail || `${fallback} (${response.status})`);
  }
  return response.json();
}

async function safeDetail(response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) => item.msg || JSON.stringify(item))
        .join("; ");
    }
    return payload.error || "";
  } catch {
    return "";
  }
}
