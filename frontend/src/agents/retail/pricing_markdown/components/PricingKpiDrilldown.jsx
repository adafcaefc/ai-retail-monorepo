import { useLanguage } from "../../../../LanguageProvider.jsx";
import DrillDrawer, { DrillBars, DrillSection } from "../../../../components/DrillDrawer.jsx";
import { formatIdr, formatIndex, formatPercent } from "../presentation.js";

/**
 * The KPI tile drill-down drawer. `history` is always null: the workbook
 * has one snapshot day and no date column, so a trend line would be a
 * fabrication.
 */
export default function PricingKpiDrilldown({ drilldown, onClose, onSelectSku }) {
  const { t, language } = useLanguage();

  if (!drilldown) return null;

  const format = (value) => {
    if (drilldown.unit === "IDR") return formatIdr(value, language);
    // Both stored as whole-number-scale (28.4 -> 28.4%), same convention
    // PricingKpiGrid.jsx's formatValue uses for the headline tile.
    if (drilldown.unit === "percent") return formatPercent(value / 100, language);
    if (drilldown.unit === "index") return formatIndex(value, language);
    return Math.round(Number(value) || 0);
  };

  return (
    <DrillDrawer
      title={drilldown.label}
      subtitle={
        drilldown.formula
          ? `${drilldown.formula} · ${drilldown.additive ? t("additive") : t("mean")}`
          : undefined
      }
      onClose={onClose}
    >
      <DrillSection icon="🗂️" title={t("This metric by category")}>
        <DrillBars rows={drilldown.by_category} format={format} />
      </DrillSection>
      <DrillSection icon="🏬" title={t("This metric by vertical")}>
        <DrillBars rows={drilldown.by_vertical} format={format} />
      </DrillSection>
      <DrillSection icon="📦" title={t("Top contributing SKUs")}>
        {drilldown.top_skus.length === 0 ? (
          <p className="pricing-empty">{t("Nothing in scope.")}</p>
        ) : (
          <ul className="pricing-drill-skus">
            {drilldown.top_skus.map((sku) => (
              <li key={sku.sku_id}>
                <button type="button" onClick={() => onSelectSku(sku.sku_id)}>
                  <span className="pricing-drill-sku-name">{sku.name}</span>
                  <span className="pricing-drill-sku-value">{format(sku.value)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DrillSection>
      <DrillSection icon="📈" title={t("History")}>
        <p className="pricing-empty">
          {t("No history recorded — the workbook carries one snapshot day.")}
        </p>
      </DrillSection>
    </DrillDrawer>
  );
}
