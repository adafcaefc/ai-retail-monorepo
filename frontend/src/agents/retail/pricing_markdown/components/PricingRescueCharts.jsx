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
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { useLanguage } from "../../../../LanguageProvider.jsx";
import { CANDIDATE_STATES } from "../data/contract.js";
import { formatIdr, formatPercent, stateColor } from "../presentation.js";

/** "W-16" / "Today" / "W+15" — the signed `week` field computeLadderHistory ships. */
function formatWeek(week, t) {
  if (week === 0) return t("Today");
  return week > 0 ? `W+${week}` : `W${week}`;
}

/**
 * "Rescue waterfall" — A5 mockup's `ch-a5`: value at risk -> recovered ->
 * residual write-off, as three steps rather than a bar+line overlay (see
 * AtRiskVsRecoverableChart in PricingCharts.jsx for that alternative view).
 * Built directly from `dashboard.kpis` — no new selector needed, since
 * at_risk_value/recoverable_value/write_off_value already reconcile exactly
 * (write_off_value = max(0, at_risk_value - recoverable_value), see
 * computeKpis in data/selectors.js).
 *
 * Classic recharts stacked-bar waterfall: an invisible `base` bar offsets
 * each step to its running total, and a colored `size` bar on top draws the
 * actual step. Written fresh here rather than imported from
 * ../../../../components/ChartRenderer.jsx's own waterfall (that one is
 * shaped for LLM chat payloads, not this board — every agent folder keeps
 * its own chart components, see presentation.js's docstring).
 */
export function RescueWaterfallChart({ kpis }) {
  const { t, language } = useLanguage();
  const atRisk = Number(kpis?.at_risk_value) || 0;
  const writeOff = Number(kpis?.write_off_value) || 0;
  // Clamped against at_risk so the bar never runs the total negative even
  // if a future recovery formula change let recoverable exceed at-risk.
  const recovered = Math.max(0, Math.min(Number(kpis?.recoverable_value) || 0, atRisk));

  if (!atRisk) return <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>;

  const rows = [
    { name: t("At risk"), base: 0, size: atRisk, fill: "var(--red-500)" },
    { name: t("Recovered"), base: writeOff, size: recovered, fill: "var(--green-500)" },
    { name: t("Residual write-off"), base: 0, size: writeOff, fill: "var(--amber-600)" },
  ];

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-rescue-waterfall">
      <h4>{t("Rescue waterfall")}</h4>
      <p className="pricing-footnote">{t("Value at risk → recovered vs written off")}</p>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value, name) => (name === "size" ? formatIdr(value, language) : null)}
            labelFormatter={(label) => label}
          />
          <Bar dataKey="base" stackId="waterfall" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="size" stackId="waterfall" name={t("Value")}>
            {rows.map((row, i) => (
              <Cell key={i} fill={row.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * "Elasticity vs depth" — A5 mockup's `ch-a5b`: one bubble per markdown
 * candidate, x = price elasticity, y = this candidate's own markdown depth
 * at the current lever (`depth_pct`, from computeCandidates), bubble size =
 * at-risk-gross exposure, colored by risk state. First scatter/bubble chart
 * in this codebase (grep confirmed no prior <ScatterChart> usage) — recharts
 * already ships Scatter/ZAxis, just not previously imported anywhere.
 */
export function ElasticityVsDepthChart({ rows }) {
  const { t, language } = useLanguage();
  if (!rows?.length) return <p className="pricing-empty">{t("No markdown candidates in scope.")}</p>;

  const byState = new Map(CANDIDATE_STATES.map((state) => [state, []]));
  for (const r of rows) {
    if (!byState.has(r.state)) byState.set(r.state, []);
    byState.get(r.state).push({
      x: r.elasticity,
      y: r.depth_pct,
      z: r.at_risk_gross,
      name: r.name,
      state: r.state,
    });
  }

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-elasticity-depth">
      <h4>{t("Elasticity vs depth")}</h4>
      <p className="pricing-footnote">
        {t("Bubble = at-risk value · steeper elasticity clears faster")}
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="x"
            name={t("Elasticity")}
            tick={{ fontSize: 11 }}
            label={{ value: t("Price elasticity"), position: "insideBottom", offset: -4, fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={t("Depth")}
            tickFormatter={(v) => `${v}%`}
            tick={{ fontSize: 11 }}
          />
          <ZAxis type="number" dataKey="z" range={[40, 400]} name={t("At-risk value")} />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            formatter={(value, name) => {
              if (name === t("Depth")) return `${value}%`;
              if (name === t("At-risk value")) return formatIdr(value, language);
              return value;
            }}
          />
          {[...byState.entries()]
            .filter(([, points]) => points.length)
            .map(([state, points]) => (
              <Scatter key={state} name={state} data={points} fill={stateColor(state)} fillOpacity={0.65} />
            ))}
        </ScatterChart>
      </ResponsiveContainer>
    </section>
  );
}

/**
 * "At-risk value: ladder vs no action" — the mockup's `ch-main` for A5,
 * adapted to what this board actually has. The fixture has no time
 * dimension anywhere (no weekly/date field on any item, unlike
 * Replenishment's real 33-week demand curve), and unlike demand, at-risk
 * value has no real PAST to record either — it is a snapshot metric, not a
 * rate with history to backtest. So NEITHER side of this chart is measured:
 * `week: 0` ("Today") is the one real point (today's own at_risk_value/
 * write_off_value, injected in computeLadderHistory from `dashboard.kpis`
 * -- NOT read from the ladder table, which never stores offset 0 at all),
 * and `week -16..-1`/`week 1..16` are both modelled the same way, from
 * `synthetic.markdown_ladder_store_sku_16w` (see that table's migrations
 * and scripts/generate_synthetic_markdown_ladder_16w.py for the exact
 * assumptions and the gates it passed before being written).
 *
 * `rows = dashboard.ladder_history`, one point per week, oldest first — see
 * computeLadderHistory in data/selectors.js. `horizon` (4/8/12/16, one per
 * side — the control itself lives in the filter bar, `PricingMarkdownFilters
 * .jsx`, mirroring `demand_forecasting`'s own Horizon control) is a pure
 * client-side slice here — every week is already computed and shipped, so
 * narrowing the horizon never triggers a refetch, unlike demand_
 * forecasting's own horizon (which must reload because its horizon changes
 * what the backend computes in the first place).
 */
export function MarkdownLadderChart({ rows, horizon = 16, kpis }) {
  const { t, language } = useLanguage();
  if (!rows?.length) {
    return <p className="pricing-empty">{t("No projection available for this scope.")}</p>;
  }

  // `week: 0` is today, so "Horizon N" means N weeks of history (-N..-1)
  // AND N weeks of forecast beyond today (1..N) -- inclusive on both ends,
  // e.g. Horizon 4 shows W-4..W+4. Data only goes out to W+15, so Horizon
  // 16's forward edge naturally caps there rather than reaching a
  // nonexistent W+16.
  const visible = rows.filter((row) => row.week >= -horizon && row.week <= horizon);

  // Non-zero-anchored, framed on the plotted band — same reasoning
  // RequirementVsInboundPanel.jsx uses: these are two comparable weekly
  // figures, not independent magnitudes, so cropping to the data (with
  // padding) keeps the gap between them legible instead of compressed
  // against a zero baseline the values never approach.
  const plotted = visible.flatMap((row) => [row.no_action, row.ladder]);
  const low = plotted.length ? Math.min(...plotted) : 0;
  const high = plotted.length ? Math.max(...plotted) : 0;
  const padding = (high - low) * 0.2 || high * 0.05 || 1;
  const domain = [Math.max(0, low - padding), high + padding];

  return (
    <section className="pricing-chart-block" data-testid="pricing-chart-ladder-vs-no-action">
      <h4>{t("At-risk value: ladder vs no action")}</h4>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={visible} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="week" tickFormatter={(v) => formatWeek(v, t)} tick={{ fontSize: 11 }} />
          <YAxis domain={domain} tickFormatter={(v) => formatIdr(v, language)} tick={{ fontSize: 11 }} />
          <Tooltip
            labelFormatter={(v) => formatWeek(v, t)}
            formatter={(value) => formatIdr(value, language)}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {/* The boundary between the modelled past and the modelled future —
              the one point on either side of it that IS real. */}
          <ReferenceLine x={0} stroke="var(--line)" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="no_action"
            name={t("No action")}
            stroke="var(--red-500)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="ladder"
            name={t("Markdown ladder")}
            stroke="var(--green-500)"
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      {kpis ? (
        <div className="pricing-ladder-stats">
          <LadderStat label={t("AT RISK")} value={formatIdr(kpis.at_risk_value, language)} />
          <LadderStat label={t("RECOVER")} value={formatIdr(kpis.recoverable_value, language)} />
          <LadderStat label={t("WRITE-OFF")} value={formatIdr(kpis.write_off_value, language)} />
          <LadderStat
            label={t("DEPTH")}
            value={`−${formatPercent((Number(kpis.avg_depth_pct) || 0) / 100, language)}`}
          />
        </div>
      ) : null}
      <p className="pricing-footnote">
        {t("Synthetic projection")} · {t("Today is real; every other week is modelled from each SKU's own growth and recovery rate.")}
      </p>
    </section>
  );
}

function LadderStat({ label, value }) {
  return (
    <div className="pricing-ladder-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
