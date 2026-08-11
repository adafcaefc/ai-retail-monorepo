import { useState } from "react";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { REGISTER_FORMULAS } from "../data/contract.js";
import {
  formatDays,
  formatIdrExact,
  formatUnits,
  stateSlug,
} from "../presentation.js";

/**
 * The register is already severity-sorted by the selectors, and the whole
 * chain is only 800 rows, so this pages client-side rather than asking the
 * provider for a window. When the API owns the real dataset it should page
 * server-side and this becomes an offset the query carries.
 */
const PAGE_SIZE = 50;

/**
 * A2 spec section 5c. Every SKU, worst state first, then by value.
 *
 * The tooltips on Position, ROP and DoS carry their formula because the same
 * three words mean different things in different retail systems, and a reader
 * who cannot see the definition tends to assume the wrong one.
 */
export default function RiskRegisterTable({ rows, onSelect }) {
  const { language, t } = useLanguage();
  const [page, setPage] = useState(0);

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const visible = rows.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE);

  if (!rows.length) {
    return (
      <section className="risk-panel" aria-label={t("Inventory risk register")}>
        <header className="risk-panel-head">
          <h3>{t("Inventory risk register")}</h3>
        </header>
        <p className="risk-empty">{t("No SKUs match the current scope.")}</p>
      </section>
    );
  }

  return (
    <section className="risk-panel risk-register" aria-label={t("Inventory risk register")}>
      <header className="risk-panel-head">
        <h3>{t("Inventory risk register")}</h3>
        <span className="risk-panel-note">
          {formatUnits(rows.length, language)} {t("SKUs")}
        </span>
      </header>

      <div className="risk-table-scroll">
        <table className="risk-table">
          <thead>
            <tr>
              <th scope="col">{t("SKU")}</th>
              <th scope="col">{t("State")}</th>
              <th scope="col" className="num">{t("On-hand")}</th>
              <th scope="col" className="num">{t("Open PO")}</th>
              <th scope="col" className="num" title={t("Position = On-hand + Open PO")}>
                {t("Position")}
              </th>
              <th scope="col" className="num" title={t("ROP = ADS × (Lead + Safety)")}>
                {t("ROP")}
              </th>
              <th scope="col" className="num" title={t("DoS = Position ÷ ADS")}>
                {t("DoS")}
              </th>
              <th scope="col" className="num" title={t("Value = Position × price")}>
                {t("Value")}
              </th>
              <th scope="col">{t("Next agent")}</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr
                key={row.sku_id}
                className={`risk-row risk-row--${stateSlug(row.state)}`}
                onClick={() => onSelect(row.sku_id)}
                tabIndex={0}
                role="button"
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.sku_id);
                  }
                }}
              >
                <td>
                  {/* Name first: a reader scanning for a product recognises it
                      by name, and the code is the lookup key underneath. */}
                  <span className="risk-sku-name-primary">{row.name}</span>
                  <span className="risk-sku-meta">
                    {row.sku_id} · {row.category_name}
                  </span>
                </td>
                <td>
                  <span className={`risk-chip risk-chip--${stateSlug(row.state)}`}>
                    {t(row.state)}
                  </span>
                </td>
                {/* Each figure carries its own formula, not just the header, so
                    the definition is reachable wherever the eye lands. */}
                <td className="num" title={t(REGISTER_FORMULAS.on_hand)}>
                  {formatUnits(row.on_hand, language)}
                </td>
                <td className="num" title={t(REGISTER_FORMULAS.open_po)}>
                  {formatUnits(row.open_po, language)}
                </td>
                <td className="num" title={t(REGISTER_FORMULAS.position)}>
                  <b>{formatUnits(row.position, language)}</b>
                </td>
                <td className="num" title={t(REGISTER_FORMULAS.rop)}>
                  {formatUnits(row.rop, language)}
                </td>
                <td className="num" title={t(REGISTER_FORMULAS.dos)}>
                  {formatDays(row.dos, language)}
                </td>
                <td className="num" title={t(REGISTER_FORMULAS.inv_value)}>
                  {formatIdrExact(row.inv_value, language)}
                </td>
                <td className="risk-next-agent">→ {t(row.next_agent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 ? (
        <div className="risk-pager">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            disabled={current === 0}
          >
            {t("Previous")}
          </button>
          <span>
            {t("Page")} {current + 1} / {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
            disabled={current >= pageCount - 1}
          >
            {t("Next")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
