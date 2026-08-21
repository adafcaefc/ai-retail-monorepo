const HANDOFFS_ENDPOINT = "/api/retail/agent-handoffs";
const INBOX_ENDPOINT = "/api/retail/agent-inbox";

async function safeDetail(response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") return payload.detail;
    if (Array.isArray(payload?.detail)) {
      return payload.detail
        .map((item) => item.msg || JSON.stringify(item))
        .join("; ");
    }
    return payload?.error || "";
  } catch {
    return "";
  }
}

async function parseJson(response, fallback) {
  if (!response.ok) {
    const detail = await safeDetail(response);
    const error = new Error(detail || `${fallback} (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function createAgentHandoff(payload, { signal } = {}) {
  const response = await fetch(HANDOFFS_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  return parseJson(response, "Agent handoff creation failed");
}

export async function fetchAgentHandoff(handoffId, { signal } = {}) {
  const response = await fetch(
    `${HANDOFFS_ENDPOINT}/${encodeURIComponent(handoffId)}`,
    { signal },
  );
  return parseJson(response, "Agent handoff detail request failed");
}

export async function fetchAgentInbox(agentId, { signal } = {}) {
  const response = await fetch(
    `${INBOX_ENDPOINT}?agent=${encodeURIComponent(agentId)}`,
    { signal },
  );
  return parseJson(response, "Agent inbox request failed");
}

export async function updateAgentHandoffStatus(
  handoffId,
  status,
  { signal } = {},
) {
  const response = await fetch(
    `${HANDOFFS_ENDPOINT}/${encodeURIComponent(handoffId)}/status`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
      signal,
    },
  );
  return parseJson(response, "Agent handoff status update failed");
}

export { HANDOFFS_ENDPOINT, INBOX_ENDPOINT };
