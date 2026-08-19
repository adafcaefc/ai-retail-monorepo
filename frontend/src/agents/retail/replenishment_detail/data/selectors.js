/**
 * Every figure this board shows, derived from the rows the API returns.
 *
 * Pure functions over plain arrays. The backend returns lines, not a finished
 * dashboard, and the aggregation lives here — same split as the sibling Retail
 * boards, and for the same reason: porting it to Python would create a second
 * implementation of the same arithmetic that then has to be kept in step
 * forever.
 *
 * What is NOT recomputed here: the per-line conversion, exception codes and
 * eligibility. Those arrive on the line from `dashboard.py`, because the chat
 * agent's snapshot has to flag exactly the lines the grid flags. Deriving them
 * a second time in JavaScript is how the agent ends up confidently describing a
 * line the grid does not show as blocked.
 */

import { ALL, DEFAULT_SCOPE, DEFAULT_SORT } from "./contract.js";

/** Item search covers code AND name — spec section 9. */
export function matchesSearch(line, term) {
  const needle = String(term || "").trim().toLowerCase();
  if (!needle) return true;
  return (
    String(line.sku_id || "").toLowerCase().includes(needle) ||
    String(line.name || "").toLowerCase().includes(needle)
  );
}

function matchesReorderStatus(line, status) {
  if (status === ALL) return true;
  if (status === "YES") return line.is_reorder === true;
  // "NO_ORDER" is the third question a detail page gets asked: what did we
  // decide not to buy. A resting line is one with no order to place, which is
  // not the same as one that failed a check.
  if (status === "NO_ORDER") return line.action_eligibility === "NO_ORDER";
  return true;
}

function withinAmountBand(line, min, max) {
  const amount = Number(line.amount) || 0;
  // Blank is "no bound", not zero — an empty box must not exclude every line.
  const low = min === "" || min == null ? null : Number(min);
  const high = max === "" || max == null ? null : Number(max);
  if (low != null && Number.isFinite(low) && amount < low) return false;
  if (high != null && Number.isFinite(high) && amount > high) return false;
  return true;
}

/** The nine client-side predicates of spec section 9, applied together. */
export function scopeLines(lines, scope = {}) {
  const merged = { ...DEFAULT_SCOPE, ...scope };
  return (lines || []).filter(
    (line) =>
      matchesReorderStatus(line, merged.reorder_status) &&
      matchesSearch(line, merged.sku) &&
      (merged.designated_vendor === ALL ||
        line.designated_vendor === merged.designated_vendor) &&
      (merged.best_price_vendor === ALL ||
        line.best_price_vendor === merged.best_price_vendor) &&
      (merged.buy_uom === ALL || line.buy_uom === merged.buy_uom) &&
      (merged.eligibility === ALL ||
        line.action_eligibility === merged.eligibility) &&
      (!merged.saving_only || Number(line.saving_vs_designated) > 0) &&
      withinAmountBand(line, merged.min_amount, merged.max_amount),
  );
}

export function sum(rows, key) {
  return (rows || []).reduce((total, row) => total + (Number(row[key]) || 0), 0);
}

/**
 * The six KPIs of spec section 7.
 *
 * Two populations on purpose, as Agent 3 does. `lines` is what the grid shows;
 * `allLines` is everything in scope before the reorder-status filter. The
 * reorder count and the SKU denominator have to come from the second, or
 * opening the board on "Needs reorder" would make the count equal the row
 * count and the ratio meaningless.
 *
 * `buy_uom_count` rather than a summed buy quantity — spec section 7's
 * critical display rule. The quantities are in `computeUomBreakdown`.
 */
export function computeKpis(lines, allLines) {
  const universe = allLines && allLines.length ? allLines : lines;
  const uoms = new Set(
    lines.filter((line) => line.buy_uom).map((line) => line.buy_uom),
  );

  return {
    reorder_sku_count: universe.filter((line) => line.is_reorder).length,
    skus_in_scope: universe.length,
    order_qty_sales: sum(lines, "order_qty_sales"),
    ordered_sales_units: sum(lines, "ordered_sales_units"),
    rounding_uplift: sum(lines, "rounding_uplift"),
    purchase_amount: sum(lines, "amount"),
    potential_saving: sum(lines, "saving_vs_designated"),
    alternate_vendor_count: lines.filter((line) => line.has_alternate_vendor)
      .length,
    blocked_count: lines.filter(
      (line) => line.action_eligibility === "BLOCKED",
    ).length,
    buy_uom_count: uoms.size,
    line_count: lines.length,
  };
}

/**
 * Buy quantity grouped by UOM, because the total would be meaningless.
 *
 * Spec section 7 and section 17, finding 9. Summing Crates, Pallets and Packs
 * gives a number that is arithmetically valid and that nobody can act on, so
 * this is what the board shows in its place.
 */
export function computeUomBreakdown(lines) {
  const groups = new Map();
  for (const line of lines) {
    const uom = line.buy_uom || "(none)";
    const bucket = groups.get(uom) || {
      buy_uom: uom,
      line_count: 0,
      order_qty_buy: 0,
      ordered_sales_units: 0,
      amount: 0,
    };
    bucket.line_count += 1;
    bucket.order_qty_buy += Number(line.order_qty_buy) || 0;
    bucket.ordered_sales_units += Number(line.ordered_sales_units) || 0;
    bucket.amount += Number(line.amount) || 0;
    groups.set(uom, bucket);
  }
  return [...groups.values()].sort((a, b) => b.amount - a.amount);
}

/** How many lines carry each exception code, for the filter and the strip. */
export function computeExceptionCounts(lines) {
  const counts = {};
  for (const line of lines) {
    for (const code of line.exception_codes || []) {
      counts[code] = (counts[code] || 0) + 1;
    }
  }
  return counts;
}

/**
 * Dropdown options for the three filters the backend does not serve.
 *
 * Derived from the full row set rather than the filtered one: a dropdown that
 * only offers what is already selected cannot be used to change the selection.
 */
export function computeFilterFacets(lines) {
  const designated = new Set();
  const best = new Set();
  const uoms = new Set();
  for (const line of lines) {
    if (line.designated_vendor) designated.add(line.designated_vendor);
    if (line.best_price_vendor) best.add(line.best_price_vendor);
    if (line.buy_uom) uoms.add(line.buy_uom);
  }
  const option = (value) => ({ value, label: value });
  return {
    vendors: [...designated].sort().map(option),
    best_price_vendors: [...best].sort().map(option),
    buy_uoms: [...uoms].sort().map(option),
  };
}

/** Quotes keyed by SKU, so the inspector is a lookup rather than a scan. */
export function indexQuotes(quotes) {
  const bySku = {};
  for (const quote of quotes || []) {
    (bySku[quote.sku_id] ||= []).push(quote);
  }
  return bySku;
}

const TEXT_COLUMNS = new Set([
  "sku_id",
  "name",
  "category_label",
  "vertical_id",
  "buy_uom",
  "designated_vendor",
  "best_price_vendor",
  "action_eligibility",
]);

/**
 * Sort, defaulting to spec section 8.1: Amount desc, Saving desc, Item asc.
 *
 * The two tiebreakers are not decoration. Hundreds of lines share an Amount of
 * zero, and without a stable final key the same query returns them in a
 * different order each render, which reads as data changing under the reader.
 */
export function sortLines(lines, sort = DEFAULT_SORT) {
  const { by = DEFAULT_SORT.by, direction = DEFAULT_SORT.direction } = sort || {};
  const factor = direction === "asc" ? 1 : -1;
  const isText = TEXT_COLUMNS.has(by);

  return [...lines].sort((a, b) => {
    let primary;
    if (isText) {
      primary = String(a[by] ?? "").localeCompare(String(b[by] ?? "")) * factor;
    } else {
      primary = ((Number(a[by]) || 0) - (Number(b[by]) || 0)) * factor;
    }
    if (primary !== 0) return primary;

    const saving =
      (Number(b.saving_vs_designated) || 0) -
      (Number(a.saving_vs_designated) || 0);
    if (by !== "saving_vs_designated" && saving !== 0) return saving;

    return String(a.sku_id ?? "").localeCompare(String(b.sku_id ?? ""));
  });
}

/**
 * The five row states of spec section 8.2, resolved to one class per row.
 *
 * Ordered by what a planner needs to notice first: a line that cannot be acted
 * on outranks one that merely has an opportunity attached.
 */
export function rowState(line) {
  if (line.action_eligibility === "BLOCKED") return "blocked";
  if (line.action_eligibility === "NO_ORDER") return "resting";
  if (line.has_alternate_vendor) return "alternate";
  if (Number(line.saving_vs_designated) > 0) return "saving";
  return "action";
}

/**
 * The four inspector sections of spec section 8.3, plus the section 8.4 trace.
 *
 * The Execution section reports what is absent by name. The alternative is
 * four empty fields, which reads as data that failed to load rather than as a
 * dataset that never carried it.
 */
export function buildInspector(line, quotesBySku, terms) {
  if (!line) return null;
  const quotes = [...(quotesBySku?.[line.sku_id] || [])].sort(
    (a, b) => a.unit_price - b.unit_price,
  );

  return {
    line,
    inventory: [
      { label: "Qty on hand", value: line.qty_on_hand, unit: "units" },
      { label: "Open PO", value: line.open_po, unit: "units" },
      { label: "Position", value: line.position, unit: "units" },
      { label: "Reorder point", value: line.rop, unit: "units" },
      { label: "Max", value: line.max, unit: "units" },
      { label: "Demand/day", value: line.demand_per_day, unit: "units" },
    ],
    conversion: [
      { label: "Required (Max − Position)", value: line.required_qty_sales, unit: "sales units" },
      { label: "Order qty (sales)", value: line.order_qty_sales, unit: "sales units" },
      { label: "Pack factor", value: line.pack_factor, unit: `per ${line.buy_uom || "pack"}` },
      { label: "Packs required (exact)", value: line.packs_required_exact, unit: "" },
      { label: "Order qty (buy)", value: line.order_qty_buy, unit: line.buy_uom || "" },
      { label: "Ordered sales units", value: line.ordered_sales_units, unit: "sales units" },
      { label: "Rounding uplift", value: line.rounding_uplift, unit: "sales units" },
    ],
    vendor: {
      designated: line.designated_vendor,
      designated_price: line.unit_price_ta,
      best: line.best_price_vendor,
      best_price: line.best_price,
      saving: line.saving_vs_designated,
      saving_pct: line.saving_pct,
      candidates: quotes,
      terms,
    },
    exceptions: line.exception_codes || [],
    eligibility: line.action_eligibility,
    trace: buildTrace(line),
  };
}

/** Spec section 8.4 — the arithmetic with this line's numbers substituted. */
export function buildTrace(line) {
  const n = (value) =>
    Number(value ?? 0).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const steps = [];

  steps.push(`Position = ${n(line.qty_on_hand)} + ${n(line.open_po)} = ${n(line.position)}.`);
  steps.push(
    line.is_reorder
      ? `Reorder = YES because Position ${n(line.position)} < ROP ${n(line.rop)}.`
      : `Reorder = — because Position ${n(line.position)} is not below ROP ${n(line.rop)}.`,
  );

  if (!line.is_reorder || !line.order_qty_sales) {
    steps.push("No order quantity follows, so there is nothing to convert or price.");
    return steps;
  }

  steps.push(
    `Order qty (sales) = Max ${n(line.max)} − Position ${n(line.position)} = ${n(line.order_qty_sales)}.`,
  );
  if (line.pack_factor > 0) {
    steps.push(
      `Order qty (buy) = CEILING(${n(line.order_qty_sales)} / ${n(line.pack_factor)}) = ` +
        `${n(line.order_qty_buy)} ${line.buy_uom || "packs"}.`,
    );
    steps.push(
      `Ordered sales units = ${n(line.order_qty_buy)} × ${n(line.pack_factor)} = ` +
        `${n(line.ordered_sales_units)} (${n(line.rounding_uplift)} above the requirement).`,
    );
    steps.push(
      `Amount = ${n(line.ordered_sales_units)} × Rp${n(line.unit_price_ta)} = Rp${n(line.amount)}.`,
    );
  }
  steps.push(
    Number(line.saving_vs_designated) > 0
      ? `Saving = ${n(line.ordered_sales_units)} × (Rp${n(line.unit_price_ta)} − Rp${n(line.best_price)}) = Rp${n(line.saving_vs_designated)}.`
      : `Saving = Rp0 — ${line.designated_vendor || "the designated vendor"} already holds the best price.`,
  );
  return steps;
}

/**
 * Shape the API payload into the board's contract. Narrowing happens later.
 *
 * This deliberately does NOT apply the scope. It used to, and that was a bug
 * worth naming: the board then re-narrowed the already-narrowed rows, so the
 * unfiltered population was gone the moment the payload loaded and no filter
 * could ever widen back to it — "All lines" and "No order" both returned
 * nothing, because the rows they wanted had been dropped one layer down.
 *
 * The rule now has one home. This function shapes; `rebuild` in the dashboard
 * narrows. The KPIs and breakdown here describe the whole payload, which is
 * the honest answer to "nothing has been filtered yet".
 */
export function buildDashboardFromRows(payload) {
  const lines = payload.lines || [];

  return {
    schema_version: payload.schema_version,
    agent: payload.agent,
    as_of: payload.generated_at ?? payload.as_of ?? "",
    is_mock: payload.is_mock,
    note: payload.note,
    formulas: payload.formulas ?? {},
    filter_options: {
      ...(payload.filter_options ?? {}),
      ...computeFilterFacets(lines),
    },
    kpis: computeKpis(lines, lines),
    lines,
    by_uom: computeUomBreakdown(lines),
    exception_counts: computeExceptionCounts(lines),
    quotes_by_sku: indexQuotes(payload.quotes),
    quote_terms: payload.quote_terms ?? null,
    vendors: payload.vendors ?? [],
    reference_by_vertical: payload.reference_by_vertical ?? [],
  };
}
