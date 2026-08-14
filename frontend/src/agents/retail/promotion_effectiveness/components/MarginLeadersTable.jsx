import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatIdr, formatPercent } from "../presentation.js";

/**
 * The promo SKUs carrying the most incremental margin — the "largest margin
 * SKUs" list. One row per promo-eligible SKU, sorted desc by f13 margin.
 */
export default function MarginLeadersTable({ rows, onSelect }) {
  const { t, language } = useLanguage();

  return (
    <section className="promo-leaders" data-testid="promo-leaders">
      <header className="promo-section-head">
        <h3>{t("Promo margin leaders")}</h3>
      </header>
      {rows.length === 0 ? (
        <p className="promo-empty">{t("No promo-eligible SKUs in scope.")}</p>
      ) : (
        <div className="promo-table-scroll">
          <table className="promo-table">
            <thead>
              <tr>
                <th>{t("SKU")}</th>
                <th>{t("Name")}</th>
                <th>{t("Vertical")}</th>
                <th>{t("Category")}</th>
                <th>{t("Incremental margin")}</th>
                <th>{t("Cannib %")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((sku) => (
                <tr key={sku.sku_id} onClick={() => onSelect?.(sku.sku_id)}>
                  <td>{sku.sku_id}</td>
                  <td className="promo-cell-name">{sku.name}</td>
                  <td>{sku.vertical_id}</td>
                  <td>{sku.category_label}</td>
                  <td>{formatIdr(sku.incremental_margin, language)}</td>
                  <td>{formatPercent(sku.cannibalisation_pct / 100, language, { digits: 1 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
