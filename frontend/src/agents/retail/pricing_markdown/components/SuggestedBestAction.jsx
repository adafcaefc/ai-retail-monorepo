import { useState } from "react";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { BEST_ACTION_TABS } from "../data/contract.js";
import { formatIdrExact, formatUnits } from "../presentation.js";

/**
 * The tabbed markdown approval panel — A5 spec section 7. A proposal: it
 * does not submit a price change or block a reorder. It surfaces the
 * decision the reader faces, grouped for approval.
 */
export default function SuggestedBestAction({ groups, onSelect }) {
  const { t } = useLanguage();
  const [tab, setTab] = useState(BEST_ACTION_TABS[0].id);
  const active = BEST_ACTION_TABS.find((x) => x.id === tab) ?? BEST_ACTION_TABS[0];
  const rows = groups?.[tab] ?? [];

  return (
    <section className="pricing-best-action" data-testid="pricing-best-action">
      <header className="pricing-section-head">
        <h3>{t("Suggested best action")}</h3>
        <span className="pricing-section-note">
          {t("A proposal. Segregation of authority applies before anything is submitted.")}
        </span>
      </header>
      <div className="pricing-tabs" role="tablist">
        {BEST_ACTION_TABS.map((x) => (
          <button
            key={x.id}
            type="button"
            role="tab"
            aria-selected={x.id === tab}
            className={`pricing-tab${x.id === tab ? " is-active" : ""}`}
            onClick={() => setTab(x.id)}
          >
            {t(x.label)}
            <span className="pricing-tab-count">{groups?.[x.id]?.length ?? 0}</span>
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="pricing-empty">{t("No candidates in this group.")}</p>
      ) : (
        <div className="pricing-table-scroll">
          <table className="pricing-table">
            <thead>
              <tr>
                <th>{t("SKU")}</th>
                <th>{t("Store")}</th>
                <th>{t("Category")}</th>
                <th>{t("State")}</th>
                <th>{t("Position")}</th>
                <th>{t("At-risk value")}</th>
                <th>{t("Recoverable")}</th>
                <th>{t("Write-off")}</th>
                <th>{t("Recommendation")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={`${c.sku_id}-${c.store_id}`} onClick={() => onSelect?.(c.sku_id)}>
                  <td>{c.sku_id}</td>
                  <td>{c.store_id}</td>
                  <td>{c.category_label}</td>
                  <td>{t(c.state)}</td>
                  <td>{formatUnits(c.position, "en")}</td>
                  <td>{formatIdrExact(c.at_risk_value, "en")}</td>
                  <td>{formatIdrExact(c.recoverable_value, "en")}</td>
                  <td>{formatIdrExact(c.at_risk_value - c.recoverable_value, "en")}</td>
                  <td className="pricing-cell-recommendation">{t(active.recommendation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
