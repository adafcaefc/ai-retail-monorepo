import { useEffect, useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LINE_FORMULAS, PRICE_BASIS_NOTE } from "../data/contract.js";
import { buildDetailCsv, detailFilename } from "../data/csv.js";
import { rowState } from "../data/selectors.js";
import { formatIdr, formatIdrExact, formatRate, formatUnits } from "../presentation.js";

/** Spec section 8.1: 50–100 rows a page. */
const PAGE_SIZE = 50;

/**
 * The nineteen workbook columns, in the sheet's own order.
 *
 * `sticky` marks the three the spec freezes (Item, Item name, Reorder?), and
 * `numeric` right-aligns and enables numeric sorting. `formula` is the per-cell
 * hover text: "Position", "Amount" and "Saving" mean different things in
 * different retail systems, and a reader who cannot check what a column counts
 * will eventually assume the wrong one.
 */
const COLUMNS = [
  { id: "sku_id", label: "Item", sticky: true },
  { id: "name", label: "Item name", sticky: true },
  /*
   * Reorder? sits third, not tenth as the sheet orders it.
   *
   * Spec 8.1 freezes Item, Item name AND Reorder?. Sticky columns only work
   * when they are contiguous — a frozen tenth column detaches and floats over
   * whatever it lands on. Moving the verdict beside the identifier is what
   * makes the freeze implementable, and it is also the column a planner scans
   * first, so it earns the position on its own.
   */
  { id: "is_reorder", label: "Reorder?", sticky: true, kind: "pill" },
  { id: "category_label", label: "Category" },
  { id: "vertical_id", label: "Vertical" },
  { id: "qty_on_hand", label: "Qty on hand", numeric: true },
  { id: "open_po", label: "Open PO", numeric: true },
  { id: "demand_per_day", label: "Demand/day", numeric: true, kind: "rate" },
  { id: "rop", label: "ROP", numeric: true },
  { id: "max", label: "Max", numeric: true },
  { id: "order_qty_sales", label: "Order (sales)", numeric: true },
  { id: "buy_uom", label: "Buy UOM" },
  { id: "order_qty_buy", label: "Order (buy)", numeric: true },
  { id: "designated_vendor", label: "Designated vendor" },
  { id: "unit_price_ta", label: "Unit price (TA)", numeric: true, kind: "idr" },
  { id: "amount", label: "Amount", numeric: true, kind: "idr" },
  { id: "best_price_vendor", label: "Best-price vendor" },
  { id: "best_price", label: "Best price", numeric: true, kind: "idr" },
  { id: "saving_vs_designated", label: "Saving", numeric: true, kind: "idr" },
];

/**
 * Download rows as a file, guarded for jsdom.
 *
 * `URL.createObjectURL` does not exist under the test runner, and a missing
 * method there is not a reason for the export button to throw through the
 * component that rendered it.
 */
function download(text, filename) {
  if (typeof URL?.createObjectURL !== "function") return false;
  const blob = new Blob([text], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

export default function ReplenishmentDetailGrid({
  lines,
  sort,
  onSort,
  onSelect,
  selectedSku,
  scope,
  asOf,
  currency,
}) {
  const { t, language } = useLanguage();
  const [page, setPage] = useState(0);

  // Any change to what is being shown returns to the first page. Staying on
  // page 9 of a result that now has two is how a filter reads as "no rows".
  useEffect(() => {
    setPage(0);
  }, [lines.length, sort?.by, sort?.direction]);

  const pages = Math.max(1, Math.ceil(lines.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const visible = lines.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  return (
    <section className="rdet-grid-panel" data-testid="replenishment-detail-grid">
      <header className="rdet-grid-head">
        <div>
          <h3>{t("Replenishment lines")}</h3>
          <p className="rdet-grid-note">
            {formatUnits(lines.length, language)} {t("lines")} · {PRICE_BASIS_NOTE}
          </p>
        </div>
        <button
          type="button"
          className="rdet-export"
          disabled={!lines.length}
          onClick={() =>
            download(
              buildDetailCsv(lines, currency),
              detailFilename(scope?.legal_entity_id, asOf),
            )
          }
        >
          {t("Export CSV")}
        </button>
      </header>

      <div className="rdet-table-scroll">
        <table className="rdet-table">
          <thead>
            <tr>
              {COLUMNS.map((column) => {
                const active = sort?.by === column.id;
                return (
                  <th
                    key={column.id}
                    className={[
                      column.numeric ? "num" : "",
                      column.sticky ? "sticky" : "",
                      active ? "sorted" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    aria-sort={
                      active
                        ? sort.direction === "asc"
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                  >
                    <button
                      type="button"
                      onClick={() => onSort(column.id)}
                      title={LINE_FORMULAS[column.id] || ""}
                    >
                      {t(column.label)}
                      {active ? (
                        <span aria-hidden="true">
                          {sort.direction === "asc" ? " ▲" : " ▼"}
                        </span>
                      ) : null}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((line) => (
              <tr
                key={line.sku_id}
                className={[
                  `rdet-row-${rowState(line)}`,
                  line.sku_id === selectedSku ? "is-selected" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => onSelect(line)}
                tabIndex={0}
                role="button"
                aria-label={`${line.sku_id} ${line.name}`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(line);
                  }
                }}
              >
                {COLUMNS.map((column) => (
                  <td
                    key={column.id}
                    className={[
                      column.numeric ? "num" : "",
                      column.sticky ? "sticky" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    title={cellTitle(column, line, language)}
                  >
                    {cell(column, line, language, t)}
                  </td>
                ))}
              </tr>
            ))}
            {visible.length ? null : (
              <tr>
                <td colSpan={COLUMNS.length} className="rdet-empty">
                  {t("No lines match these filters.")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 ? (
        <footer className="rdet-pager">
          <button
            type="button"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            {t("Previous")}
          </button>
          <span>
            {t("Page")} {current + 1} / {pages}
          </span>
          <button
            type="button"
            disabled={current >= pages - 1}
            onClick={() => setPage(current + 1)}
          >
            {t("Next")}
          </button>
        </footer>
      ) : null}
    </section>
  );
}

function cell(column, line, language, t) {
  const raw = line[column.id];

  if (column.kind === "pill") {
    return (
      <span className={`rdet-pill rdet-pill-${line.is_reorder ? "yes" : "no"}`}>
        {line.is_reorder ? t("YES") : "—"}
      </span>
    );
  }
  if (column.kind === "idr") return formatIdr(raw, language);
  if (column.kind === "rate") return formatRate(raw, language);
  if (column.numeric) return formatUnits(raw, language);

  // A missing vendor or UOM is an exception the board flags elsewhere; here it
  // should read as absent rather than as an empty cell that looks like a
  // rendering failure.
  if (raw === null || raw === undefined || raw === "") return "—";

  if (column.id === "best_price_vendor" && line.has_alternate_vendor) {
    return <span className="rdet-alt-vendor">{raw}</span>;
  }
  return raw;
}

/** Exact figures on hover, because an abbreviated one cannot be reconciled. */
function cellTitle(column, line, language) {
  if (column.kind === "idr") return formatIdrExact(line[column.id], language);
  if (column.id === "order_qty_buy") {
    return `${formatUnits(line.order_qty_buy, language)} × ${formatUnits(line.pack_factor, language)} = ${formatUnits(line.ordered_sales_units, language)} sales units`;
  }
  if (column.id === "order_qty_sales" && line.rounding_uplift) {
    return `Pack rounding adds ${formatUnits(line.rounding_uplift, language)} sales units`;
  }
  return LINE_FORMULAS[column.id] || "";
}
