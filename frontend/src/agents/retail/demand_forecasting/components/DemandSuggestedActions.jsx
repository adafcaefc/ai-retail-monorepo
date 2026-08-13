import { useState } from "react";

import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

export default function DemandSuggestedActions({ actions }) {
  const { language, t } = useLanguage();
  const [previewOpen, setPreviewOpen] = useState(false);

  return (
    <section className="demand-panel demand-suggested-actions" aria-labelledby="demand-actions-title">
      <header className="demand-panel-head">
        <div>
          <p>{t("Presentational recommendation")}</p>
          <h2 id="demand-actions-title">{t("Suggested Best Action")}</h2>
          <span>{t("Calculated from the current Demand scope · transactions disabled")}</span>
        </div>
        <span className="demand-pending-badge">{t("Backend integration pending")}</span>
      </header>

      <div className="demand-action-grid">
        <article className="demand-action-card demand-action-card--primary">
          <span>{t("Primary")}</span>
          <h3>{t(actions.primary.title)}</h3>
          <p>{t(actions.primary.description)}</p>
          <button type="button" disabled title={t("Backend integration pending")}>{t(actions.primary.action_label)}</button>
        </article>
        <article className="demand-action-card">
          <span>{t("Secondary")}</span>
          <h3>{t(actions.secondary.title)}</h3>
          <p>{t(actions.secondary.description)}</p>
          <button type="button" disabled title={t("Backend integration pending")}>{t(actions.secondary.action_label)}</button>
        </article>
      </div>

      <div className="demand-plan-preview">
        <div>
          <strong>{t(actions.plan_preview.title)}</strong>
          <span>{t(actions.plan_preview.description)}</span>
        </div>
        <button type="button" className="demand-button demand-button--quiet" onClick={() => setPreviewOpen((open) => !open)}>
          {previewOpen ? t("Hide preview") : t("Preview forecast basket")}
        </button>
      </div>

      {previewOpen ? (
        <div className="demand-plan-table">
          <table>
            <thead><tr><th>{t("SKU")}</th><th>{t("Forecast 7d")}</th><th>{t("Signal")}</th><th>{t("Route")}</th></tr></thead>
            <tbody>{actions.plan_preview.rows.map((row) => (
              <tr key={row.sku_id}>
                <td><strong>{row.sku_name}</strong><small>{row.sku_id}</small></td>
                <td>{formatNumber(row.forecast_7d_units, language, { maximumFractionDigits: 0 })}</td>
                <td>{t(row.signal)}</td>
                <td>{t(row.route)}</td>
              </tr>
            ))}</tbody>
          </table>
          <button type="button" className="demand-disabled-transaction" disabled title={t("Backend integration pending")}>{t("Generate forecast basket")}</button>
        </div>
      ) : null}
    </section>
  );
}
