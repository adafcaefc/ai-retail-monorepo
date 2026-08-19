export const DEFAULT_FORECAST_DETAIL_SORT = Object.freeze({
  column: "forecast",
  direction: "desc",
});

const TEXT_COLLATOR = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

const SORT_VALUES = Object.freeze({
  sku: (row) => row?.sku_name,
  category: (row) => row?.category_label,
  ads: (row) => row?.ads_units_per_day,
  forecast: (row) => row?.forecast_units ?? row?.forecast_7d_units,
  trend: (row) => row?.trend_pct,
  signals: (row) => normalizeSignals(row?.signals),
  supply_state: (row) => row?.supply_state,
});

function isMissing(value) {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

function numericValue(value) {
  if (isMissing(value)) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function normalizeSignals(signals) {
  if (!Array.isArray(signals)) return "";
  return signals
    .map((signal) => (signal === null || signal === undefined ? "" : String(signal).trim().toLowerCase()))
    .join(", ");
}

function compareText(left, right) {
  return TEXT_COLLATOR.compare(String(left), String(right));
}

function comparePrimary(left, right, column) {
  const leftValue = SORT_VALUES[column](left);
  const rightValue = SORT_VALUES[column](right);
  const numericColumn = column === "ads" || column === "forecast" || column === "trend";

  if (numericColumn) {
    const leftNumber = numericValue(leftValue);
    const rightNumber = numericValue(rightValue);
    if (leftNumber === null || rightNumber === null) {
      if (leftNumber === null && rightNumber === null) return 0;
      return leftNumber === null ? 1 : -1;
    }
    return leftNumber - rightNumber;
  }

  if (isMissing(leftValue) || isMissing(rightValue)) {
    if (isMissing(leftValue) && isMissing(rightValue)) return 0;
    return isMissing(leftValue) ? 1 : -1;
  }

  return compareText(leftValue, rightValue);
}

function compareSkuId(left, right) {
  return compareText(left?.sku_id ?? "", right?.sku_id ?? "");
}

export function toggleForecastDetailSort(currentSort, column) {
  if (currentSort?.column === column) {
    return {
      column,
      direction: currentSort.direction === "asc" ? "desc" : "asc",
    };
  }

  return { column, direction: "asc" };
}

export function sortForecastDetailRows(rows, sort = DEFAULT_FORECAST_DETAIL_SORT) {
  const column = SORT_VALUES[sort?.column] ? sort.column : DEFAULT_FORECAST_DETAIL_SORT.column;
  const direction = sort?.direction === "asc" ? "asc" : "desc";
  const multiplier = direction === "asc" ? 1 : -1;

  return (Array.isArray(rows) ? rows : [])
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const primary = comparePrimary(left.row, right.row, column);

      // Missing values stay at the bottom in both directions. The primary
      // comparator already encodes that ordering, so do not reverse it.
      const leftValue = SORT_VALUES[column](left.row);
      const rightValue = SORT_VALUES[column](right.row);
      const leftMissing = numericColumn(column)
        ? numericValue(leftValue) === null
        : isMissing(leftValue);
      const rightMissing = numericColumn(column)
        ? numericValue(rightValue) === null
        : isMissing(rightValue);
      if (leftMissing || rightMissing) {
        if (leftMissing && rightMissing) {
          return compareSkuId(left.row, right.row) || left.index - right.index;
        }
        return leftMissing ? 1 : -1;
      }

      if (primary !== 0) return primary * multiplier;
      return compareSkuId(left.row, right.row) || left.index - right.index;
    })
    .map(({ row }) => row);
}

function numericColumn(column) {
  return column === "ads" || column === "forecast" || column === "trend";
}
