// QC-043: narrowing the board to one product, week, tier or vendor.
//
// The backend declares which dimensions a payload can be sliced by and which
// elements each one applies to (`dashboard.filters`). Filtering happens here,
// on data already delivered, so changing a filter costs no round trip and
// cannot disagree with what the KPI row was computed from.
//
// Element keys are `view:<k>` and `side:<k>`, matching the info registry.

// A chart may abbreviate its label to fit ("Ind" for "Industrial"); `key`
// carries the full value the filter matches on.
function filterPoints(points, wanted) {
  return points.filter(
    (point) => String(point?.key ?? point?.label ?? "") === wanted
  );
}

/**
 * Apply the active selections to one chart or table.
 * Returns the element unchanged when no active filter targets it.
 */
export function applyFilters(
  element,
  elementKey,
  definitions,
  selected,
  othersLabel = "Others"
) {
  if (!element || !definitions?.length) {
    return element;
  }

  const active = definitions.filter(
    (definition) =>
      selected?.[definition.id] &&
      (definition.applies_to || []).includes(elementKey)
  );

  if (!active.length) {
    return element;
  }

  let next = element;

  for (const definition of active) {
    const wanted = selected[definition.id];

    if (next.table) {
      const column = definition.column ?? 0;
      const rows = next.table.rows.filter(
        (row) => String(row?.[column] ?? "") === wanted
      );
      next = { ...next, table: { ...next.table, rows } };
      continue;
    }

    // A line is a shape through time; dropping every other point leaves one
    // stranded dot (the audit: 13 weeks -> 1 survivor for every option). The
    // chosen point is highlighted on the intact curve instead.
    if (next.chart_type === "line") {
      next = { ...next, highlight: wanted };
      continue;
    }

    // A donut narrowed to one slice renders as a full ring — 100% of itself,
    // whatever the value. Keeping the rest aggregated as "Others" preserves
    // the share reading the donut exists for.
    if (next.chart_type === "donut" || next.chart_type === "pie") {
      const slices = next.data || [];
      const match = filterPoints(slices, wanted);
      const rest = slices.filter((point) => !match.includes(point));
      const others = rest.reduce(
        (sum, point) => sum + (Number(point?.value) || 0),
        0
      );
      next = {
        ...next,
        data: others > 0
          ? [...match, { label: othersLabel, value: others, muted: true }]
          : match,
      };
      continue;
    }

    const data = next.data || [];
    const isSeries =
      data.length > 0 &&
      data[0] &&
      typeof data[0] === "object" &&
      "values" in data[0];

    next = {
      ...next,
      data: isSeries
        ? data.map((series) => ({
            ...series,
            values: filterPoints(series.values || [], wanted),
          }))
        : filterPoints(data, wanted),
    };
  }

  return next;
}

/**
 * The view a filter should bring into the focus panel, or null.
 *
 * Several filters target one panel that is not the default view — "Cost line"
 * only touches the Finance opex table, "Vendor" only the leakage vendor table.
 * Choosing a value with that panel closed changed nothing on screen, so the
 * control read as broken. Side panels are always visible, so a filter that
 * touches one needs no move.
 */
export function focusFor(definition, activeKey) {
  const targets = definition?.applies_to || [];
  if (!targets.length || targets.includes(activeKey)) {
    return null;
  }
  if (targets.some((key) => key.startsWith("side:"))) {
    return null;
  }
  const view = targets.find((key) => key.startsWith("view:"));
  return view ? view.slice("view:".length) : null;
}

/** True when a filter has narrowed this element to nothing. */
export function isEmptyAfterFilter(element) {
  if (!element) {
    return false;
  }
  if (element.table) {
    return element.table.rows.length === 0;
  }
  const data = element.data || [];
  if (!data.length) {
    return false;
  }
  if (data[0] && typeof data[0] === "object" && "values" in data[0]) {
    return data.every((series) => (series.values || []).length === 0);
  }
  return false;
}
