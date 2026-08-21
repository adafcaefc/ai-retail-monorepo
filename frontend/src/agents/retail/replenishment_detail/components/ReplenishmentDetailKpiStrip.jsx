import { useLanguage } from "../../../../LanguageProvider.jsx";
import { KPI_FORMULAS, MIXED_UOM_NOTE } from "../data/contract.js";
import {
  formatIdr,
  formatIdrExact,
  formatUnits,
  kpiAccent,
} from "../presentation.js";

/**
 * The six KPIs of spec section 7.
 *
 * The third tile is the interesting one. The spec lists "Order qty (buy)" as a
 * KPI and then, in the same section, warns that summing Crates, Cartons and
 * Pallets "produces a mathematically valid count but a weak operational KPI".
 * So the tile reports how many distinct buy UOMs the order spans, with the
 * breakdown panel below it, rather than showing a total nobody can act on.
 * That is the spec's own recommendation followed rather than its table copied.
 */
const TILES = [
  { id: "reorder_sku_count", label: "Reorder SKUs", format: "units" },
  { id: "order_qty_sales", label: "Order qty (sales)", format: "units" },
  { id: "buy_uom_count", label: "Order qty (buy)", format: "uom" },
  { id: "purchase_amount", label: "Purchase amount", format: "idr" },
  { id: "potential_saving", label: "Potential saving", format: "idr" },
  { id: "alternate_vendor_count", label: "Alternate-vendor SKUs", format: "units" },
];

export default function ReplenishmentDetailKpiStrip({ kpis, onSelectTile }) {
  const { t, language } = useLanguage();

  return (
    <div className="rdet-kpi-grid" data-testid="replenishment-detail-kpis">
      {TILES.map((tile) => (
        <button
          key={tile.id}
          type="button"
          className="rdet-kpi"
          style={{ "--rdet-kpi-accent": kpiAccent(tile.id) }}
          title={tooltip(tile, kpis, language, t)}
          onClick={() => onSelectTile(tile.id)}
        >
          <span className="rdet-kpi-label">{t(tile.label)}</span>
          <span className="rdet-kpi-value">
            {value(tile, kpis, language, t)}
          </span>
        </button>
      ))}
    </div>
  );
}

function value(tile, kpis, language, t) {
  const raw = kpis[tile.id] ?? 0;
  if (tile.format === "idr") return formatIdr(raw, language);
  if (tile.format === "uom") return formatUnits(raw, language);
  return formatUnits(raw, language);
}

function tooltip(tile, kpis, language, t) {
  const lines = [KPI_FORMULAS[tile.id]];
  if (tile.id === "buy_uom_count") lines.push(MIXED_UOM_NOTE);
  if (tile.id === "purchase_amount") {
    lines.push(`${t("Exact")}: ${formatIdrExact(kpis.purchase_amount, language)}`);
  }
  if (tile.id === "potential_saving") {
    lines.push(`${t("Exact")}: ${formatIdrExact(kpis.potential_saving, language)}`);
  }
  lines.push(t("Click to filter the grid to this."));
  return lines.filter(Boolean).join("\n");
}
