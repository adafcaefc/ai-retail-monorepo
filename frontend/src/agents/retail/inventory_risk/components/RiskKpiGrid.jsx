import KpiSparkline from "../../../../components/KpiSparkline.jsx";
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
 * The mini-charts are DISTRIBUTIONS, never trends. There is still no date
 * column in this workbook, so the original note here was right that a trend
 * line would have to be invented — but a histogram of the rows behind the
 * number needs no dates at all, and says something the figure cannot: whether
 * the count is concentrated or spread. Each carries a caption naming its axis,
 * so nothing reads as time. See `computeKpiSparklines`.
 */
export default function RiskKpiGrid({
  kpis,
  sparklines = {},
  onDrillStockoutRisk,
  onOpenDrilldown,
}) {
  const { language, t } = useLanguage();

  const dosBelow = kpis.avg_dos < DOS_TARGET.min;
  const dosAbove = kpis.avg_dos > DOS_TARGET.max;

  const tiles = [
    // Every count below is DISTINCT SKUs over the ENGINE_STORE grid, which is
    // what the workbook's own dropdown reports. A SKU in trouble at six stores
    // is one SKU here, six rows in the register beneath.
    {
      // `Position < ROP`, the same predicate Replenishment's
      // `skus_to_reorder` and Demand Forecasting's `stockout_risk_skus` tile
      // count, so the three boards read the same number for "at stockout
      // risk". The narrower Stockout-state-alone count (`stockout_skus`)
      // still exists as data for the risk register's state filter, but is not
      // this tile.
      id: "stockout_risk_skus",
      label: "Stockout-risk SKUs",
      value: formatUnits(kpis.stockout_risk_skus, language),
      caption: `${formatIdr(kpis.stockout_risk_value, language)} ${t("at risk")}`,
      captionTone: kpis.stockout_risk_skus > 0 ? "bad" : "",
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
        const spark = sparklines[tile.id];
        const title = [t(tile.label), formula, spark?.caption, tile.captionNote]
          .filter(Boolean)
          .join("\n");

        const body = (
          <>
            <div className="risk-kpi-text">
              <div className="risk-kpi-label">{t(tile.label)}</div>
              <div className="risk-kpi-value">{tile.value}</div>
              <div
                className={`risk-kpi-caption${
                  tile.captionTone ? ` risk-kpi-caption--${tile.captionTone}` : ""
                }`}
              >
                {tile.caption}
              </div>
            </div>
            {/*
              Beside the figure, as the mockup places it, so the tile reads as
              one object rather than a number with a footnote. The axis name
              moves into the tooltip rather than vanishing: these are
              distributions, and a reader who assumed a trend would be reading
              a shape that says nothing about time.
            */}
            {spark?.values?.length ? (
              <div className="risk-kpi-spark" title={t(spark.caption)}>
                <KpiSparkline values={spark.values} kind={spark.kind} />
              </div>
            ) : null}
          </>
        );

        const style = { "--risk-kpi-accent": kpiAccent(tile.id) };
        const className = `risk-kpi risk-kpi--${kpiTone(tile.id, kpis[tile.id])}`;

        /*
         * Every tile now opens its own decomposition, so every tile is a
         * button — the earlier split (one actionable tile, five inert
         * articles) existed only because five of them had nothing to show.
         *
         * The stockout tile keeps its second, stronger action: a separate
         * control scopes the board to the reorder zone. Opening a drawer and
         * filtering the whole board are different intents and a reader should
         * not have to guess which a click will do.
         */
        return (
          <article key={tile.id} className={className} style={style}>
            <button
              type="button"
              className="risk-kpi-open"
              title={`${title}\n${t("Click to break this number down")}`}
              onClick={() => onOpenDrilldown?.(tile.id)}
            >
              {body}
            </button>
            {tile.onClick ? (
              <button
                type="button"
                className="risk-kpi-scope"
                onClick={tile.onClick}
              >
                {t("Show only the reorder zone")}
              </button>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
