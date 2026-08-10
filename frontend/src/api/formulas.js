// Formula Manager CRUD. Root-relative paths: Vite proxies /api in dev and
// FastAPI serves the build from the same origin in production.

export async function fetchFormulas() {
  const response = await fetch("/api/formulas");
  return parseJson(response, "Formulas request failed");
}

export async function createFormula(formula) {
  const response = await fetch("/api/formulas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(formula)
  });
  return parseJson(response, "Create formula request failed");
}

export async function updateFormula(formulaId, formula) {
  const response = await fetch(
    `/api/formulas/${encodeURIComponent(formulaId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formula)
    }
  );
  return parseJson(response, "Update formula request failed");
}

export async function deleteFormula(formulaId) {
  const response = await fetch(
    `/api/formulas/${encodeURIComponent(formulaId)}`,
    { method: "DELETE" }
  );
  return parseJson(response, "Delete formula request failed");
}

/** Check a draft expression against its parameters without storing it. */
export async function validateFormula(expression, parameters) {
  const response = await fetch("/api/formulas/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expression, parameters })
  });
  return parseJson(response, "Validate formula request failed");
}

/** Run a stored formula against parameter values. */
export async function evaluateFormula(formulaId, values) {
  const response = await fetch(
    `/api/formulas/${encodeURIComponent(formulaId)}/evaluate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values })
    }
  );
  return parseJson(response, "Evaluate formula request failed");
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
