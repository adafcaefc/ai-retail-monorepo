import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LEVER_DEFINITIONS } from "../data/contract.js";

/**
 * Prints above the KPIs whenever a lever is off baseline, so a reader meets
 * the warning before the number. Matters more here than on the sibling
 * boards: a scenario can change a SKU's delist/grow VERDICT, not just its
 * value, so the counts below are recommendations under an assumption.
 */
export default function AssortmentAppliedScenarioBanner({ levers, onClear }) {
  const { t } = useLanguage();
  const moved = LEVER_DEFINITIONS.filter((l) => Number(levers?.[l.id] ?? 0) !== 0);

  if (moved.length === 0) return null;

  return (
    <div className="assortment-scenario-banner" role="status">
      <span className="assortment-scenario-banner-label">
        {t("Scenario active")} ·{" "}
        {moved.map((l) => `${t(l.label)} ${levers[l.id]}${l.unit}`).join(", ")} ·{" "}
        {t("delist and grow verdicts below are recalculated under this assumption")}
      </span>
      <button type="button" className="assortment-button" onClick={onClear}>
        {t("Back to workbook")}
      </button>
    </div>
  );
}
