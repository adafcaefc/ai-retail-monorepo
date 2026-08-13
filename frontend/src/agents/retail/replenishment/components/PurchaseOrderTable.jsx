import { useMemo, useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LINE_FORMULAS, PACK_ROUNDING_NOTE, ROUTE_ORDER } from "../data/contract.js";
import { buildPurchaseOrderCsv, purchaseOrderFilename } from "../data/csv.js";
import { formatIdr, formatIdrExact, formatUnits, routeColor } from "../presentation.js";

const PAGE_SIZE = 40;
const ALL_ROUTES = "all";

/**
 * Hand a CSV to the browser.
 *
 * Guarded rather than assumed: `createObjectURL` is absent under jsdom, and a
 * test that clicks Export should exercise the CSV, not die on a missing DOM
 * API. When it is absent the file is simply not offered — nothing here is the
 * only way to read these numbers.
 */
function download(filename, text) {
  if (typeof URL?.createObjectURL !== "function") return false;

  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

/**
 * A3 spec 5c and 7: the purchase order, split by route.
 *
 * The route bar is section 7's `poTab()` / `buildPOgroups()`. It groups this
 * table only — the route dropdown in the filter bar scopes the whole board, and
 * the two answer different questions: "show me the cross-dock board" against
 * "I am placing the cross-dock order now".
 *
 * Paged rather than scrolled — a purchase order is worked down, and 800 rows in
 * one scroll container loses a reader's place on every re-render.
 *
 * Each numeric column carries its formula on hover. "Position", "ROP" and "Max"
 * mean different things in different retail systems, and the arithmetic that
 * turns a shortfall into whole cases is exactly where a reader stops trusting a
 * screen if it cannot be checked in place.
 */
export default function PurchaseOrderTable({ rows, routes, asOf, onSelect }) {
  const { language, t } = useLanguage();
  const [page, setPage] = useState(0);
  const [tab, setTab] = useState(ALL_ROUTES);

  const grouped = useMemo(() => {
    const groups = new Map(ROUTE_ORDER.map((id) => [id, []]));
    for (const row of rows) {
      if (groups.has(row.route)) groups.get(row.route).push(row);
    }
    return groups;
  }, [rows]);

  const visibleRows = tab === ALL_ROUTES ? rows : (grouped.get(tab) ?? []);

  const pages = Math.max(1, Math.ceil(visibleRows.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const visible = visibleRows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  const totalCost = visibleRows.reduce((running, row) => running + row.order_value_cost, 0);
  const totalSaving = visibleRows.reduce(
    (running, row) => running + row.saving_vs_designated,
    0,
  );

  const routeLabel = (id) => routes?.find((route) => route.id === id)?.label ?? id;

  const tabs = [
    { id: ALL_ROUTES, label: t("All routes"), count: rows.length },
    ...ROUTE_ORDER.map((id) => ({
      id,
      label: t(routeLabel(id)),
      count: grouped.get(id)?.length ?? 0,
    })),
  ];

  function exportRows(scopeId, exportable) {
    download(
      purchaseOrderFilename(scopeId, asOf),
      buildPurchaseOrderCsv(exportable),
    );
  }

  return (
    <section className="po-panel po-order" aria-label={t("Purchase order preview")}>
      <header className="po-panel-head">
        <h3>{t("Purchase order preview")}</h3>
        <span className="po-panel-note">
          {formatUnits(visibleRows.length, language)} {t("lines")} ·{" "}
          {formatIdr(totalCost, language)} {t("at cost")}
          {totalSaving > 0
            ? ` · ${formatIdr(totalSaving, language)} ${t("recoverable")}`
            : ""}
        </span>
      </header>

      <div className="po-routebar" role="tablist" aria-label={t("Purchase order route")}>
        {tabs.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            className={tab === entry.id ? "po-routetab is-active" : "po-routetab"}
            onClick={() => {
              setTab(entry.id);
              setPage(0);
            }}
          >
            {entry.id === ALL_ROUTES ? null : (
              <span
                className="po-routetab-dot"
                style={{ background: routeColor(entry.id) }}
                aria-hidden="true"
              />
            )}
            {entry.label}
            <small>{formatUnits(entry.count, language)}</small>
          </button>
        ))}

        <div className="po-routebar-actions">
          <button
            type="button"
            className="po-button po-button--quiet"
            onClick={() => exportRows(tab, visibleRows)}
            disabled={visibleRows.length === 0}
          >
            {tab === ALL_ROUTES ? t("Export CSV") : t("Export this route")}
          </button>
          {tab === ALL_ROUTES ? null : (
            <button
              type="button"
              className="po-button po-button--quiet"
              onClick={() => exportRows(ALL_ROUTES, rows)}
              disabled={rows.length === 0}
            >
              {t("Export full PO")}
            </button>
          )}
        </div>
      </div>

      {visibleRows.length === 0 ? (
        <p className="po-empty">{t("Nothing needs ordering in the current scope.")}</p>
      ) : (
        <>
          <div className="po-table-scroll">
            <table className="po-table">
              <thead>
                <tr>
                  <th>{t("SKU")}</th>
                  <th className="num" title={LINE_FORMULAS.position}>{t("Position")}</th>
                  <th className="num" title={LINE_FORMULAS.rop}>{t("ROP")}</th>
                  <th className="num" title={LINE_FORMULAS.max}>{t("Max")}</th>
                  <th className="num" title={LINE_FORMULAS.order_qty_sales}>{t("Order")}</th>
                  <th className="num" title={LINE_FORMULAS.order_qty_buy}>{t("Buy")}</th>
                  <th className="num" title={LINE_FORMULAS.order_value_cost}>{t("Line cost")}</th>
                  <th>{t("Vendor")}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr
                    key={row.sku_id}
                    className="po-row"
                    onClick={() => onSelect(row.sku_id)}
                  >
                    <td>
                      <span
                        className="po-row-route"
                        style={{ background: routeColor(row.route) }}
                        title={`+${row.lead_days}d`}
                        aria-hidden="true"
                      />
                      <span className="po-row-name">{row.name}</span>
                      <span className="po-row-meta">
                        {row.sku_id} · {row.category_label}
                      </span>
                    </td>
                    <td className="num" title={LINE_FORMULAS.position}>
                      {formatUnits(row.position, language)}
                    </td>
                    <td className="num" title={LINE_FORMULAS.rop}>
                      {formatUnits(row.rop, language)}
                    </td>
                    <td className="num" title={LINE_FORMULAS.max}>
                      {formatUnits(row.max, language)}
                    </td>
                    <td className="num" title={LINE_FORMULAS.order_qty_sales}>
                      {formatUnits(row.order_qty_sales, language)}
                    </td>
                    <td className="num" title={LINE_FORMULAS.order_qty_buy}>
                      {formatUnits(row.order_qty_buy, language)}
                      <small> {row.buy_uom}</small>
                    </td>
                    <td className="num" title={LINE_FORMULAS.order_value_cost}>
                      {formatIdrExact(row.order_value_cost, language)}
                    </td>
                    <td>
                      <span className="po-vendor">{row.designated_vendor}</span>
                      {row.saving_vs_designated > 0 ? (
                        <span
                          className="po-vendor-switch"
                          title={t("Cheapest quote for this line")}
                        >
                          → {row.best_price_vendor} (
                          {formatIdr(row.saving_vs_designated, language)})
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="po-pager">
            <button
              type="button"
              onClick={() => setPage((value) => Math.max(0, value - 1))}
              disabled={current === 0}
            >
              {t("Previous")}
            </button>
            <span>
              {t("Page")} {current + 1} / {pages}
            </span>
            <button
              type="button"
              onClick={() => setPage((value) => Math.min(pages - 1, value + 1))}
              disabled={current >= pages - 1}
            >
              {t("Next")}
            </button>
          </div>

          <p className="po-panel-caveat">{t(PACK_ROUNDING_NOTE)}</p>
        </>
      )}
    </section>
  );
}
