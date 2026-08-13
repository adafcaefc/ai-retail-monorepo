import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatIdr, formatIdrExact, formatUnits } from "../presentation.js";

/**
 * The quotes behind the saving — `Trade Agreement`, on screen at last.
 *
 * `VendorSourcingPanel` beside this one totals what is recoverable per vendor.
 * That total was the whole of what the board could say: a buyer told a line
 * could be Rp 12 m cheaper had no way to see whose price that was, what the
 * minimum break is, or by how much the incumbent is beaten. All 2,400 rows
 * were seeded into Postgres and read by nobody.
 *
 * WHY THE CHEAPEST IS RANKED ON LIST PRICE
 * The discount column is shown and deliberately not applied. The workbook
 * picks its `best_price` on list price, and folding `discount_pct` in would
 * name a different winner on 159 of 800 SKUs — so the panel would contradict
 * the saving printed next to it, with nothing on the board to say which of the
 * two is the answer. The discount is there to be read; the ranking stays on
 * the basis the figure was computed on.
 *
 * A row proposes. It does not place an order: every transactional control on
 * this board is absent rather than disabled, because there is no ERP behind it.
 */
export default function VendorQuotePanel({ sourcing, limit = 8 }) {
  const { language, t } = useLanguage();
  const skus = sourcing?.skus ?? [];

  if (!skus.length) {
    // Not an empty box: "nothing to switch" is a finding, and on a narrow
    // scope it is the likely one.
    return (
      <section className="po-panel po-quotes" aria-label={t("Vendor quotes")}>
        <header className="po-panel-head">
          <h3>{t("Vendor quotes")}</h3>
        </header>
        <p className="po-quotes-empty">
          {sourcing?.on_best_lines
            ? `${formatUnits(sourcing.on_best_lines, language)} ${t(
                "ordered lines are already on the cheapest quote on file.",
              )}`
            : t("No line in this scope has an order to place.")}
        </p>
      </section>
    );
  }

  const shown = skus.slice(0, limit);
  const terms = sourcing.terms;

  return (
    <section className="po-panel po-quotes" aria-label={t("Vendor quotes")}>
      <header className="po-panel-head">
        <h3>{t("Vendor quotes")}</h3>
        <span className="po-panel-note">
          {formatUnits(sourcing.switchable_lines, language)}{" "}
          {t("lines could move to a cheaper vendor")}
          {sourcing.on_best_lines
            ? ` · ${formatUnits(sourcing.on_best_lines, language)} ${t(
                "already on best price",
              )}`
            : ""}
        </span>
      </header>

      {terms ? (
        <p className="po-quotes-terms">
          {t("All quotes")}: {terms.currency} · {t("lead")} {terms.lead_time_days}d ·{" "}
          {t("valid")} {terms.valid_from} → {terms.valid_to}
        </p>
      ) : null}

      <ul className="po-quote-list">
        {shown.map((row) => (
          <li key={row.sku_id}>
            <details>
              <summary>
                <span className="po-quote-sku">
                  <b>{row.name}</b>
                  <small>
                    {row.sku_id} · {row.category_label}
                  </small>
                </span>
                <span className="po-quote-switch">
                  {row.designated_vendor} → <b>{row.best_price_vendor}</b>
                </span>
                <span className="po-quote-saving">
                  −{formatIdr(row.saving, language)}
                </span>
              </summary>

              <p className="po-quote-basis">
                {formatUnits(row.order_qty_buy, language)} {row.buy_uom} ={" "}
                {formatUnits(row.order_units, language)} {t("units on order")} ·{" "}
                {formatIdrExact(row.unit_price_trade - row.best_price, language)}{" "}
                {t("per unit cheaper")}
              </p>

              <table className="po-quote-table">
                <thead>
                  <tr>
                    <th scope="col">{t("Vendor")}</th>
                    <th scope="col">{t("Unit price")}</th>
                    <th scope="col">{t("Min qty")}</th>
                    <th scope="col">{t("Discount")}</th>
                  </tr>
                </thead>
                <tbody>
                  {row.quotes.map((quote) => {
                    const isBest = quote.vendor === row.best_price_vendor;
                    return (
                      <tr
                        key={quote.vendor_account}
                        className={
                          quote.is_designated
                            ? "po-quote-designated"
                            : isBest
                              ? "po-quote-best"
                              : undefined
                        }
                      >
                        <th scope="row">
                          {quote.vendor}
                          {quote.is_designated ? (
                            <span className="po-quote-flag">{t("designated")}</span>
                          ) : null}
                          {isBest && !quote.is_designated ? (
                            <span className="po-quote-flag po-quote-flag--best">
                              {t("cheapest")}
                            </span>
                          ) : null}
                        </th>
                        <td>{formatIdrExact(quote.unit_price, language)}</td>
                        <td>{formatUnits(quote.min_qty_break, language)}</td>
                        {/* Read, never applied — see the note above. */}
                        <td>{quote.discount_pct}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </details>
          </li>
        ))}
      </ul>

      {skus.length > shown.length ? (
        <p className="po-quotes-more">
          {formatUnits(skus.length - shown.length, language)}{" "}
          {t("more lines with a cheaper quote, not shown")}
        </p>
      ) : null}
    </section>
  );
}
