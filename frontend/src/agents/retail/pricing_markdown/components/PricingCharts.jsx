import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { ALL } from "../data/contract.js";
import { categoryColor, formatIdr } from "../presentation.js";

/**
 * When a chart's own grouping dimension has been narrowed to a single bar by
 * the active scope, the chart is still numerically correct but has nothing
 * left to compare — this points at where the actual breakdown lives instead
 * of leaving a bare 1-bar chart that reads as broken. Data-driven (checks
 * the computed row count), not scope-condition-driven, so it also covers
 * cases where a dimension only ever has one value regardless of filters.
 */
function ScopeCollapseNote({ data, hint }) {
  const { t } = useLanguage();
  if (data.length !== 1) return null;
  return (
    <p className="pricing-footnote">
      {t("Scoped to")} <b>{data[0].label}</b>
      {hint ? <> — {t(hint)}</> : null}
    </p>
  );
}

/** A panel title with an optional "Back to all X" reset button beside it. */
function ChartHead({ title, selected, resetLabel, onSelect }) {
  const { t } = useLanguage();
  const hasSelection = Boolean(selected) && selected !== ALL;
  return (
    <div className="pricing-panel-head">
      <h4>{t(title)}</h4>
      {hasSelection ? (
        <button type="button" className="pricing-chart-reset" onClick={() => onSelect(ALL)}>
          {t(resetLabel)}
        </button>
      ) : null}
    </div>
  );
}

/**
 * A row of filter-shortcut pills mirroring the chart above it — the primary
 * click target in tests (Recharts bar clicks are mocked out there), same
 * role as demand_forecasting's DrilldownButtons.
 */
function DrilldownPills({ rows, idKey, onSelect, label }) {
  const { t } = useLanguage();
  if (!onSelect || !rows.length) return null;
  return (
    <div className="pricing-chart-drilldowns" aria-label={t(label)}>
      {rows.map((row) => (
        <button key={row[idKey]} type="button" onClick={() => onSelect(row[idKey])}>
          {row.label}
        </button>
      ))}
    </div>
  );
}

/**
 * At-risk value by vertical (vertical bars) — A5 spec section 5a. Sorted
 * desc, value labels on. Clicking a bar or pill scopes the board to that
 * vertical; `onSelect` also receives "ALL" from the reset button.
 */
export function AtRiskByVerticalChart({ rows, selected, onSelect }) {
  const { t, language } = useLanguage();
  const data = [...rows]
    .filter((r) => r.at_risk_value > 0)
    .sort((a, b) => b.at_risk_value - a.at_risk_value)
    .map((r) => ({ ...r, label: r.label ?? r.vertical_id, value: r.at_risk_value }));

  if (!data.length) return <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>;

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-vertical">
      <ChartHead title="At-risk value by vertical" selected={selected} resetLabel="Back to all verticals" onSelect={onSelect} />
      <ScopeCollapseNote data={data} />
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar
            dataKey="value"
            name={t("At-risk value")}
            onClick={onSelect ? (entry) => onSelect(entry?.vertical_id ?? entry?.payload?.vertical_id) : undefined}
            cursor={onSelect ? "pointer" : undefined}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <DrilldownPills rows={data} idKey="vertical_id" onSelect={onSelect} label="Vertical filter shortcuts" />
    </section>
  );
}

/**
 * At-risk value by category (horizontal bars) — the by-category dimension
 * chart. Clicking a bar or pill scopes the board to that category.
 */
export function AtRiskByCategoryChart({ rows, selected, onSelect }) {
  const { t, language } = useLanguage();
  const data = [...rows].sort((a, b) => b.value - a.value).slice(0, 8);

  if (!data.length) return <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>;

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-category">
      <ChartHead title="At-risk value by category" selected={selected} resetLabel="Back to all categories" onSelect={onSelect} />
      <ScopeCollapseNote data={data} hint='See "At-risk value by vertical" and the store charts for more context.' />
      <ResponsiveContainer width="100%" height={260}>
        <BarChart layout="vertical" data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar
            dataKey="value"
            name={t("At-risk value")}
            onClick={onSelect ? (entry) => onSelect(entry?.category_id ?? entry?.payload?.category_id) : undefined}
            cursor={onSelect ? "pointer" : undefined}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <DrilldownPills rows={data} idKey="category_id" onSelect={onSelect} label="Category filter shortcuts" />
    </section>
  );
}

/**
 * "At-risk value vs recoverable markdown" — the main chart, A5 spec section
 * 4. At-risk as bars, recoverable as an overlaid line, per vertical.
 */
export function AtRiskVsRecoverableChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows]
    .filter((r) => r.at_risk_value > 0)
    .sort((a, b) => b.at_risk_value - a.at_risk_value)
    .map((r) => ({
      label: r.label ?? r.vertical_id,
      at_risk: r.at_risk_value,
      recoverable: r.recoverable_value,
    }));

  if (!data.length) return <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>;

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-main">
      <h4>{t("At-risk value vs recoverable markdown")}</h4>
      <ScopeCollapseNote
        data={data}
        hint='See "At-risk value by category" and the store charts below for the breakdown.'
      />
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Legend />
          <Bar dataKey="at_risk" name={t("At-risk value")} fill="var(--red-500)" />
          <Line type="monotone" dataKey="recoverable" name={t("Recoverable")} stroke="var(--green-600)" strokeWidth={2} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
