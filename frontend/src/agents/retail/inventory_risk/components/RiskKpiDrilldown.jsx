import DrillDrawer, {
  DrillBars,
  DrillSection,
} from "../../../../components/DrillDrawer.jsx";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { KPI_FORMULAS } from "../data/contract.js";
import { formatDays, formatIdrExact, formatUnits } from "../presentation.js";
import { stateSlug } from "../presentation.js";

/**
 * What one KPI tile is made of (mockup: `openKpiDrill`).
 *
 * Four sections, each answering a question the tile itself cannot: what the
 * formula is, which categories carry it, which stores carry it, and which SKUs
 * are the biggest single contributors.
 *
 * The mockup shows a fifth — a twelve-period history — drawn from a seeded
 * random walk. It is not reproduced. This dataset holds one snapshot per SKU
 * and no date column anywhere, so that chart could only ever be fiction, and
 * an invented trend on a risk board is exactly the thing this module set out
 * not to ship. The section is kept, and says so; it fills in when a dated
 * source lands.
 */
export default function RiskKpiDrilldown({ drilldown, onClose, onSelectSku }) {
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
          {t("across")} {formatUnits(drilldown.sku_count, language)} {t("SKUs in scope")}
        </span>
      </div>

      {formula ? <code className="drill-formula">ƒ {formula}</code> : null}

      {/*
        A mean cannot be split and added back up. Saying so beside the bars
        costs one line and stops a reader summing them against the headline.
      */}
      {drilldown.additive ? null : (
        <p className="drill-warning">
          {t(
            "This metric is an average, so the breakdowns below are each group's own average and do not sum to the headline.",
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

      <DrillSection
        icon="🏪"
        title="This metric by store"
        note={t("Each store's own position, derived per store — not an allocation.")}
      >
        <DrillBars rows={drilldown.by_store} format={format} />
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
                  <span className="drill-sku-right">
                    <span className={`risk-chip risk-chip--${stateSlug(sku.state)}`}>
                      {t(sku.state)}
                    </span>
                    <b>{format(sku.value)}</b>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DrillSection>
    </DrillDrawer>
  );
}

/**
 * Money, days and counts are not interchangeable, and the drawer reuses one
 * bar list for all three — so the unit travels with the metric rather than
 * being guessed from the magnitude.
 */
function formatterFor(unit, language) {
  if (unit === "money") return (value) => formatIdrExact(value, language);
  if (unit === "days") return (value) => `${formatDays(value, language)}d`;
  return (value) => formatUnits(Math.round(value), language);
}
