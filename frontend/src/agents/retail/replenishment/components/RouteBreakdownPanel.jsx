import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLanguage } from "../../../../LanguageProvider.jsx";
import { formatIdr, formatUnits, routeColor } from "../presentation.js";

function RouteTooltip({ active, payload }) {
  const { language, t } = useLanguage();
  if (!active || !payload?.length) return null;

  const route = payload[0].payload;
  return (
    <div className="po-chart-tooltip">
      <strong>{route.label}</strong>
      <span>+{route.added_days}d {t("lead")}</span>
      <span>
        {t("At cost")}: {formatIdr(route.order_value_cost, language)}
      </span>
      <span>
        {t("Lines")}: {formatUnits(route.line_count, language)}
      </span>
      <em>{t(route.note)}</em>
    </div>
  );
}

/**
 * A3 spec 5a: order value by route.
 *
 * Bars stay in lead-time order rather than sorting by size. The question this
 * chart answers is "how much of my order is stuck behind the slowest path",
 * and re-ordering the bars by value would hide exactly that.
 */
export default function RouteBreakdownPanel({ routes, activeRoute, onSelect }) {
  const { language, t } = useLanguage();
  const total = routes.reduce((running, route) => running + route.order_value_cost, 0);

  return (
    <section className="po-panel" aria-label={t("Order value by route")}>
      <header className="po-panel-head">
        <h3>{t("Order value by route")}</h3>
        <span className="po-panel-note">{formatIdr(total, language)} {t("at cost")}</span>
      </header>

      <div className="po-chart" role="img" aria-label={t("Order value by route")}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={routes} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid stroke="var(--gray-100)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--line)" }}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={(value) => formatIdr(value, language)}
            />
            <Tooltip cursor={{ fill: "var(--gray-100)", fillOpacity: 0.4 }} content={<RouteTooltip />} />
            <Bar dataKey="order_value_cost" isAnimationActive={false} radius={[4, 4, 0, 0]}>
              {routes.map((route) => (
                <Cell
                  key={route.id}
                  fill={routeColor(route.id)}
                  fillOpacity={activeRoute === route.id || !activeRoute ? 1 : 0.35}
                  cursor="pointer"
                  onClick={() => onSelect(route.id)}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="po-route-legend">
        {routes.map((route) => (
          <li key={route.id}>
            <button
              type="button"
              className={activeRoute === route.id ? "is-active" : ""}
              onClick={() => onSelect(route.id)}
            >
              <span className="po-route-swatch" style={{ background: routeColor(route.id) }} />
              <span className="po-route-name">{route.label}</span>
              <span className="po-route-lead">+{route.added_days}d</span>
              <span className="po-route-lines">
                {formatUnits(route.line_count, language)} {t("lines")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
