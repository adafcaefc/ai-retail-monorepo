import { useLanguage } from "../../../../LanguageProvider.jsx";
import { AT_RISK_VALUE_NOTE } from "../data/contract.js";
import {
  formatDays,
  formatIdr,
  formatUnits,
  kpiTone,
} from "../presentation.js";

/**
 * The six A2 KPIs (spec section 3), plus slow-movers and at-risk value.
 *
 * No sparklines. The workbook carries no date column, so any trend line here
 * would be invented — and an invented trend on a risk board is worse than no
 * trend. They return when the daily history does.
 */
export default function RiskKpiGrid({ kpis }) {
  const { language, t } = useLanguage();

  const tiles = [
    {
      id: "stockout_risk_skus",
      label: "Stockout-risk SKUs",
      value: formatUnits(kpis.stockout_risk_skus, language),
      caption: t("Position below reorder point"),
    },
    {
      id: "overstock_skus",
      label: "Overstock SKUs",
      value: formatUnits(kpis.overstock_skus, language),
      caption: t("Days of supply above 15"),
    },
    {
      id: "expiry_units",
      label: "Expiry-risk units",
      value: formatUnits(Math.round(kpis.expiry_units), language),
      caption: t("Units beyond shelf-life cover"),
    },
    {
      id: "slow_mover_skus",
      label: "Slow-moving SKUs",
      value: formatUnits(kpis.slow_mover_skus, language),
      caption: t("Declining growth, high cover"),
    },
    {
      id: "avg_dos",
      label: "Avg days of supply",
      value: `${formatDays(kpis.avg_dos, language)}d`,
      caption: t("Mean position ÷ ADS"),
    },
    {
      id: "inventory_value",
      label: "Inventory value",
      value: formatIdr(kpis.inventory_value, language),
      caption: `${t("At risk")}: ${formatIdr(kpis.at_risk_value, language)}`,
      title: t(AT_RISK_VALUE_NOTE),
    },
  ];

  return (
    <section className="risk-kpi-grid" aria-label={t("Inventory risk summary")}>
      {tiles.map((tile) => (
        <article
          key={tile.id}
          className={`risk-kpi risk-kpi--${kpiTone(tile.id, kpis[tile.id])}`}
          title={tile.title}
        >
          <div className="risk-kpi-label">{t(tile.label)}</div>
          <div className="risk-kpi-value">{tile.value}</div>
          <div className="risk-kpi-caption">{tile.caption}</div>
        </article>
      ))}
    </section>
  );
}
