/*
 * The Data Source page is the one static page that talks to the backend. It
 * reads windows of the workbook in `resources/` rather than downloading the
 * 10MB file: the backend parses it with openpyxl and returns cells that
 * already carry their display string and their formatting.
 *
 * Sheet names are the ids, and they are not all ASCII — one sheet is
 * "What-If · Per Agent", with a middle dot — so encodeURIComponent is
 * mandatory here, not defensive.
 */
export async function fetchSheetList() {
  const response = await fetch("/api/excel/sheets");

  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(
      detail || `Sheet list request failed (${response.status})`
    );
  }

  return response.json();
}

export async function fetchSheetPage(sheet, { offset = 0, limit = 100 } = {}) {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit)
  });

  const response = await fetch(
    `/api/excel/sheets/${encodeURIComponent(sheet)}?${params.toString()}`
  );

  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(
      detail || `Sheet request failed (${response.status})`
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
