import { useLanguage } from "../../../../LanguageProvider.jsx";
import { BASELINE_LEVERS, LEVER_DEFINITIONS } from "../data/contract.js";

/**
 * Prints above the KPIs whenever a lever is off baseline, so a reader meets
 * the warning before the number. Lists the levers that moved and offers a
 * single "Back to workbook" reset.
 *
 * "Off baseline" is per-lever, not "non-zero" -- `markdown` rests at 25
 * (matching the workbook's B6), not 0, so it must be compared against its
 * own BASELINE_LEVERS entry, not a literal 0.
 */
export default function PricingAppliedScenarioBanner({ levers, onClear }) {
  const { t } = useLanguage();
  const moved = LEVER_DEFINITIONS.filter(
    (l) => Number(levers?.[l.id] ?? BASELINE_LEVERS[l.id]) !== BASELINE_LEVERS[l.id],
  );

  if (moved.length === 0) return null;

  return (
    <div className="pricing-scenario-banner" role="status">
      <span className="pricing-scenario-banner-label">
        {t("Scenario active")} ·{" "}
        {moved.map((l) => `${t(l.label)} ${levers[l.id]}${l.unit}`).join(", ")}
      </span>
      <button type="button" className="pricing-button" onClick={onClear}>
        {t("Back to workbook")}
      </button>
    </div>
  );
}
