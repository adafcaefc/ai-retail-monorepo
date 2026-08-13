// Frontend agent ids are the canonical `folder.agent` ids the API expects.

export async function fetchMonitoringAgents(agentId) {
  const response = await fetch(
    `/api/monitoring-agents?agent=${encodeURIComponent(agentId)}`
  );
  return parseJson(response, "Monitoring agents request failed");
}

export async function fetchAlerts(agentId) {
  const response = await fetch(
    `/api/alerts?agent=${encodeURIComponent(agentId)}`
  );
  return parseJson(response, "Alerts request failed");
}

export async function fetchAlertActions(alertId, { status } = {}) {
  const response = await fetch(
    `/api/alerts/${encodeURIComponent(alertId)}/actions${statusQuery(status)}`
  );
  return parseJson(response, "Alert actions request failed");
}

export async function fetchActions(agentId, { status } = {}) {
  const response = await fetch(
    `/api/actions?agent=${encodeURIComponent(agentId)}${statusQuery(status, "&")}`
  );
  return parseJson(response, "Actions history request failed");
}

export async function fetchActionHistory(agentId) {
  const response = await fetch(
    `/api/actions/history?agent=${encodeURIComponent(agentId)}`
  );
  return parseJson(response, "Action history request failed");
}

export async function clearAlerts(agentId) {
  const response = await fetch(
    `/api/alerts?agent=${encodeURIComponent(agentId)}`,
    { method: "DELETE" }
  );
  return parseJson(response, "Clear alerts request failed");
}

export async function populateAlerts(agentId) {
  const response = await fetch(
    `/api/alerts/populate?agent=${encodeURIComponent(agentId)}`,
    { method: "POST" }
  );
  return parseJson(response, "Populate alerts request failed");
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
export async function fetchAlertsWithActions(agentId, { status } = {}) {
  const payload = await fetchAlerts(agentId);
  const alerts = Array.isArray(payload.items) ? payload.items : [];

  const withActions = await Promise.all(
    alerts.map(async (alert) => {
      try {
        const actionsPayload = await fetchAlertActions(alert.id, { status });
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

function statusQuery(status, prefix = "?") {
  return status ? `${prefix}status=${encodeURIComponent(status)}` : "";
}

async function parseJson(response, fallback) {
  if (!response.ok) {
    const detail = await safeDetail(response);
    const error = new Error(detail || `${fallback} (${response.status})`);
    // Callers that need to branch on the failure (a 409 "already running"
    // populate is not the same kind of failure as a 500) read this instead
    // of pattern-matching the message text.
    error.status = response.status;
    throw error;
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
