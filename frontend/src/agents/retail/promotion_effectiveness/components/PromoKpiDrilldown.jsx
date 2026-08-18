import { useLanguage } from "../../../../LanguageProvider.jsx";
import DrillDrawer, { DrillBars, DrillSection } from "../../../../components/DrillDrawer.jsx";
import { formatIdr } from "../presentation.js";

/**
 * The KPI tile drill-down drawer. Opens from any tile, decomposes the headline
 * by category, by vertical, and names the top contributing SKUs.
 *
 * `history` is always null: the workbook has one snapshot day and no date
 * column, so a trend line here would be a fabrication. The drawer says so.
 */
export default function PromoKpiDrilldown({ drilldown, onClose, onSelectSku }) {
  const { t, language } = useLanguage();

  if (!drilldown) return null;

  const format = (value) =>
    drilldown.unit === "IDR" ? formatIdr(value, language) : Math.round(Number(value) || 0);

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
          <p className="drill-empty">{t("Nothing in scope.")}</p>
        ) : (
          // Shared with the other retail boards' drilldowns (RiskKpiDrilldown,
          // etc.) — .drill-skus / .drill-sku-name / .drill-sku-right already
          // have global CSS, so this list needs none of its own.
          <ul className="drill-skus">
            {drilldown.top_skus.map((sku) => (
              <li key={sku.sku_id}>
                <button type="button" onClick={() => onSelectSku(sku.sku_id)}>
                  <span className="drill-sku-name">{sku.name}</span>
                  <span className="drill-sku-right">{format(sku.value)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DrillSection>
      <DrillSection icon="📈" title={t("History")}>
        <p className="drill-empty">
          {drilldown.history
            ? null
            : t("No history recorded — the workbook carries one snapshot day.")}
        </p>
      </DrillSection>
    </DrillDrawer>
  );
}
