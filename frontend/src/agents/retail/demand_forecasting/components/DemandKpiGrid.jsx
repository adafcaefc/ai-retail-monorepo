import KpiSparkline from "../../../../components/KpiSparkline.jsx";
import { formatNumber } from "../../../../format.js";
import { useLanguage } from "../../../../LanguageProvider.jsx";

function displayValue(kpi, language) {
  if (kpi.value == null) {
    return "—";
  }
  const digits = ["forecast_accuracy", "demand_trend"].includes(kpi.id) ? 1 : 0;
  const prefix = kpi.id === "demand_trend" && kpi.value > 0 ? "+" : "";
  const value = formatNumber(kpi.value, language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${prefix}${value}${kpi.unit === "%" ? "%" : ""}`;
}

// Stockout-risk SKUs is the one tile A1 doesn't own the story for: A2
// (Inventory Risk) is where a reader acts on it, matching the mockup's own
// `nav("a2")` on this tile. Every other tile opens its own decomposition
// in place. The app has no router -- navigation is `activeAgent` state in
// App.jsx, reached by a real `#pageId` hash link (see `pages/excelAddress.js`)
// -- so this is a genuine <a href>, not a button with a side effect.
const CROSS_AGENT_LINKS = {
  stockout_risk_skus: "retail.inventory_risk",
};

export default function DemandKpiGrid({ kpis, onOpenDrilldown }) {
  const { language, t } = useLanguage();

  return (
    <section className="demand-kpi-grid" aria-label={t("Demand forecast summary") }>
      {kpis.map((kpi) => {
        const crossAgentId = CROSS_AGENT_LINKS[kpi.id];
        const Tile = crossAgentId ? "a" : "button";
        const tileProps = crossAgentId
          ? { href: `#${crossAgentId}`, title: t("Open in Inventory Risk") }
          : {
              type: "button",
              title: t("Click to break this number down"),
              onClick: () => onOpenDrilldown?.(kpi.id),
            };

        return (
        <Tile
          key={kpi.id}
          className={`demand-kpi demand-kpi--${kpi.status}`}
          {...tileProps}
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
        </Tile>
        );
      })}
    </section>
  );
}
