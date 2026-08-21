import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { categoryColor, formatIdr, formatPercent, formatUnits } from "../presentation.js";

/** Active bar stays at full opacity; the rest dim, so a selection reads at a glance. */
function cellOpacity(key, activeKey) {
  return !activeKey || key === activeKey ? 1 : 0.35;
}

/**
 * Incremental margin by vertical (vertical bars) — the by-vertical chart from
 * the A4 spec section 5a. Sorted desc by margin, value labels on. Click a bar
 * to scope the board to that vertical, matching inventory_risk's dimension
 * charts — the only two clicked-to-filter charts on this board are this one
 * and the by-category chart below, both of which already have a dropdown
 * filter for the same field.
 */
export function MarginByVerticalChart({ rows, onSelect, activeKey }) {
  const { t, language } = useLanguage();
  const data = [...rows]
    .filter((r) => r.incremental_margin > 0)
    .sort((a, b) => b.incremental_margin - a.incremental_margin)
    .map((r) => ({
      label: r.label ?? r.vertical_id,
      value: r.incremental_margin,
      selection_key: r.vertical_id,
    }));

  if (!data.length) return <p className="promo-empty">{t("No promo margin in scope.")}</p>;

  return (
    <section className="promo-chart-block" data-testid="promo-chart-vertical">
      <h4>{t("Incremental margin by vertical")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar
            dataKey="value"
            name={t("Incremental margin")}
            onClick={onSelect ? (point) => onSelect(point.selection_key) : undefined}
            cursor={onSelect ? "pointer" : undefined}
          >
            {data.map((row, i) => (
              <Cell
                key={row.selection_key}
                fill={categoryColor(i)}
                fillOpacity={cellOpacity(row.selection_key, activeKey)}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * Incremental margin by category (horizontal bars) — the by-category dimension
 * chart from the A4 spec section 6. Click a bar to scope the board to that
 * category.
 */
export function MarginByCategoryChart({ rows, onSelect, activeKey }) {
  const { t, language } = useLanguage();
  const data = [...rows]
    .sort((a, b) => b.value - a.value)
    .slice(0, 8)
    .map((row) => ({ ...row, selection_key: row.category_id }));

  if (!data.length) return <p className="promo-empty">{t("No promo margin in scope.")}</p>;

  return (
    <section className="promo-chart-block" data-testid="promo-chart-category">
      <h4>{t("Incremental margin by category")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart layout="vertical" data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar
            dataKey="value"
            name={t("Incremental margin")}
            onClick={onSelect ? (point) => onSelect(point.selection_key) : undefined}
            cursor={onSelect ? "pointer" : undefined}
          >
            {data.map((row, i) => (
              <Cell
                key={row.selection_key}
                fill={categoryColor(i)}
                fillOpacity={cellOpacity(row.selection_key, activeKey)}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * Incremental margin by channel (horizontal bars, sorted desc) — A4 spec
 * section 5b. Reconciles exactly to the chain-net headline (see
 * `selectors.js`'s `computeByChannel`), unlike a physical inventory position.
 */
export function MarginByChannelChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows].filter((r) => r.incremental_margin > 0);

  if (!data.length) return <p className="promo-empty">{t("No promo margin in scope.")}</p>;

  return (
    <section className="promo-chart-block" data-testid="promo-chart-channel">
      <h4>{t("Incremental margin by channel")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart layout="vertical" data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar dataKey="incremental_margin" name={t("Incremental margin")}>
            {data.map((row, i) => (
              <Cell key={row.label} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * Incremental margin by store (horizontal bars, top 12) — A4 spec section 6.
 * A proportional split of each item's own margin by store size (see
 * `computeByStore`), not a re-measurement, so it reconciles exactly to the
 * chain-net headline.
 */
const TOP_STORES = 12;

export function MarginByStoreChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows].slice(0, TOP_STORES);

  if (!data.length) return <p className="promo-empty">{t("No promo margin in scope.")}</p>;

  return (
    <section className="promo-chart-block" data-testid="promo-chart-store">
      <h4>
        {t("Incremental margin by store")}
        <span className="promo-section-note">{t("Top 12")}</span>
      </h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart layout="vertical" data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar dataKey="incremental_margin" name={t("Incremental margin")}>
            {data.map((row, i) => (
              <Cell key={row.store_id} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * Incremental margin by store cluster (vertical bars with value labels) — A4
 * spec section 6.
 */
export function MarginByClusterChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows];

  if (!data.length) return <p className="promo-empty">{t("No promo margin in scope.")}</p>;

  return (
    <section className="promo-chart-block" data-testid="promo-chart-cluster">
      <h4>{t("Incremental margin by cluster")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 20, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar dataKey="incremental_margin" name={t("Incremental margin")} label={{ position: "top", fontSize: 10, formatter: (v) => formatIdr(v, language) }}>
            {data.map((row, i) => (
              <Cell key={row.label} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * Inventory value by state — A4 spec section 6's inventory-state-exposure
 * chart. Deliberately titled and measured differently from every other chart
 * here: this is inventory value, NOT incremental margin, and the spec's own
 * section 11 warns it should not be reconciled against the margin headline —
 * state is unrelated to the store-size proportionality every margin chart
 * on this board relies on.
 */
export function InventoryStateChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows];

  if (!data.length) return <p className="promo-empty">{t("No promo-eligible inventory in scope.")}</p>;

  return (
    <section className="promo-chart-block" data-testid="promo-chart-state">
      <h4 title={t("Inventory value by state — not incremental margin, and not reconciled to it.")}>
        {t("Inventory value by state")}
      </h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="state" tick={{ fontSize: 11 }} tickFormatter={(v) => t(v)} />
          <YAxis tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} labelFormatter={(v) => t(v)} />
          <Bar dataKey="value" name={t("Inventory value")}>
            {data.map((row, i) => (
              <Cell key={row.state} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * Campaign mix by season (stacked bars of pre-buy units per discount type) —
 * the stacked dimension chart from the A4 spec section 6.
 *
 * Recharts reads both the axis domain and the stack off the chart-level
 * `data`, so every discount type needs its own numeric key on the row. Keeping
 * the nested `segments` array as the `dataKey` and handing each Bar a private
 * `data` prop instead does not work: the domain comes out non-numeric, the
 * axis falls back to 0–4, `stackId` is ignored, and all eleven series are
 * drawn full-height on the same x band, overdrawing one another.
 */
export function SeasonMixChart({ rows }) {
  const { t, language } = useLanguage();
  const discountTypes = [
    ...new Set(rows.flatMap((r) => r.segments.map((s) => s.discount_type))),
  ];
  const data = rows.map((r) => {
    const point = { season: r.season };
    for (const type of discountTypes) {
      point[type] = r.segments.find((s) => s.discount_type === type)?.value ?? 0;
    }
    return point;
  });

  if (!rows.length) return <p className="promo-empty">{t("No campaigns in scope.")}</p>;

  return (
    <section className="promo-chart-block" data-testid="promo-chart-season">
      <h4>{t("Campaign mix by season (pre-buy units)")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="season" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatUnits(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatUnits(v, language)} />
          <Legend />
          {discountTypes.map((type, i) => (
            <Bar
              key={type}
              dataKey={type}
              name={type}
              stackId="a"
              fill={categoryColor(i)}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

function DemandUpliftTooltip({ active, payload, label }) {
  const { t, language } = useLanguage();
  if (!active || !payload?.length) return null;

  const point = payload[0].payload;

  return (
    <div className="promo-chart-tooltip">
      <strong>{label}</strong>
      <span>
        {t("Baseline")}: {formatUnits(Math.round(point.baseline), language)}
      </span>
      {point.with_promo !== null ? (
        <span>
          {t("With promo")}: {formatUnits(Math.round(point.with_promo), language)}
        </span>
      ) : null}
      <em>ƒ promo = baseline × (1 + uplift)</em>
    </div>
  );
}

/**
 * Baseline vs promo demand — replaces the "uplift vs margin quality" combo
 * chart. Two weekly demand curves, `weeks_back`/`weeks_forward` either side of
 * a "Today" divider: `demand` is `dashboard.demand_uplift`, built by
 * `computeDemandUplift` in `data/selectors.js` from whichever items the active
 * scope narrowed to, so the Vertical/Category/Store/SKU filters and the
 * What-If levers all reach this chart the same way they reach every other one
 * on this board — no filter wiring of its own.
 *
 * `Baseline` is Replenishment's own real weekly curve for these SKUs, not a
 * flat estimate (see `computeDemandUplift`'s doc for the join). `With promo`
 * is null before Today, so the two lines read as one shared curve up to the
 * divider instead of drawing an identical line twice, then bridges at Today
 * and runs dashed to the horizon.
 *
 * The y-axis is framed on the data rather than anchored at zero, exactly as
 * `RequirementVsInboundPanel` frames its own — both series move within a
 * narrow band relative to their own size, and a zero-anchored axis would
 * spend most of its height on empty space below the lines and flatten the
 * real week-to-week movement into a couple of pixels.
 */
export function PromoDemandUpliftChart({ demand }) {
  const { t, language } = useLanguage();

  if (!demand?.points?.length) {
    return <p className="promo-empty">{t("No promo demand in scope.")}</p>;
  }

  const plotted = demand.points.flatMap((point) =>
    [point.baseline, point.with_promo].filter((value) => typeof value === "number"),
  );
  const low = plotted.length ? Math.min(...plotted) : 0;
  const high = plotted.length ? Math.max(...plotted) : 0;
  const padding = (high - low) * 0.2 || high * 0.05 || 1;
  const domain = [Math.max(0, low - padding), high + padding];

  return (
    <section className="promo-chart-block" data-testid="promo-chart-main">
      <h4>{t("Baseline vs promo demand")}</h4>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={demand.points} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={6} />
          <YAxis
            domain={domain}
            tickFormatter={(v) => formatUnits(v, language)}
            tick={{ fontSize: 11 }}
            width={56}
          />
          <Tooltip content={<DemandUpliftTooltip />} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <ReferenceLine x="Today" stroke="var(--line)" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="baseline"
            name={t("Baseline")}
            stroke="var(--gray-500, var(--muted))"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="with_promo"
            name={t("With promo")}
            stroke="var(--success)"
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}
