import { useLanguage } from "../../../../LanguageProvider.jsx";
import {
  AT_RISK_VALUE_NOTE,
  DOS_TARGET,
  KPI_FORMULAS,
} from "../data/contract.js";
import {
  formatDays,
  formatIdr,
  formatUnits,
  kpiAccent,
  kpiTone,
} from "../presentation.js";

/**
 * The six A2 KPIs (spec section 3).
 *
 * Each tile carries a count, a money or context line underneath, and the
 * formula behind it on hover — the same three layers the mockup shows through
 * `val` / `sub` / `data-fx`. The money lines are not decoration: overstock and
 * expiry are only actionable once you know what they cost, and a count alone
 * cannot be compared against anything.
 *
 * No sparklines. The workbook carries no date column, so any trend line here
 * would be invented, and an invented trend on a risk board is worse than no
 * trend. They return when daily history does.
 */
export default function RiskKpiGrid({ kpis, onDrillStockoutRisk }) {
  const { language, t } = useLanguage();

  const dosBelow = kpis.avg_dos < DOS_TARGET.min;
  const dosAbove = kpis.avg_dos > DOS_TARGET.max;

  const tiles = [
    {
      id: "stockout_risk_skus",
      label: "Stockout-risk SKUs",
      value: formatUnits(kpis.stockout_risk_skus, language),
      caption: t("Position below reorder point"),
      // The mockup's KPI #1 drills into the at-risk breakdown; here that means
      // scoping the board to the two states that make up the reorder zone.
      onClick: onDrillStockoutRisk,
    },
    {
      id: "overstock_skus",
      label: "Overstock SKUs",
      value: formatUnits(kpis.overstock_skus, language),
      caption: `${formatIdr(kpis.overstock_excess_value, language)} ${t("excess")}`,
      captionTone: kpis.overstock_excess_value > 0 ? "warn" : "",
    },
    {
      id: "expiry_units",
      label: "Expiry-risk units",
      value: formatUnits(Math.round(kpis.expiry_units), language),
      caption: `${formatIdr(kpis.expiry_value, language)} ${t("write-off risk")}`,
      captionTone: kpis.expiry_value > 0 ? "bad" : "",
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
      caption: `${t("target")} ${DOS_TARGET.min}–${DOS_TARGET.max}d`,
      captionTone: dosBelow || dosAbove ? "warn" : "good",
    },
    {
      id: "inventory_value",
      label: "Inventory value",
      value: formatIdr(kpis.inventory_value, language),
      caption: `${t("At risk")}: ${formatIdr(kpis.at_risk_value, language)}`,
      captionNote: t(AT_RISK_VALUE_NOTE),
    },
  ];

  return (
    <section className="risk-kpi-grid" aria-label={t("Inventory risk summary")}>
      {tiles.map((tile) => {
        const formula = KPI_FORMULAS[tile.id];
        const title = [t(tile.label), formula, tile.captionNote]
          .filter(Boolean)
          .join("\n");

        const body = (
          <>
            <div className="risk-kpi-label">{t(tile.label)}</div>
            <div className="risk-kpi-value">{tile.value}</div>
            <div
              className={`risk-kpi-caption${
                tile.captionTone ? ` risk-kpi-caption--${tile.captionTone}` : ""
              }`}
            >
              {tile.caption}
            </div>
          </>
        );

        const style = { "--risk-kpi-accent": kpiAccent(tile.id) };
        const className = `risk-kpi risk-kpi--${kpiTone(tile.id, kpis[tile.id])}`;

        // A tile that filters the board is a button; the rest are not, so a
        // keyboard user is not offered five stops that do nothing.
        return tile.onClick ? (
          <button
            key={tile.id}
            type="button"
            className={`${className} risk-kpi--actionable`}
            style={style}
            title={`${title}\n${t("Click to show only the reorder zone")}`}
            onClick={tile.onClick}
          >
            {body}
          </button>
        ) : (
          <article key={tile.id} className={className} style={style} title={title}>
            {body}
          </article>
        );
      })}
    </section>
  );
}
