import { useState } from "react";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { BEST_ACTION_TABS } from "../data/contract.js";
import { formatGmroi, formatIdrExact } from "../presentation.js";

/**
 * The tabbed assortment plan panel — A6 spec section 7. Four tabs, a clean
 * partition of the delist + grow population.
 *
 * A6 spec section 11 is explicit that delisting reaches other agents
 * (replenishment, promotion, markdown, vendor commitments), so the panel
 * says out loud that this is a proposal requiring category-manager and
 * vendor review rather than something the board can enact.
 */
export default function SuggestedBestAction({ groups, onSelect }) {
  const { t, language } = useLanguage();
  const [tab, setTab] = useState(null);

  const availableTabs = BEST_ACTION_TABS.filter((x) => (groups?.[x.id]?.length ?? 0) > 0);
  const visibleTabs = availableTabs.length > 0 ? availableTabs : BEST_ACTION_TABS;
  const activeTabId = visibleTabs.some((x) => x.id === tab)
    ? tab
    : (visibleTabs[0]?.id ?? BEST_ACTION_TABS[0].id);

  const active = BEST_ACTION_TABS.find((x) => x.id === activeTabId) ?? BEST_ACTION_TABS[0];
  const rows = groups?.[activeTabId] ?? [];

  return (
    <section className="assortment-best-action" data-testid="assortment-best-action">
      <header className="assortment-section-head">
        <h3>{t("Suggested best action")}</h3>
        <span className="assortment-section-note">
          {t("A proposal. Delisting reaches replenishment, promotion, markdown and vendor commitments — category manager and vendor review apply first.")}
        </span>
      </header>
      <div className="assortment-tabs" role="tablist">
        {visibleTabs.map((x) => (
          <button
            key={x.id}
            type="button"
            role="tab"
            aria-selected={x.id === activeTabId}
            className={`assortment-tab${x.id === activeTabId ? " is-active" : ""}`}
            onClick={() => setTab(x.id)}
          >
            {t(x.label)}
            <span className="assortment-tab-count">{groups?.[x.id]?.length ?? 0}</span>
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="assortment-empty">{t("No SKUs in this group.")}</p>
      ) : (
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
                <th>{t("Recommendation")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sku_id} onClick={() => onSelect?.(r.sku_id)}>
                  <td>{r.sku_id}</td>
                  <td>{r.category_label}</td>
                  <td>{r.vendor}</td>
                  <td>{r.brand}</td>
                  <td>{t(r.state)}</td>
                  <td>{formatGmroi(r.gmroi, language)}</td>
                  <td>{formatIdrExact(r.contribution_per_day, language)}</td>
                  <td>{formatIdrExact(r.inv_value, language)}</td>
                  <td className="assortment-cell-recommendation">{t(active.recommendation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
