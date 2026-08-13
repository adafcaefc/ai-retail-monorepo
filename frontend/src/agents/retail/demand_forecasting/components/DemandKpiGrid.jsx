import KpiSparkline from "../../../../components/KpiSparkline.jsx";
import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

function displayValue(kpi, language) {
  const digits = ["forecast_accuracy", "demand_trend"].includes(kpi.id) ? 1 : 0;
  const prefix = kpi.id === "demand_trend" && kpi.value > 0 ? "+" : "";
  const value = formatNumber(kpi.value, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${prefix}${value}${kpi.unit === "%" ? "%" : ""}`;
}

export default function DemandKpiGrid({ kpis, onOpenDrilldown }) {
  const { language, t } = useLanguage();

  return (
    <section className="demand-kpi-grid" aria-label={t("Demand forecast summary") }>
      {kpis.map((kpi) => (
        /* Every tile opens its own decomposition, so the tile face is a
           button. A1 has no second per-tile action, so unlike A2 and A3 there
           is no scope pill beside it. */
        <button
          key={kpi.id}
          type="button"
          className={`demand-kpi demand-kpi--${kpi.status}`}
          title={t("Click to break this number down")}
          onClick={() => onOpenDrilldown?.(kpi.id)}
        >
          <div className="demand-kpi-text">
            <div className="demand-kpi-label">{t(kpi.label)}</div>
            <div className="demand-kpi-value">
              {displayValue(kpi, language)}
              {kpi.unit && kpi.unit !== "%" ? <small>{t(kpi.unit)}</small> : null}
            </div>
            <div className="demand-kpi-comparison">{t(kpi.comparison_label)}</div>
          </div>
          {/*
            A histogram, not a trend, wherever no real series exists. Three of
            these tiles are typed constants and none of the six has a dated
            source, so those show how the number is SPREAD — which needs no
            history at all. The axis name sits in the tooltip so the shape is
            never read as movement over time.
          */}
          {kpi.sparkline?.length ? (
            <div
              className="demand-kpi-spark-wrap"
              title={kpi.sparkline_caption ? t(kpi.sparkline_caption) : undefined}
            >
              <KpiSparkline
                values={kpi.sparkline}
                kind={kpi.sparkline_kind ?? "series"}
              />
            </div>
          ) : null}
        </button>
      ))}
    </section>
  );
}
