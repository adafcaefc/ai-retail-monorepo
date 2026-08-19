import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import {
  categoryColor,
  classificationColor,
  formatGmroi,
  formatGrowth,
  formatIdr,
  formatUnits,
} from "../presentation.js";

const VERDICTS = [
  { id: "delist", label: "Delist" },
  { id: "hold", label: "Hold" },
  { id: "grow", label: "Grow" },
];

function QuadrantTooltip({ active, payload }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="assortment-chart-tooltip">
      <strong>{p.sku_id} · {p.name}</strong>
      <span>{t("Category")}: {p.category_label}</span>
      <span>{t("GMROI")}: {formatGmroi(p.gmroi, language)}</span>
      <span>{t("Growth")}: {formatGrowth(p.growth, language)}</span>
      <span>{t("Inventory value")}: {formatIdr(p.inv_value, language)}</span>
      <span>{t("Contribution/day")}: {formatIdr(p.contribution_per_day, language)}</span>
      <span className="assortment-tooltip-total">{t("Verdict")}: {t(p.classification)}</span>
    </div>
  );
}

/**
 * "Delist vs grow opportunity" — the main chart, A6 spec section 4.
 * GMROI on x, growth on y, inventory value as bubble size, verdict as
 * colour. The reference lines are the cutoffs the verdict actually used, so
 * a reader can see why a point landed where it did rather than taking the
 * colour on trust.
 */
export function DelistVsGrowQuadrant({ points, thresholds, onSelectSku }) {
  const { t, language } = useLanguage();

  if (!points.length) {
    return <p className="assortment-empty">{t("No SKUs in scope.")}</p>;
  }

  const series = VERDICTS.map((v) => ({
    ...v,
    data: points.filter((p) => p.classification === v.id),
  })).filter((s) => s.data.length > 0);

  return (
    <section className="assortment-chart-block" data-testid="assortment-chart-main">
      <header className="assortment-section-head">
        <h3>{t("Delist vs grow opportunity")}</h3>
        <span className="assortment-section-note">
          {t("Bubble size is inventory value. Lines mark the GMROI cutoffs the verdict used.")}
        </span>
      </header>
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 12, right: 20, bottom: 16, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="gmroi"
            name={t("GMROI")}
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => formatGmroi(v, language)}
            label={{ value: t("GMROI"), position: "insideBottom", offset: -8, fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="growth"
            name={t("Growth")}
            tick={{ fontSize: 11 }}
            domain={["dataMin - 0.02", "dataMax + 0.02"]}
            tickFormatter={(v) => formatGrowth(v, language)}
            label={{ value: t("Growth"), angle: -90, position: "insideLeft", fontSize: 11 }}
          />
          <ZAxis type="number" dataKey="inv_value" range={[20, 420]} name={t("Inventory value")} />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<QuadrantTooltip />} />
          <Legend />
          {thresholds?.p25_gmroi_chain ? (
            <ReferenceLine
              x={thresholds.p25_gmroi_chain}
              stroke="var(--red-500)"
              strokeDasharray="4 4"
              label={{ value: t("Delist cutoff"), fontSize: 10, position: "top" }}
            />
          ) : null}
          {thresholds?.p75_gmroi_healthy ? (
            <ReferenceLine
              x={thresholds.p75_gmroi_healthy}
              stroke="var(--green-600)"
              strokeDasharray="4 4"
              label={{ value: t("Grow cutoff"), fontSize: 10, position: "top" }}
            />
          ) : null}
          {/* Growth 1.0 is the flat line: below it a SKU is shrinking. */}
          <ReferenceLine y={1} stroke="var(--gray-500)" strokeDasharray="2 4" />
          {series.map((s) => (
            <Scatter
              key={s.id}
              name={t(s.label)}
              data={s.data}
              fill={classificationColor(s.id)}
              fillOpacity={0.65}
              onClick={(point) => onSelectSku?.(point?.sku_id)}
              cursor={onSelectSku ? "pointer" : undefined}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * "Margin contribution Pareto" — the mockup's `#ch-a6`, and the visual the
 * Demo Script names for step 7 ("A6 Pareto + GMROI").
 *
 * Bars are the highest-contributing SKUs, coloured by the verdict they already
 * carry, so the reader sees at a glance whether the range's earners and its
 * delist candidates are the same lines. The line is the cumulative share over
 * the WHOLE scope, not just the drawn bars, and the marker is the rank where
 * it reaches 80% — the Pareto point, counted from the data rather than stored.
 */
export function MarginContributionPareto({ pareto, onSelectSku }) {
  const { t, language } = useLanguage();
  const bars = pareto?.bars ?? [];

  if (!bars.length) {
    return <p className="assortment-empty">{t("No SKUs in scope.")}</p>;
  }

  const withinChart = pareto.pareto_rank > 0 && pareto.pareto_rank <= bars.length;

  return (
    <section className="assortment-chart-block" data-testid="assortment-chart-pareto">
      <header className="assortment-section-head">
        <h3>{t("Margin contribution Pareto")}</h3>
        <span className="assortment-section-note">
          {t("Top")} {bars.length} {t("of")} {pareto.sku_count} {t("SKUs by contribution/day")} ·{" "}
          {pareto.pareto_rank} {t("SKUs carry the first")} {pareto.pareto_share_pct}%
        </span>
      </header>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={bars} margin={{ top: 12, right: 12, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="rank" tick={{ fontSize: 10 }} />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => formatIdr(v, language, { digits: 0 })}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, 100]}
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip content={<ParetoTooltip />} />
          {withinChart ? (
            <ReferenceLine
              yAxisId="right"
              x={bars[pareto.pareto_rank - 1].rank}
              stroke="var(--gray-500)"
              strokeDasharray="4 4"
              label={{ value: `${pareto.pareto_share_pct}%`, fontSize: 10, position: "top" }}
            />
          ) : null}
          <Bar
            yAxisId="left"
            dataKey="contribution_per_day"
            name={t("Contribution/day")}
            onClick={(row) => onSelectSku?.(row?.sku_id)}
            cursor={onSelectSku ? "pointer" : undefined}
          >
            {bars.map((row) => (
              <Cell key={row.sku_id} fill={classificationColor(row.classification)} />
            ))}
          </Bar>
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="cumulative_share"
            name={t("Cumulative share")}
            stroke="var(--gray-700)"
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </section>
  );
}

function ParetoTooltip({ active, payload }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="assortment-chart-tooltip">
      <strong>{p.sku_id} · {p.name}</strong>
      <span>{t("Contribution/day")}: {formatIdr(p.contribution_per_day, language)}</span>
      <span>{t("GMROI")}: {formatGmroi(p.gmroi, language)}</span>
      <span>{t("Cumulative share")}: {p.cumulative_share}%</span>
      <span className="assortment-tooltip-total">{t("Verdict")}: {t(p.classification)}</span>
    </div>
  );
}

/**
 * "Range decision mix" — the mockup's `#ch-a6b`, the Pareto's twin card.
 *
 * The same three verdicts the rest of the board runs on, counted by SKU, with
 * the range size in the middle. It answers the question the Pareto raises:
 * having seen that a few lines carry the margin, how much of the range is
 * actually up for a decision.
 *
 * Reads the KPIs rather than re-counting the items, so it cannot disagree
 * with the tiles above it.
 */
export function RangeDecisionMix({ kpis }) {
  const { t, language } = useLanguage();

  const slices = [
    { id: "grow", label: "Grow", value: Number(kpis?.grow_candidates) || 0 },
    { id: "hold", label: "Keep", value: Number(kpis?.hold_count) || 0 },
    { id: "delist", label: "Delist", value: Number(kpis?.delist_candidates) || 0 },
  ].filter((s) => s.value > 0);

  const total = Number(kpis?.sku_count) || 0;
  if (!slices.length || !total) {
    return <p className="assortment-empty">{t("No SKUs in scope.")}</p>;
  }

  return (
    <section className="assortment-chart-block" data-testid="assortment-chart-decision-mix">
      <h4>{t("Range decision mix")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={slices}
            dataKey="value"
            nameKey="label"
            innerRadius="58%"
            outerRadius="82%"
            paddingAngle={1}
          >
            {slices.map((s) => (
              <Cell key={s.id} fill={classificationColor(s.id)} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name) => [
              `${formatUnits(value, language)} ${t("SKUs")} · ${((value / total) * 100).toFixed(1)}%`,
              t(name),
            ]}
          />
          <Legend formatter={(value) => t(value)} />
          <text
            x="50%"
            y="46%"
            textAnchor="middle"
            className="assortment-donut-centre"
          >
            {formatUnits(total, language)}
          </text>
          <text
            x="50%"
            y="46%"
            dy={18}
            textAnchor="middle"
            className="assortment-donut-centre-sub"
          >
            {t("SKUs in range")}
          </text>
        </PieChart>
      </ResponsiveContainer>
    </section>
  );
}

/** Contribution/day by vertical (vertical bars) — A6 spec section 5a. */
export function ContributionByVerticalChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows]
    .filter((r) => r.contribution_per_day > 0)
    .sort((a, b) => b.contribution_per_day - a.contribution_per_day)
    .map((r) => ({ label: r.label ?? r.vertical_id, value: r.contribution_per_day }));

  if (!data.length) return <p className="assortment-empty">{t("No SKUs in scope.")}</p>;

  return (
    <section className="assortment-chart-block" data-testid="assortment-chart-vertical">
      <h4>{t("Contribution/day by vertical")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatIdr(v, language, { digits: 0 })} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar dataKey="value" name={t("Contribution/day")}>
            {data.map((_, i) => (
              <Cell key={i} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/** Contribution/day by category (horizontal bars) — A6 spec section 6. */
export function ContributionByCategoryChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows].sort((a, b) => b.value - a.value).slice(0, 8);

  if (!data.length) return <p className="assortment-empty">{t("No SKUs in scope.")}</p>;

  return (
    <section className="assortment-chart-block" data-testid="assortment-chart-category">
      <h4>{t("Contribution/day by category")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart layout="vertical" data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => formatIdr(v, language, { digits: 0 })} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar dataKey="value" name={t("Contribution/day")}>
            {data.map((_, i) => (
              <Cell key={i} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
