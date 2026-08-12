import { useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LINE_FORMULAS, PACK_ROUNDING_NOTE } from "../data/contract.js";
import { formatIdr, formatIdrExact, formatUnits, routeColor } from "../presentation.js";

const PAGE_SIZE = 40;

/**
 * A3 spec 5c: the purchase order itself.
 *
 * Paged rather than scrolled — a purchase order is worked down, and 800 rows
 * in one scroll container loses a reader's place on every re-render.
 *
 * Each numeric column carries its formula on hover. "Position", "ROP" and
 * "Max" mean different things in different retail systems, and the arithmetic
 * that turns a shortfall into whole cases is exactly where a reader stops
 * trusting a screen if it cannot be checked in place.
 */
export default function PurchaseOrderTable({ rows, onSelect }) {
  const { language, t } = useLanguage();
  const [page, setPage] = useState(0);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const visible = rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  const totalCost = rows.reduce((running, row) => running + row.order_value_cost, 0);
  const totalSaving = rows.reduce(
    (running, row) => running + row.saving_vs_designated,
    0,
  );

  return (
    <section className="po-panel po-order" aria-label={t("Purchase order preview")}>
      <header className="po-panel-head">
        <h3>{t("Purchase order preview")}</h3>
        <span className="po-panel-note">
          {formatUnits(rows.length, language)} {t("lines")} ·{" "}
          {formatIdr(totalCost, language)} {t("at cost")}
          {totalSaving > 0
            ? ` · ${formatIdr(totalSaving, language)} ${t("recoverable")}`
            : ""}
        </span>
      </header>

      {rows.length === 0 ? (
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
