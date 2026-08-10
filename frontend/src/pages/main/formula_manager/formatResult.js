// Results are compared against values read from the workbook's saved
// calculation cache, which stores more precision than Excel displays. A tiny
// relative tolerance is what makes "matches the workbook" meaningful.
const RELATIVE_TOLERANCE = 1e-6;

export function formatResult(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "TRUE" : "FALSE";
  }
  if (typeof value !== "number") {
    return String(value);
  }
  return value.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

export function resultsMatch(computed, expected) {
  if (computed === null || computed === undefined) {
    return false;
  }
  if (typeof expected === "string" || typeof computed === "string") {
    return String(computed) === String(expected);
  }

  const first = Number(computed);
  const second = Number(expected);
  if (Number.isNaN(first) || Number.isNaN(second)) {
    return false;
  }

  const scale = Math.max(Math.abs(first), Math.abs(second), 1);
  return Math.abs(first - second) <= RELATIVE_TOLERANCE * scale;
}
