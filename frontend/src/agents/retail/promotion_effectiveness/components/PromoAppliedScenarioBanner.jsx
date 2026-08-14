import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LEVER_DEFINITIONS } from "../data/contract.js";

/**
 * Prints above the KPIs whenever a lever is off baseline, so a reader scrolling
 * to a number meets the warning before the number. Lists the levers that moved
 * and offers a single "Back to workbook" reset.
 */
export default function PromoAppliedScenarioBanner({ levers, onClear }) {
  const { t } = useLanguage();
  const moved = LEVER_DEFINITIONS.filter((l) => Number(levers?.[l.id] ?? 0) !== 0);

  if (moved.length === 0) return null;

  return (
    <div className="promo-scenario-banner" role="status">
      <span className="promo-scenario-banner-label">
        {t("Scenario active")} ·{" "}
        {moved.map((l) => `${t(l.label)} ${levers[l.id]}${l.unit}`).join(", ")}
      </span>
      <button type="button" className="promo-button" onClick={onClear}>
        {t("Back to workbook")}
      </button>
    </div>
  );
}
