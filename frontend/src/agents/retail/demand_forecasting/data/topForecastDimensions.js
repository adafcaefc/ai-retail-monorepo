export const TOP_FORECAST_DIMENSION_LIMIT = 20;

const LABEL_COLLATOR = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

function rawForecast(row) {
  if (row?.forecast_units === null || row?.forecast_units === undefined || row?.forecast_units === "") {
    return null;
  }

  const value = Number(row.forecast_units);
  return Number.isFinite(value) ? value : null;
}

function compareLabels(left, right) {
  const labelOrder = LABEL_COLLATOR.compare(
    String(left?.label ?? ""),
    String(right?.label ?? ""),
  );
  if (labelOrder) return labelOrder;

  const idOrder = LABEL_COLLATOR.compare(
    String(left?.id ?? ""),
    String(right?.id ?? ""),
  );
  return idOrder;
}

/**
 * Return the highest forecast dimension rows without changing the source.
 * The caller supplies the already-filtered category/store result set.
 */
export function takeTopForecastDimensions(
  rows,
  limit = TOP_FORECAST_DIMENSION_LIMIT,
) {
  const numericLimit = Number(limit);
  const rowLimit = Number.isFinite(numericLimit)
    ? Math.max(0, Math.floor(numericLimit))
    : TOP_FORECAST_DIMENSION_LIMIT;

  return (Array.isArray(rows) ? rows : [])
    .map((row, index) => ({ row, index, forecast: rawForecast(row) }))
    .sort((left, right) => {
      if (left.forecast === null || right.forecast === null) {
        if (left.forecast === null && right.forecast === null) {
          return compareLabels(left.row, right.row) || left.index - right.index;
        }
        return left.forecast === null ? 1 : -1;
      }

      const forecastOrder = right.forecast - left.forecast;
      return forecastOrder || compareLabels(left.row, right.row) || left.index - right.index;
    })
    .slice(0, rowLimit)
    .map(({ row }) => row);
}
