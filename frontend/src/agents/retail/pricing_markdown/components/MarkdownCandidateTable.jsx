import { useState } from "react";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatIdrExact, formatUnits } from "../presentation.js";

const PAGE_SIZE = 12;

/**
 * The Markdown candidate preview — every SKU in scope with at least one
 * store in Expiry, Overstock or Slow-mover, sorted by at-risk value desc.
 */
export default function MarkdownCandidateTable({ candidates, onSelect }) {
  const { t, language } = useLanguage();
  const [page, setPage] = useState(0);

  const total = candidates.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const start = safePage * PAGE_SIZE;
  const pageRows = candidates.slice(start, start + PAGE_SIZE);

  return (
    <section className="pricing-candidates" data-testid="pricing-candidates">
      <header className="pricing-section-head">
        <h3>{t("Markdown candidate preview")}</h3>
        <span className="pricing-section-note">
          {t("Expiry, Overstock and Slow-mover SKUs only — Stockout/Low belong to Agent 3.")}
        </span>
      </header>
      {total === 0 ? (
        <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>
      ) : (
        <>
          <div className="pricing-table-scroll">
            <table className="pricing-table">
              <thead>
                <tr>
                  <th>{t("SKU")}</th>
                  <th>{t("Category")}</th>
                  <th>{t("State")}</th>
                  <th>{t("Position")}</th>
                  <th>{t("DoS")}</th>
                  <th>{t("Price")}</th>
                  <th>{t("At-risk value")}</th>
                  <th>{t("Recoverable")}</th>
                  <th>{t("Write-off")}</th>
                  <th>{t("Vendor")}</th>
                  <th>{t("Brand")}</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((c) => (
                  <tr key={c.sku_id} className="pricing-candidate-row" onClick={() => onSelect?.(c.sku_id)}>
                    <td>{c.sku_id}</td>
                    <td>{c.category_label}</td>
                    <td>
                      <span className={`pricing-state-badge pricing-state-${c.state.toLowerCase()}`}>
                        {t(c.state)}
                      </span>
                    </td>
                    <td>{formatUnits(c.position, language)}</td>
                    <td>{c.dos}</td>
                    <td>{formatIdrExact(c.price, language)}</td>
                    <td>{formatIdrExact(c.at_risk_value, language)}</td>
                    <td>{formatIdrExact(c.recoverable_value, language)}</td>
                    <td>{formatIdrExact(c.write_off_value, language)}</td>
                    <td>{c.vendor}</td>
                    <td>{c.brand}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="pricing-table-pager">
            <span>
              {t("Page")} {safePage + 1} / {pageCount}
            </span>
            <button type="button" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
              {t("Prev")}
            </button>
            <button type="button" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>
              {t("Next")}
            </button>
          </footer>
        </>
      )}
    </section>
  );
}
