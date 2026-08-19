import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import ForecastLineChart from "./ForecastLineChart.jsx";

const GRAIN_LABELS = {
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  yearly: "Yearly",
};

function SummaryValue({ item, language }) {
  if (typeof item.value === "string") return item.value;
  const digits = ["accuracy", "trend"].includes(item.id) ? 1 : 0;
  const prefix = item.id === "trend" && item.value > 0 ? "+" : "";
  return `${prefix}${formatNumber(item.value, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}${item.unit === "%" ? "%" : ""}`;
}

export default function ForecastOverviewPanel({ forecast, grains, onGrainChange }) {
  const { language, t } = useLanguage();
  return (
    <section className="demand-panel demand-overview-panel" aria-labelledby="demand-overview-title">
      <header className="demand-panel-head demand-panel-head--wrap">
        <div>
          <p>{t("Demand outlook")}</p>
          <h2 id="demand-overview-title">{t("Demand forecast — actual vs AI")}</h2>
          <span>{t(forecast.horizon_label)}</span>
          {forecast.history_count > 0 ? (
            <small className="demand-history-caveat">{t("Illustrative history — not real transaction data")}</small>
          ) : null}
        </div>
        <div className="demand-period-selector" aria-label={t("Forecast period")}>
          {grains.map((grain) => (
            <button
              key={grain}
              type="button"
              aria-pressed={forecast.grain === grain}
              onClick={() => onGrainChange(grain)}
            >
              {t(GRAIN_LABELS[grain])}
            </button>
          ))}
        </div>
      </header>
      <ForecastLineChart points={forecast.points} ariaLabel={t("Demand forecast overview chart")} />
      <div className="demand-summary-strip">
        {forecast.summary.map((item) => (
          <div key={item.id}>
            <span>{t(item.label)}</span>
            <strong><SummaryValue item={item} language={language} /></strong>
            {item.unit && item.unit !== "%" ? <small>{t(item.unit)}</small> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
