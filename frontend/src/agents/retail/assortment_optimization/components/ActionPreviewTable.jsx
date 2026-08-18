import { useState } from "react";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatGmroi, formatGrowth, formatIdrExact } from "../presentation.js";

const PAGE_SIZE = 12;

/**
 * The Assortment action preview — A6 spec section 5c. Delist candidates
 * first (ranked by capital locked), then grow candidates (ranked by
 * productivity). Hold SKUs are absent by design: they are not an action.
 */
export default function ActionPreviewTable({ rows, onSelect }) {
  const { t, language } = useLanguage();
  const [page, setPage] = useState(0);

  const total = rows.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const start = safePage * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);

  return (
    <section className="assortment-action-preview" data-testid="assortment-action-preview">
      <header className="assortment-section-head">
        <h3>{t("Assortment action preview")}</h3>
        <span className="assortment-section-note">
          {t("Delist and grow candidates only — a hold SKU is not an action.")}
        </span>
      </header>
      {total === 0 ? (
        <p className="assortment-empty">{t("No delist or grow candidates in scope.")}</p>
      ) : (
        <>
          <div className="assortment-table-scroll">
            <table className="assortment-table">
              <thead>
                <tr>
                  <th>{t("SKU")}</th>
                  <th>{t("Category")}</th>
                  <th>{t("Vendor")}</th>
                  <th>{t("Brand")}</th>
                  <th>{t("State")}</th>
                  <th>{t("GMROI")}</th>
                  <th>{t("Contribution/day")}</th>
                  <th>{t("Inventory value")}</th>
                  <th>{t("Growth")}</th>
                  <th>{t("Action")}</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r) => (
                  <tr
                    key={r.sku_id}
                    className="assortment-action-row"
                    onClick={() => onSelect?.(r.sku_id)}
                  >
                    <td>{r.sku_id}</td>
                    <td>{r.category_label}</td>
                    <td>{r.vendor}</td>
                    <td>{r.brand}</td>
                    <td>{t(r.state)}</td>
                    <td>{formatGmroi(r.gmroi, language)}</td>
                    <td>{formatIdrExact(r.contribution_per_day, language)}</td>
                    <td>{formatIdrExact(r.inv_value, language)}</td>
                    <td>{formatGrowth(r.growth, language)}</td>
                    <td>
                      <span className={`assortment-verdict-badge assortment-verdict-${r.classification}`}>
                        {t(r.recommendation)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="assortment-table-pager">
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
