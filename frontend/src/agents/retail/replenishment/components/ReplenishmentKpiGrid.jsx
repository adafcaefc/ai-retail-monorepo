import KpiSparkline from "../../../../components/KpiSparkline.jsx";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { KPI_FORMULAS } from "../data/contract.js";
import {
  formatDays,
  formatIdr,
  formatPercent,
  formatUnits,
} from "../presentation.js";

/**
 * A3 spec section 3, plus the one figure the spec leaves out.
 *
 * `Order value` is a single tile, not two: `ENGINE_STORE!Y` (`Order value`),
 * the A3 tab's own `Order value` column, and its per-vertical reconciliation
 * all price the shortfall at selling price and hold no trade-agreement price
 * anywhere in the engine. A cost-basis figure is real and useful — it prices
 * the purchase order line by line elsewhere on this board — but the workbook
 * never states a second *headline* order value to stand beside it, so this
 * grid does not invent one.
 *
 * `Recoverable` is the only tile that proposes something rather than reporting
 * a state: what the same purchase order would cost at each line's cheapest
 * quoted vendor instead of its designated one.
 */
export default function ReplenishmentKpiGrid({
  kpis,
  sparklines = {},
  onDrillReorder,
  onOpenDrilldown,
}) {
  const { language, t } = useLanguage();

  const tiles = [
    {
      id: "skus_to_reorder",
      label: "SKUs to reorder",
      value: formatUnits(kpis.skus_to_reorder, language),
      tone: kpis.skus_to_reorder ? "warn" : "good",
      drill: true,
    },
    {
      id: "order_units",
      label: "Order units",
      value: formatUnits(kpis.order_units, language),
      sub: t("sales units"),
    },
    {
      id: "order_value_retail",
      label: "Order value",
      value: formatIdr(kpis.order_value_retail, language),
      sub: t("purchase plan"),
      tone: "warn",
    },
    {
      id: "fill_rate_pct",
      label: "Fill rate",
      value: formatPercent(kpis.fill_rate_pct, language),
      sub: `${t("cover")} ${formatDays(kpis.avg_cover_days, language)}`,
      tone: kpis.fill_rate_pct >= 60 ? "good" : "warn",
    },
    {
      id: "recoverable_saving",
      label: "Recoverable",
      value: formatIdr(kpis.recoverable_saving, language),
      sub: t("by switching vendor"),
      tone: kpis.recoverable_saving > 0 ? "good" : "neutral",
    },
  ];

  return (
    <section className="po-kpi-grid" aria-label={t("Replenishment summary")}>
      {tiles.map((tile) => (
        /*
         * Every tile opens its own decomposition, so the tile face is always a
         * button. The reorder tile keeps its second, stronger action as a
         * separate control: opening a drawer and re-scoping the whole board
         * are different intents, and one click cannot mean both.
         */
        <article
          key={tile.id}
          className={`po-kpi po-kpi--${tile.tone || "neutral"}`}
        >
          <button
            type="button"
            className="po-kpi-open"
            title={[
              KPI_FORMULAS[tile.id],
              sparklines[tile.id] ? t(sparklines[tile.id].caption) : null,
              t("Click to break this number down"),
            ]
              .filter(Boolean)
              .join("\n")}
            onClick={() => onOpenDrilldown?.(tile.id)}
          >
            <span className="po-kpi-text">
              <span className="po-kpi-label">{t(tile.label)}</span>
              <strong className="po-kpi-value">{tile.value}</strong>
              {tile.sub ? <small className="po-kpi-sub">{tile.sub}</small> : null}
            </span>
            {/* Beside the figure, as the mockup places it. The axis name lives
                in the tile tooltip, so a distribution is never mistaken for a
                trend. */}
            {sparklines[tile.id]?.values?.length ? (
              <span className="po-kpi-spark">
                <KpiSparkline
                  values={sparklines[tile.id].values}
                  kind={sparklines[tile.id].kind}
                />
              </span>
            ) : null}
          </button>
          {tile.drill && onDrillReorder ? (
            <button type="button" className="po-kpi-scope" onClick={onDrillReorder}>
              {t("Show only lines to reorder")}
            </button>
          ) : null}
        </article>
      ))}
    </section>
  );
}
