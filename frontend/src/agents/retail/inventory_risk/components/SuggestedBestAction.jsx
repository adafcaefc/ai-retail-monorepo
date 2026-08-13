import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatIdr, formatUnits, stateSlug } from "../presentation.js";

/**
 * Suggested Best Action (A2 spec section 1 point 8).
 *
 * Inventory Risk diagnoses; it does not fix. Every problem it finds belongs to
 * another agent — Stockout and Low are a replenishment call (Agent 3),
 * Expiry, Overstock and Slow-mover are a markdown call (Agent 5). This panel
 * is that hand-off made explicit, sized so a reader can see which route is the
 * bigger decision today rather than inferring it from a table of 800 rows.
 *
 * It deliberately routes rather than acts: nothing here claims a purchase
 * order or a markdown has been raised, because none has.
 */
export default function SuggestedBestAction({ routes, onSelect }) {
  const { language, t } = useLanguage();

  if (!routes.length) {
    return (
      <section className="risk-panel" aria-label={t("Suggested best action")}>
        <header className="risk-panel-head">
          <h3>{t("Suggested best action")}</h3>
        </header>
        <p className="risk-empty">{t("Nothing needs action in the current scope.")}</p>
      </section>
    );
  }

  return (
    <section className="risk-panel risk-actions" aria-label={t("Suggested best action")}>
      <header className="risk-panel-head">
        <h3>{t("Suggested best action")}</h3>
        <span className="risk-panel-note">{t("Routed to the owning agent")}</span>
      </header>

      <div className="risk-action-grid">
        {routes.map((route) => (
          <article key={route.next_agent} className="risk-action">
            <div className="risk-action-head">
              <span className="risk-action-route">→ {t(route.next_agent)}</span>
              <span className="risk-action-value">
                {formatIdr(route.value, language)}
              </span>
            </div>

            <div className="risk-action-meta">
              {formatUnits(route.sku_count, language)} {t("SKUs")}
              {" · "}
              {route.states.map((state) => (
                <span
                  key={state}
                  className={`risk-chip risk-chip--${stateSlug(state)}`}
                >
                  {t(state)}
                </span>
              ))}
            </div>

            <ul className="risk-action-list">
              {route.top_skus.map((sku) => (
                <li key={sku.sku_id}>
                  <button type="button" onClick={() => onSelect(sku.sku_id)}>
                    <span className="risk-action-sku-name">{sku.name}</span>
                    <span className="risk-action-sku-id">{sku.sku_id}</span>
                    <span className="risk-action-sku-value">
                      {formatIdr(sku.value, language)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
