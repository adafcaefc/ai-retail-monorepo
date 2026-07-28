// The enabled modules, served by the backend registry
// (backend/src/llm/agents/modules.py). Response order is sidebar order.

export async function fetchAgents() {
  const response = await fetch("/api/html/agents");

  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(
      detail || `Agents request failed (${response.status})`
    );
  }

  const payload = await response.json();
  return payload.items || [];
}

async function safeDetail(response) {
  try {
    const payload = await response.json();
    return payload.detail || payload.error || "";
  } catch {
    return "";
  }
}
