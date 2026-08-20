import { useLanguage } from "../../../../LanguageProvider.jsx";
import ForecastLineChart from "./ForecastLineChart.jsx";

export default function ForecastConfidencePanel({ confidence }) {
  const { t } = useLanguage();
  return (
    <section className="demand-panel demand-confidence-panel" aria-labelledby="demand-confidence-title">
      <header className="demand-panel-head">
        <div>
          <p>{t("Forecast confidence")}</p>
          <h2 id="demand-confidence-title">{t("Demand forecast · actual vs AI")}</h2>
          <span>{t(confidence.horizon_label)}</span>
        </div>
        <span className="demand-panel-tag">{confidence.horizon_weeks}W</span>
      </header>
      <ForecastLineChart
        points={confidence.points}
        ariaLabel={t("Demand forecast confidence chart")}
        compact
        includeConfidence
      />
    </section>
  );
}
