import { useState } from "react";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { BEST_ACTION_TABS } from "../data/contract.js";
import { formatPercent, formatUnits } from "../presentation.js";

/**
 * The tabbed promo plan approval panel — A4 spec section 7. Three tabs:
 * High ROI (approve), Funding Gap (renegotiate funding), Pre-buy Required
 * (trigger A3). The recommendation on each campaign is resolved upstream by
 * the promoClassify rule, never re-decided here.
 *
 * This panel is a proposal: it does not submit a D365 discount or raise a
 * pre-buy. It surfaces the decision the reader faces, grouped for approval.
 */
export default function SuggestedBestAction({ groups, onSelect }) {
  const { t } = useLanguage();
  const [tab, setTab] = useState(BEST_ACTION_TABS[0].id);
  const active = BEST_ACTION_TABS.find((x) => x.id === tab) ?? BEST_ACTION_TABS[0];
  const rows = groups?.[tab] ?? [];

  return (
    <section className="promo-best-action" data-testid="promo-best-action">
      <header className="promo-section-head">
        <h3>{t("Suggested best action")}</h3>
        <span className="promo-section-note">
          {t("A proposal. Segregation of authority applies before anything is submitted.")}
        </span>
      </header>
      <div className="promo-tabs" role="tablist">
        {BEST_ACTION_TABS.map((x) => (
          <button
            key={x.id}
            type="button"
            role="tab"
            aria-selected={x.id === tab}
            className={`promo-tab${x.id === tab ? " is-active" : ""}`}
            onClick={() => setTab(x.id)}
          >
            {t(x.label)}
            <span className="promo-tab-count">{groups?.[x.id]?.length ?? 0}</span>
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="promo-empty">{t("No campaigns in this group.")}</p>
      ) : (
        <div className="promo-table-scroll">
          <table className="promo-table">
            <thead>
              <tr>
                <th>{t("Promo ID")}</th>
                <th>{t("Name")}</th>
                <th>{t("Vertical")}</th>
                <th>{t("Uplift %")}</th>
                <th>{t("Funding %")}</th>
                <th>{t("Pre-buy")}</th>
                <th>{t("D365 construct")}</th>
                <th>{t("Recommendation")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.promo_id} onClick={() => onSelect?.(c.promo_id)}>
                  <td>{c.promo_id}</td>
                  <td className="promo-cell-name">{c.promo_name}</td>
                  <td>{c.vertical_label ?? c.vertical_id}</td>
                  <td>{formatPercent(c.expected_uplift_pct / 100, "en", { digits: 0 })}</td>
                  <td>{formatPercent(c.supplier_funding_pct / 100, "en", { digits: 0 })}</td>
                  <td>{formatUnits(c.pre_buy_uplift_units, "en")}</td>
                  <td className="promo-cell-construct">{c.d365_construct}</td>
                  <td className="promo-cell-recommendation">{t(active.recommendation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
