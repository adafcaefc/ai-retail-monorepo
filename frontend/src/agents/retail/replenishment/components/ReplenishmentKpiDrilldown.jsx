import DrillDrawer, {
  DrillBars,
  DrillSection,
} from "../../../../components/DrillDrawer.jsx";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { KPI_FORMULAS } from "../data/contract.js";
import {
  formatIdrExact,
  formatPercent,
  formatUnits,
} from "../presentation.js";

/**
 * What one A3 KPI tile is made of (mockup: `openKpiDrill`).
 *
 * The mockup's twelve-period history is a seeded random walk and its per-store
 * panel is a `charCodeAt` allocation. Neither is reproduced: this dataset has
 * no dated source, and A3's real per-store columns are used where they exist.
 * Where they do not — cost, fill rate, vendor saving — the section names the
 * reason rather than inventing a split.
 */
export default function ReplenishmentKpiDrilldown({
  drilldown,
  onClose,
  onSelectSku,
}) {
  const { language, t } = useLanguage();
  if (!drilldown) return null;

  const format = formatterFor(drilldown.unit, language);
  const formula = KPI_FORMULAS[drilldown.id];

  return (
    <DrillDrawer
      title={t(drilldown.label)}
      subtitle={`${t("Current value")}: ${format(drilldown.total)}`}
      onClose={onClose}
    >
      <div className="drill-headline">
        <span className="drill-headline-value">{format(drilldown.total)}</span>
        <span className="drill-headline-sub">
          {t("across")} {formatUnits(drilldown.line_count, language)}{" "}
          {t("order lines in scope")}
        </span>
      </div>

      {formula ? <code className="drill-formula">ƒ {formula}</code> : null}

      {drilldown.additive ? null : (
        <p className="drill-warning">
          {t(
            "This metric is a rate, so the breakdowns below are each group's own rate and do not sum to the headline.",
          )}
        </p>
      )}

      <DrillSection icon="📈" title="12-period history of this metric">
        <p className="drill-empty">
          {t(
            "No history recorded. The source holds a single snapshot per SKU with no date column, so a trend here would be generated rather than measured.",
          )}
        </p>
      </DrillSection>

      <DrillSection icon="🗂️" title="This metric by category">
        <DrillBars rows={drilldown.by_category} format={format} />
      </DrillSection>

      <DrillSection icon="🏪" title="This metric by store">
        {drilldown.store_unavailable_reason ? (
          <p className="drill-empty">{t(drilldown.store_unavailable_reason)}</p>
        ) : (
          <DrillBars rows={drilldown.by_store} format={format} />
        )}
      </DrillSection>

      <DrillSection icon="🔎" title="Top contributing SKUs">
        {drilldown.top_skus.length === 0 ? (
          <p className="drill-empty">{t("Nothing in scope.")}</p>
        ) : (
          <ul className="drill-skus">
            {drilldown.top_skus.map((sku) => (
              <li key={sku.id}>
                <button
                  type="button"
                  onClick={() => onSelectSku?.(sku.id)}
                  title={t("Filter the board to this SKU")}
                >
                  <span className="drill-sku-name">
                    <b>{sku.name}</b>
                    <small>
                      {sku.id} · {sku.category_name}
                    </small>
                  </span>
                  <b>{format(sku.value)}</b>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DrillSection>
    </DrillDrawer>
  );
}

function formatterFor(unit, language) {
  if (unit === "money") return (value) => formatIdrExact(value, language);
  if (unit === "percent") return (value) => formatPercent(value, language);
  return (value) => formatUnits(Math.round(value), language);
}
