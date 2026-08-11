import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

function Sparkline({ values }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 100;
    const y = 22 - ((value - min) / range) * 18;
    return `${x},${y}`;
  });
  const area = `0,24 ${points.join(" ")} 100,24`;

  return (
    <svg className="demand-kpi-spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
      <polygon points={area} />
      <polyline points={points.join(" ")} />
    </svg>
  );
}

function displayValue(kpi, language) {
  const digits = ["forecast_accuracy", "demand_trend"].includes(kpi.id) ? 1 : 0;
  const prefix = kpi.id === "demand_trend" && kpi.value > 0 ? "+" : "";
  const value = formatNumber(kpi.value, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${prefix}${value}${kpi.unit === "%" ? "%" : ""}`;
}

export default function DemandKpiGrid({ kpis }) {
  const { language, t } = useLanguage();

  return (
    <section className="demand-kpi-grid" aria-label={t("Demand forecast summary") }>
      {kpis.map((kpi) => (
        <article key={kpi.id} className={`demand-kpi demand-kpi--${kpi.status}`}>
          <div className="demand-kpi-label">{t(kpi.label)}</div>
          <div className="demand-kpi-value">
            {displayValue(kpi, language)}
            {kpi.unit && kpi.unit !== "%" ? <small>{t(kpi.unit)}</small> : null}
          </div>
          <div className="demand-kpi-comparison">{t(kpi.comparison_label)}</div>
          <Sparkline values={kpi.sparkline} />
        </article>
      ))}
    </section>
  );
}
