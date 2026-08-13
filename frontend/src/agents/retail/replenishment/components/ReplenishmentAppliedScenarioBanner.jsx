import { useLanguage } from "../../../../LanguageProvider.jsx";
import { LEVER_DEFINITIONS } from "../data/contract.js";

/**
 * A3 spec section 9b: the board is showing a scenario, not the workbook.
 *
 * Every figure above and below changes when levers drive the whole page, and
 * nothing else on screen would say so. Without this strip a reader could
 * screenshot a simulation and file it as a live purchase order — which on this
 * board is worse than on the other two, because a purchase order is a thing
 * somebody signs.
 *
 * It also names what the levers cannot reach, because a partial simulation that
 * looks total is its own kind of wrong.
 */
export default function ReplenishmentAppliedScenarioBanner({ levers, onClear }) {
  const { t } = useLanguage();

  const moved = LEVER_DEFINITIONS.filter((lever) => levers[lever.id] !== 0);
  if (!moved.length) return null;

  return (
    <div className="po-applied-banner" role="status">
      <span className="po-applied-flag">{t("Scenario")}</span>
      <p>
        <strong>{t("This is a simulated order, not one to send.")}</strong>{" "}
        {moved
          .map(
            (lever) =>
              `${t(lever.label)} ${levers[lever.id] > 0 ? "+" : ""}${levers[lever.id]}${lever.unit}`,
          )
          .join(" · ")}
      </p>
      <span className="po-applied-scope">
        {t("Store and cluster charts stay on the baseline — they arrive pre-aggregated.")}
      </span>
      <button type="button" className="po-button po-button--quiet" onClick={onClear}>
        {t("Back to workbook")}
      </button>
    </div>
  );
}
