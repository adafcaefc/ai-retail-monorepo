import DrillDrawer, {
  DrillBars,
  DrillSection,
} from "../../../../components/DrillDrawer.jsx";
import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

const DEFAULT_HISTORY_NOTE =
  "No history recorded. The source holds a single snapshot per SKU with no date column, so a trend here would be generated rather than measured.";

/**
 * What one A1 KPI tile is made of (mockup: `openKpiDrill`).
 *
 * Non-splittable tiles open to an explanation rather than a breakdown — the
 * alternative is splitting one number across categories and letting the pieces
 * read as findings.
 *
 * The mockup's twelve-period history is a seeded random walk; there is no
 * dated source here, so that section says so.
 */
export default function DemandKpiDrilldown({ drilldown, onClose, onSelectSku }) {
  const { language, t } = useLanguage();
  if (!drilldown) return null;

  const format = formatterFor(drilldown.unit, language);
  const historyNote = drilldown.history_note ?? DEFAULT_HISTORY_NOTE;

  return (
    <DrillDrawer
      title={t(drilldown.label)}
      subtitle={`${t("Current value")}: ${format(drilldown.total)}`}
      onClose={onClose}
    >
      <div className="drill-headline">
        <span className="drill-headline-value">{format(drilldown.total)}</span>
        <span className="drill-headline-sub">
          {t("across")} {formatNumber(drilldown.sku_count, language, {
            maximumFractionDigits: 0,
          })}{" "}
          {t("SKUs in scope")}
        </span>
      </div>

      {drilldown.typed_note ? (
        <>
          <p className="drill-warning">{t(drilldown.typed_note)}</p>
          <DrillSection icon="📈" title="12-period history of this metric">
            <p className="drill-empty">
              {t(historyNote)}
            </p>
          </DrillSection>
        </>
      ) : (
        <>
          <DrillSection icon="📈" title="12-period history of this metric">
            <p className="drill-empty">
              {t(historyNote)}
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
        </>
      )}
    </DrillDrawer>
  );
}

function formatterFor(unit, language) {
  if (unit === "percent") {
    return (value) =>
      `${formatNumber(value, language, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      })}%`;
  }
  return (value) =>
    formatNumber(Math.round(value), language, { maximumFractionDigits: 0 });
}
