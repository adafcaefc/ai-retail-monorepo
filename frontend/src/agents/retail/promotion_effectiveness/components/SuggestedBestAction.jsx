import { useMemo, useState } from "react";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { BEST_ACTION_TABS } from "../data/contract.js";
import { buildCampaignsCsv, campaignsFilename } from "../data/csv.js";
import { formatPercent, formatUnits } from "../presentation.js";

/**
 * Hand a CSV to the browser. Guarded rather than assumed: `createObjectURL`
 * is absent under jsdom, and a test that clicks Export should exercise the
 * CSV, not die on a missing DOM API.
 */
function download(filename, text) {
  if (typeof URL?.createObjectURL !== "function") return false;

  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

/**
 * The tabbed promo plan approval panel — A4 spec section 7. Three tabs:
 * High ROI (approve), Funding Gap (renegotiate funding), Pre-buy Required
 * (trigger A3). The recommendation on each campaign is resolved upstream by
 * the promoClassify rule, never re-decided here.
 *
 * This panel is a proposal: it does not submit a D365 discount or raise a
 * pre-buy. It surfaces the decision the reader faces, grouped for approval.
 *
 * `exportPromoPlan(k)` / `exportPromoAll()` (spec section 7): "Export this
 * tab" downloads the active tab's rows, "Export all campaigns" downloads
 * every campaign regardless of tab.
 *
 * The Cannib column has no per-campaign source: `promotion_detail` carries
 * no cannibalization field (only per-SKU items do — see contract.js's
 * TWO UPLIFTS note for the same kind of grain mismatch). Rather than
 * fabricate a campaign-level figure, this shows each campaign's VERTICAL
 * average cannib % (`reference_by_vertical`, already fetched for the KPI
 * cards) and labels the column accordingly.
 */
export default function SuggestedBestAction({ groups, allCampaigns, asOf, referenceByVertical, onSelect }) {
  const { t } = useLanguage();
  const [tab, setTab] = useState(BEST_ACTION_TABS[0].id);
  const active = BEST_ACTION_TABS.find((x) => x.id === tab) ?? BEST_ACTION_TABS[0];
  const rows = groups?.[tab] ?? [];

  const cannibByVertical = useMemo(() => {
    const map = new Map();
    for (const r of referenceByVertical ?? []) {
      map.set(r.legal_entity_id, r.cannib_pct);
    }
    return map;
  }, [referenceByVertical]);

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
        <div className="promo-tabbar-actions">
          <button
            type="button"
            className="promo-button promo-button--quiet"
            onClick={() => download(campaignsFilename(tab, asOf), buildCampaignsCsv(rows))}
            disabled={rows.length === 0}
          >
            {t("Export this tab")}
          </button>
          <button
            type="button"
            className="promo-button promo-button--quiet"
            onClick={() => download(campaignsFilename("all", asOf), buildCampaignsCsv(allCampaigns ?? []))}
            disabled={!allCampaigns?.length}
          >
            {t("Export all campaigns")}
          </button>
        </div>
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
                <th>{t("Type")}</th>
                <th>{t("Vertical")}</th>
                <th>{t("Category")}</th>
                <th>{t("Uplift %")}</th>
                <th>{t("Funding %")}</th>
                <th title={t("Vertical average, not campaign-specific — promotion_detail carries no per-campaign cannibalization field")}>
                  {t("Cannib % (vertical avg)")}
                </th>
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
                  <td>{c.discount_type}</td>
                  <td>{c.vertical_label ?? c.vertical_id}</td>
                  <td>{c.target_category}</td>
                  <td>{formatPercent(c.expected_uplift_pct / 100, "en", { digits: 0 })}</td>
                  <td>{formatPercent(c.supplier_funding_pct / 100, "en", { digits: 0 })}</td>
                  <td>
                    {cannibByVertical.has(c.vertical_id)
                      ? formatPercent(cannibByVertical.get(c.vertical_id) / 100, "en", { digits: 0 })
                      : "—"}
                  </td>
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
