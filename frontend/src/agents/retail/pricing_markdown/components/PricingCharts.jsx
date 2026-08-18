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
import { categoryColor, formatIdr } from "../presentation.js";

/**
 * At-risk value by vertical (vertical bars) — A5 spec section 5a. Sorted
 * desc, value labels on.
 */
export function AtRiskByVerticalChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows]
    .filter((r) => r.at_risk_value > 0)
    .sort((a, b) => b.at_risk_value - a.at_risk_value)
    .map((r) => ({ label: r.label ?? r.vertical_id, value: r.at_risk_value }));

  if (!data.length) return <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>;

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-vertical">
      <h4>{t("At-risk value by vertical")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar dataKey="value" name={t("At-risk value")}>
            {data.map((_, i) => (
              <Cell key={i} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/** At-risk value by category (horizontal bars) — the by-category dimension chart. */
export function AtRiskByCategoryChart({ rows }) {
  const { t, language } = useLanguage();
  const data = [...rows].sort((a, b) => b.value - a.value).slice(0, 8);

  if (!data.length) return <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>;

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-category">
      <h4>{t("At-risk value by category")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart layout="vertical" data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => formatIdr(v, language)} />
          <Bar dataKey="value" name={t("At-risk value")}>
            {data.map((_, i) => (
              <Cell key={i} fill={categoryColor(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
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
