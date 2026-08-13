import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatIdr, formatPercent, formatUnits } from "../presentation.js";

/**
 * A3 spec section 7's sourcing half: where the money goes, and where it could.
 *
 * The `saving` column is `Replenishment Detail!saving_vs_designated`, the
 * workbook's own comparison between the designated trade agreement and the
 * cheapest quote on file. It is the one number on this board that proposes
 * something, so it is shown per vendor rather than only as a chain total —
 * a saving nobody can attribute is a saving nobody can act on.
 *
 * The panel routes. It does not place an order: every transactional control on
 * this board is absent rather than disabled, because there is no ERP behind it.
 */
export default function VendorSourcingPanel({ split, vendors }) {
  const { language, t } = useLanguage();
  if (!split.length) return null;

  const scorecard = new Map(vendors.map((vendor) => [vendor.vendor, vendor]));
  const total = split.reduce((running, row) => running + row.saving, 0);

  return (
    <section className="po-panel po-sourcing" aria-label={t("Vendor sourcing")}>
      <header className="po-panel-head">
        <h3>{t("Vendor sourcing")}</h3>
        <span className="po-panel-note">
          {total > 0
            ? `${formatIdr(total, language)} ${t("recoverable across all vendors")}`
            : t("Every line is already on its cheapest quote")}
        </span>
      </header>

      <ul className="po-vendor-list">
        {split.map((row) => {
          const vendor = scorecard.get(row.vendor);
          return (
            <li key={row.vendor}>
              <div className="po-vendor-head">
                <strong>{row.vendor}</strong>
                {vendor ? (
                  <span className="po-vendor-terms">
                    {t("OTIF")} {formatPercent(vendor.otif_pct, language)} ·{" "}
                    {t("lead")} {vendor.lead_time_days}d · {vendor.payment_terms}
                  </span>
                ) : null}
              </div>
              <div className="po-vendor-figures">
                <span>
                  {formatUnits(row.line_count, language)} {t("lines")}
                </span>
                <span>{formatIdr(row.order_value_cost, language)}</span>
                {row.saving > 0 ? (
                  <span className="po-vendor-saving">
                    −{formatIdr(row.saving, language)} {t("if switched")} (
                    {formatUnits(row.switchable_lines, language)} {t("lines")})
                  </span>
                ) : (
                  <span className="po-vendor-best">{t("cheapest on file")}</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
