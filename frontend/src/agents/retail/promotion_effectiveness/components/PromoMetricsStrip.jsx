import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatIdr, formatPercent, formatRoi, formatUnits } from "../presentation.js";

function formatValue(format, value, language) {
  switch (format) {
    case "idr":
      return formatIdr(value, language);
    case "percent":
      return formatPercent(value / 100, language);
    case "roi":
      return formatRoi(value, language);
    case "units":
    default:
      return formatUnits(value, language);
  }
}

/**
 * A small horizontal strip of labeled figures, each optionally paired with a
 * delta against a baseline. Two call sites, two different spec ids:
 *
 *   #main-stats (A4 spec section 4): PROMO SKUS / UPLIFT / INCR MARGIN / ROI,
 *   no deltas — a snapshot next to the main chart.
 *
 *   #sim-metrics (A4 spec section 9c): INCR MARGIN / ROI / CANNIB / FUNDING,
 *   each with its delta vs baseline once a scenario is applied.
 */
export default function PromoMetricsStrip({ items, testId }) {
  const { t, language } = useLanguage();

  return (
    <div className="promo-metrics-strip" data-testid={testId}>
      {items.map((item) => (
        <div key={item.id} className="promo-metrics-strip-item">
          <span className="promo-metrics-strip-label">{t(item.label)}</span>
          <span className="promo-metrics-strip-value">
            {formatValue(item.format, item.value, language)}
          </span>
          {item.delta != null ? (
            <span
              className={`promo-metrics-strip-delta${
                item.delta === 0 ? "" : item.delta > 0 === !item.lowerIsBetter ? " is-good" : " is-bad"
              }`}
            >
              {item.delta > 0 ? "+" : ""}
              {formatValue(item.format, item.delta, language)}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
