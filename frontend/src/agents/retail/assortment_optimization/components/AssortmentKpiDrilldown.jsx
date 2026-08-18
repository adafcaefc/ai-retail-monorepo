import { useLanguage } from "../../../../LanguageProvider.jsx";
import DrillDrawer, { DrillBars, DrillSection } from "../../../../components/DrillDrawer.jsx";
import { formatGmroi, formatIdr } from "../presentation.js";

/**
 * The KPI tile drill-down drawer.
 *
 * The `additive` subtitle earns its place here: capital freed and
 * contribution/day sum to their headline, but avg GMROI is an
 * inventory-weighted mean whose bars deliberately do not add up.
 *
 * `history` is always null — the workbook carries one snapshot day.
 */
export default function AssortmentKpiDrilldown({ drilldown, onClose, onSelectSku }) {
  const { t, language } = useLanguage();

  if (!drilldown) return null;

  const format = (value) => {
    if (drilldown.unit === "IDR") return formatIdr(value, language);
    if (drilldown.unit === "x") return formatGmroi(value, language);
    return Math.round(Number(value) || 0);
  };

  return (
    <DrillDrawer
      title={drilldown.label}
      subtitle={
        drilldown.formula
          ? `${drilldown.formula} · ${drilldown.additive ? t("additive") : t("weighted mean — bars do not sum to the headline")}`
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
          <p className="assortment-empty">{t("Nothing in scope.")}</p>
        ) : (
          <ul className="assortment-drill-skus">
            {drilldown.top_skus.map((sku) => (
              <li key={sku.sku_id}>
                <button type="button" onClick={() => onSelectSku(sku.sku_id)}>
                  <span className="assortment-drill-sku-name">{sku.name}</span>
                  <span className="assortment-drill-sku-value">{format(sku.value)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DrillSection>
      <DrillSection icon="📈" title={t("History")}>
        <p className="assortment-empty">
          {t("No history recorded — the workbook carries one snapshot day.")}
        </p>
      </DrillSection>
    </DrillDrawer>
  );
}
