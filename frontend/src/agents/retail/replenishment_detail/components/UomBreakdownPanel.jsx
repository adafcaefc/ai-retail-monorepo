import { useLanguage } from "../../../../LanguageProvider.jsx";
import { MIXED_UOM_NOTE } from "../data/contract.js";
import { formatIdr, formatUnits } from "../presentation.js";

/**
 * Buy quantity by UOM — what the KPI strip shows instead of a total.
 *
 * Spec section 7 asks for an "Order qty (buy)" KPI and then warns in the same
 * paragraph that summing across UOMs is operationally weak. This panel is that
 * warning honoured: the quantities are here, each beside the unit that gives
 * it meaning, and no row adds them together.
 *
 * Bars are scaled to the largest row rather than to the total, because the
 * comparison a reader wants is "which unit carries the order", not "what share
 * of a sum that should not exist".
 */
export default function UomBreakdownPanel({ rows, onSelectUom, activeUom }) {
  const { t, language } = useLanguage();
  const peak = Math.max(1, ...rows.map((row) => row.amount));

  return (
    <section className="rdet-uom-panel" data-testid="replenishment-detail-uom">
      <header>
        <h3>{t("Order by buy UOM")}</h3>
        <p className="rdet-grid-note">{MIXED_UOM_NOTE}</p>
      </header>

      {rows.length ? (
        <ul className="rdet-uom-list">
          {rows.map((row) => (
            <li key={row.buy_uom}>
              <button
                type="button"
                className={row.buy_uom === activeUom ? "is-active" : ""}
                onClick={() => onSelectUom(row.buy_uom)}
                title={`${formatUnits(row.ordered_sales_units, language)} ${t("sales units after pack rounding")}`}
              >
                <span className="rdet-uom-name">{row.buy_uom}</span>
                <span className="rdet-uom-qty">
                  {formatUnits(row.order_qty_buy, language)}
                </span>
                <span className="rdet-uom-bar" aria-hidden="true">
                  <i style={{ width: `${(row.amount / peak) * 100}%` }} />
                </span>
                <span className="rdet-uom-amount">
                  {formatIdr(row.amount, language)}
                </span>
                <span className="rdet-uom-lines">
                  {formatUnits(row.line_count, language)} {t("lines")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rdet-empty">{t("No lines match these filters.")}</p>
      )}
    </section>
  );
}
