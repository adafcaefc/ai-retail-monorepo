import { DEFAULT_DEMAND_LEVERS } from "../data/contract.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

function leverValue(lever, value) {
  const sign = ["demand", "inbound", "lead", "safety"].includes(lever.id) && value > 0
    ? "+"
    : "";
  return `${sign}${value}${lever.unit}`;
}

export default function DemandAppliedScenarioBanner({ levers, definitions, onReset }) {
  const { t } = useLanguage();
  const changed = definitions.filter(
    (definition) => levers[definition.id] !== DEFAULT_DEMAND_LEVERS[definition.id],
  );

  if (!changed.length) return null;

  return (
    <div className="demand-scenario-applied" role="status" aria-label={t("What-If scenario applied")}>
      <div>
        <strong>{t("What-If scenario applied")}</strong>
        <span>{changed.map((definition) => (
          `${t(definition.label)} ${leverValue(definition, levers[definition.id])}`
        )).join(" · ")}</span>
      </div>
      <button type="button" onClick={onReset}>{t("Clear applied scenario")}</button>
    </div>
  );
}
