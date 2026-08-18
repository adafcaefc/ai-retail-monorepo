import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
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
