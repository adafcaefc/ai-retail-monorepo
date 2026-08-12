import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LEVER_DEFINITIONS } from "../data/contract.js";

/**
 * A2 spec section 8b: the board is showing a scenario, not the workbook.
 *
 * Every figure above and below changes when levers drive the whole page, and
 * nothing else on screen would say so. Without this strip a reader could take
 * a screenshot of a simulation and file it as the current position — which is
 * the one failure this dashboard cannot afford, given every other number on it
 * reconciles to a real sheet.
 *
 * It also names the two panels the levers cannot reach, because a partial
 * simulation that looks total is its own kind of wrong.
 */
export default function RiskAppliedScenarioBanner({ levers, onClear }) {
  const { t } = useLanguage();

  const moved = LEVER_DEFINITIONS.filter((lever) => levers[lever.id] !== 0);
  if (!moved.length) return null;

  return (
    <div className="risk-applied-banner" role="status">
      <span className="risk-applied-flag">{t("Scenario")}</span>
      <p>
        <strong>{t("These are simulated figures, not the workbook position.")}</strong>{" "}
        {moved
          .map((lever) => `${t(lever.label)} ${levers[lever.id] > 0 ? "+" : ""}${levers[lever.id]}${lever.unit}`)
          .join(" · ")}
      </p>
      <span className="risk-applied-scope">
        {t("Store and cluster charts stay on the baseline — they arrive pre-aggregated.")}
      </span>
      <button type="button" className="risk-button risk-button--quiet" onClick={onClear}>
        {t("Back to workbook")}
      </button>
    </div>
  );
}
