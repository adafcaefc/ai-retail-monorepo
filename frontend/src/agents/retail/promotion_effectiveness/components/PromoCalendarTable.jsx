import { useState } from "react";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatPercent, formatUnits } from "../presentation.js";

const PAGE_SIZE = 12;

/**
 * The Promotion calendar preview — every campaign in scope, sorted by planned
 * uplift then pre-buy units. Carries the D365 construct mapping so a reader can
 * see how a planned discount would land in Commerce.
 *
 * The "Two uplifts" caveat is printed in the header because the expected-uplift
 * column here is the campaign-planned figure, not the modeled net uplift on the
 * cards above.
 */
export default function PromoCalendarTable({ campaigns, onSelect }) {
  const { t } = useLanguage();
  const [page, setPage] = useState(0);

  const total = campaigns.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const start = safePage * PAGE_SIZE;
  const pageRows = campaigns.slice(start, start + PAGE_SIZE);

  return (
    <section className="promo-calendar" data-testid="promo-calendar">
      <header className="promo-section-head">
        <h3>{t("Promotion calendar preview")}</h3>
        <span className="promo-section-note">
          {t("Planned uplift is per-campaign; the card uplift is the modeled net.")}
        </span>
      </header>
      {total === 0 ? (
        <p className="promo-empty">{t("No campaigns in scope.")}</p>
      ) : (
        <>
          <div className="promo-table-scroll">
            <table className="promo-table">
              <thead>
                <tr>
                  <th>{t("Promo ID")}</th>
                  <th>{t("Name")}</th>
                  <th>{t("Type")}</th>
                  <th>{t("Vertical")}</th>
                  <th>{t("Category")}</th>
                  <th>{t("Season")}</th>
                  <th>{t("Disc %")}</th>
                  <th>{t("Funding %")}</th>
                  <th>{t("Uplift %")}</th>
                  <th>{t("Pre-buy")}</th>
                  <th>{t("Valid")}</th>
                  <th>{t("D365 construct")}</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((c) => (
                  <tr
                    key={c.promo_id}
                    className="promo-calendar-row"
                    onClick={() => onSelect?.(c.promo_id)}
                  >
                    <td>{c.promo_id}</td>
                    <td className="promo-cell-name">{c.promo_name}</td>
                    <td>{c.discount_type}</td>
                    <td>{c.vertical_label ?? c.vertical_id}</td>
                    <td>{c.target_category}</td>
                    <td>{c.season}</td>
                    <td>{c.discount_pct == null ? "—" : formatPercent(c.discount_pct / 100, "en", { digits: 0 })}</td>
                    <td>{formatPercent(c.supplier_funding_pct / 100, "en", { digits: 0 })}</td>
                    <td>{formatPercent(c.expected_uplift_pct / 100, "en", { digits: 0 })}</td>
                    <td>{formatUnits(c.pre_buy_uplift_units, "en")}</td>
                    <td>{`${c.valid_from ?? ""} → ${c.valid_to ?? ""}`}</td>
                    <td className="promo-cell-construct">{c.d365_construct}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="promo-table-pager">
            <span>
              {t("Page")} {safePage + 1} / {pageCount}
            </span>
            <button
              type="button"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
            >
              {t("Prev")}
            </button>
            <button
              type="button"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage(safePage + 1)}
            >
              {t("Next")}
            </button>
          </footer>
        </>
      )}
    </section>
  );
}
