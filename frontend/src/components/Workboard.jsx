import {
  useEffect,
  useMemo,
  useState
} from "react";

import ChartRenderer from "./ChartRenderer.jsx";
import {
  fetchDashboard,
  recalculateDashboardSimulation
} from "../api/dashboard.js";

export default function Workboard({
  agentId,
  agentName
}) {
  const [dashboard, setDashboard] = useState(null);
  const [view, setView] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [values, setValues] = useState({});
  const [scope, setScope] = useState("all");
  const [simResult, setSimResult] = useState(null);
  const [simBusy, setSimBusy] = useState(false);
  const [simError, setSimError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      setSimResult(null);
      setSimError("");

      try {
        const payload = await fetchDashboard(agentId);
        if (cancelled) {
          return;
        }

        setDashboard(payload);
        setView(payload.default_view || "");
        const nextValues = {};
        for (const input of payload.simulator?.inputs || []) {
          nextValues[input.id] = Number(input.default ?? 0);
        }
        setValues(nextValues);
        setScope(
          payload.simulator?.scope_options?.[0] || "all"
        );
      } catch (loadError) {
        if (!cancelled) {
          setDashboard(null);
          setError(
            loadError.message ||
              "Unable to load dashboard."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  const activeView = useMemo(() => {
    if (!dashboard) {
      return null;
    }
    return (
      dashboard.views?.[view] ||
      dashboard.views?.[dashboard.default_view] ||
      null
    );
  }, [dashboard, view]);

  async function runSimulation() {
    if (!dashboard?.simulator?.action || simBusy) {
      return;
    }

    setSimBusy(true);
    setSimError("");

    try {
      const action = dashboard.simulator.action;
      let body = { ...values };

      if (action === "calculate_collection_scenario") {
        body = {
          customer_name:
            dashboard.simulator.submit_data?.customer_name ||
            "Customer A",
          cash_to_collect_idr_mn: Number(
            values.cash_to_collect_idr_mn || 0
          ),
          discount_pct: Number(values.discount_pct || 0)
        };
      } else if (action === "simulate_finance") {
        body = {
          price: Number(values.price || 0),
          cost: Number(values.cost || 0),
          vol: Number(values.vol || 0),
          fx: Number(values.fx || 0),
          opex: Number(values.opex || 0),
          scope
        };
      } else if (action === "simulate_leakage") {
        const baseline = dashboard.simulator.baseline || {};
        body = {
          hold: Number(values.hold || 0),
          dupRec: Number(values.dupRec || 0),
          ovRec: Number(values.ovRec || 0),
          duplicates_amount: baseline.duplicates_amount,
          overbill_amount: baseline.overbill_amount,
          other_blocked: baseline.other_blocked,
          at_risk: baseline.at_risk
        };
      } else if (action === "simulate_cashflow") {
        body = {
          accelerate_collection_idr_mn: Number(
            values.accelerate_collection_idr_mn || 0
          ),
          defer_payment_idr_mn: Number(
            values.defer_payment_idr_mn || 0
          ),
          credit_line_draw_idr_mn: Number(
            values.credit_line_draw_idr_mn || 0
          ),
          hedge_usd: Number(values.hedge_usd || 0)
        };
      }

      const result = await recalculateDashboardSimulation(
        action,
        body
      );
      setSimResult(result);
    } catch (requestError) {
      setSimError(
        requestError.message ||
          "Simulation recalculation failed."
      );
    } finally {
      setSimBusy(false);
    }
  }

  if (loading) {
    return (
      <section
        className="workboard workboard-loading"
        data-testid="workboard"
      >
        <div
          className="workboard-loader"
          role="status"
          aria-live="polite"
        >
          <span
            className="workboard-spinner"
            aria-hidden="true"
          />
          <span>Loading {agentName} dashboard…</span>
        </div>
      </section>
    );
  }

  if (error || !dashboard) {
    return (
      <section
        className="workboard workboard-loading"
        data-testid="workboard"
      >
        <div className="workboard-status error" role="alert">
          {error || "Dashboard unavailable."}
        </div>
      </section>
    );
  }

  return (
    <section className="workboard" data-testid="workboard">
      <header className="workboard-header">
        <div>
          <span className="header-kicker">
            {agentName} dashboard
          </span>
          <h1>{agentName} performance board</h1>
        </div>
      </header>

      <div className="kpi-row" data-testid="kpi-row">
        {(dashboard.kpis || []).map((kpi) => (
          <button
            key={kpi.id}
            type="button"
            className={
              "kpi-tile" +
              (kpi.alert ? " alert" : "") +
              (view === kpi.view ? " on" : "")
            }
            data-testid={`kpi-${kpi.id}`}
            onClick={() => setView(kpi.view)}
          >
            <span className="kpi-open">OPEN</span>
            <span className="kpi-label">{kpi.label}</span>
            <strong className="kpi-value" data-testid={`kpi-${kpi.id}-value`}>
              {kpi.value}
              {kpi.unit ? (
                <span className="kpi-unit"> {kpi.unit}</span>
              ) : null}
            </strong>
            <span className="kpi-delta">{kpi.delta}</span>
          </button>
        ))}
      </div>

      <div className="workboard-mid">
        <article className="focus-card" data-testid="focus-panel">
          <FocusBody view={activeView} />
        </article>

        <div className="side-col" data-testid="side-panels">
          <article className="side-card">
            <FocusBody view={dashboard.side?.top} compact />
          </article>
          <article className="side-card">
            <FocusBody view={dashboard.side?.bottom} compact />
          </article>
        </div>
      </div>

      <WhatIfBar
        simulator={dashboard.simulator}
        values={values}
        scope={scope}
        setScope={setScope}
        onChange={(id, value) =>
          setValues((current) => ({
            ...current,
            [id]: value
          }))
        }
        onCalculate={runSimulation}
        busy={simBusy}
        error={simError}
        result={simResult}
      />
    </section>
  );
}

function FocusBody({ view, compact = false }) {
  if (!view) {
    return <p className="workboard-empty">No view data.</p>;
  }

  if (view.table) {
    return (
      <div className="focus-table-wrap">
        <div className="focus-title-row">
          <h3>{view.title}</h3>
          {view.tag ? <span className="focus-tag">{view.tag}</span> : null}
        </div>
        <table className="focus-table">
          <thead>
            <tr>
              {view.table.headers.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.table.rows.map((row, index) => (
              <tr key={`${index}-${row[0]}`}>
                {row.map((cell, cellIndex) => (
                  <td
                    key={`${index}-${cellIndex}`}
                    className={cellIndex > 0 ? "num" : undefined}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {view.note ? <p className="focus-note">{view.note}</p> : null}
      </div>
    );
  }

  return (
    <div className={compact ? "side-chart" : "focus-chart"}>
      <ChartRenderer
        data={view}
        variant={compact ? "compact" : "fill"}
      />
    </div>
  );
}

function WhatIfBar({
  simulator,
  values,
  scope,
  setScope,
  onChange,
  onCalculate,
  busy,
  error,
  result
}) {
  if (!simulator) {
    return null;
  }

  const summary = summarizeResult(simulator.action, result, simulator);

  return (
    <section className="whatif-bar" data-testid="whatif-bar">
      <div className="whatif-top">
        <strong>What-if simulator</strong>
        <div className="whatif-controls">
          {Array.isArray(simulator.scope_options) &&
            simulator.scope_options.map((option) => (
              <button
                key={option}
                type="button"
                className={
                  "scope-btn" + (scope === option ? " on" : "")
                }
                onClick={() => setScope(option)}
              >
                {option === "all" ? "All lines" : "FX lines"}
              </button>
            ))}
          <button
            type="button"
            className="calc-btn"
            data-testid="calculate-simulation"
            disabled={busy}
            onClick={onCalculate}
          >
            {busy ? (
              <>
                <span
                  className="calc-spinner"
                  aria-hidden="true"
                />
                Running scenario…
              </>
            ) : (
              "Calculate simulation"
            )}
          </button>
        </div>
      </div>

      <div
        className={
          "whatif-grid" + (busy ? " is-loading" : "")
        }
      >
        <div className="whatif-levers">
          <div className="whatif-label">Levers</div>
          {(simulator.inputs || []).map((input) => (
            <label key={input.id} className="lever">
              <span>
                {input.label}
                {input.unit ? ` (${input.unit})` : ""}
              </span>
              <div className="lever-controls">
                <input
                  type="range"
                  min={input.min}
                  max={input.max}
                  step={input.step}
                  value={values[input.id] ?? input.default ?? 0}
                  data-testid={`lever-${input.id}`}
                  disabled={busy}
                  onInput={(event) =>
                    onChange(
                      input.id,
                      Number(event.currentTarget.value)
                    )
                  }
                />
                <input
                  type="number"
                  className="lever-number"
                  min={input.min}
                  max={input.max}
                  step={input.step}
                  value={values[input.id] ?? input.default ?? 0}
                  data-testid={`lever-${input.id}-number`}
                  disabled={busy}
                  onChange={(event) =>
                    onChange(
                      input.id,
                      Number(event.currentTarget.value)
                    )
                  }
                />
              </div>
            </label>
          ))}
        </div>

        <div className="whatif-stats" data-testid="whatif-stats">
          {busy ? (
            <div
              className="whatif-loading"
              role="status"
              aria-live="polite"
            >
              <span
                className="calc-spinner calc-spinner-lg"
                aria-hidden="true"
              />
              <span>Updating scenario results…</span>
            </div>
          ) : (
            <>
              {summary.stats.map((stat) => (
                <div key={stat.label} className="whatif-stat">
                  <span>{stat.label}</span>
                  <strong data-testid={`stat-${stat.id}`}>
                    {stat.value}
                  </strong>
                  <small className={stat.tone}>{stat.delta}</small>
                </div>
              ))}
              {summary.chart ? (
                <div className="whatif-mini-chart">
                  <ChartRenderer
                    data={summary.chart}
                    variant="compact"
                  />
                </div>
              ) : null}
            </>
          )}
        </div>

        <div className="whatif-gauge" data-testid="whatif-gauge">
          <div className="whatif-label">
            {simulator.gauge_label || "Scenario"}
          </div>
          {busy ? (
            <div
              className="whatif-loading whatif-loading-gauge"
              role="status"
            >
              <span
                className="calc-spinner calc-spinner-lg"
                aria-hidden="true"
              />
            </div>
          ) : (
            <>
              <div className="gauge-center" data-testid="gauge-center">
                {summary.gauge.center}
              </div>
              <p data-testid="gauge-txt">{summary.gauge.txt}</p>
            </>
          )}
        </div>
      </div>

      {error ? (
        <div className="workboard-status error" role="alert">
          {error}
        </div>
      ) : null}
    </section>
  );
}

function summarizeResult(action, result, simulator) {
  const empty = {
    stats: [
      {
        id: "a",
        label: "Scenario",
        value: "—",
        delta: "Awaiting scenario",
        tone: ""
      },
      {
        id: "b",
        label: "Impact",
        value: "—",
        delta: "Set levers to begin",
        tone: ""
      },
      {
        id: "c",
        label: "Target",
        value: "—",
        delta: "Results after run",
        tone: ""
      }
    ],
    chart: null,
    gauge: {
      center: "—",
      txt: "Run scenario to update"
    }
  };

  if (!result) {
    return empty;
  }

  if (action === "simulate_finance") {
    const stats = result.stats || {};
    const baseline = result.baseline || {};
    const scenario = result.scenario || {};
    return {
      stats: [
        {
          id: "margin",
          label: "Scenario margin",
          value: `${stats.scenario_margin_pct}%`,
          delta: `${stats.delta_margin_pts >= 0 ? "+" : ""}${stats.delta_margin_pts} pts`,
          tone: stats.delta_margin_pts >= 0 ? "good" : "bad"
        },
        {
          id: "ebitda",
          label: "EBITDA",
          value: formatNumber(stats.ebitda_idr_mn),
          delta: `${stats.delta_ebitda_idr_mn >= 0 ? "+" : ""}${formatNumber(stats.delta_ebitda_idr_mn)} mn`,
          tone: stats.delta_ebitda_idr_mn >= 0 ? "good" : "bad"
        },
        {
          id: "target",
          label: "vs Target",
          value: `${stats.vs_target_pts} pts`,
          delta: stats.vs_target_pts >= 0 ? "at/above" : "below",
          tone: stats.vs_target_pts >= 0 ? "good" : "bad"
        }
      ],
      chart: {
        title: "Now vs Scenario",
        chart_type: "bar",
        y_axis_title: "margin %",
        target: 15,
        target_label: "Target 15%",
        data: [
          {
            label: "Now",
            value: round1((baseline.margin || 0) * 100)
          },
          {
            label: "Scenario",
            value: round1((scenario.margin || 0) * 100)
          }
        ]
      },
      gauge: result.gauge || empty.gauge
    };
  }

  if (action === "calculate_collection_scenario") {
    const payload = result.result || result;
    const baseline = simulator.baseline || {};
    return {
      stats: [
        {
          id: "dso",
          label: "Scenario DSO",
          value: `${formatNumber(payload.dso_after_days)}d`,
          delta: `${formatNumber(payload.dso_change_days)}d change`,
          tone: payload.dso_change_days <= 0 ? "good" : "bad"
        },
        {
          id: "cash",
          label: "Cash collected",
          value: formatNumber(payload.cash_collected_idr_mn),
          delta: "IDR mn",
          tone: "good"
        },
        {
          id: "discount",
          label: "Discount cost",
          value: formatNumber(payload.discount_cost_idr_mn),
          delta: `${payload.discount_pct}%`,
          tone: ""
        }
      ],
      chart: {
        title: "DSO now vs scenario",
        chart_type: "bar",
        y_axis_title: "days",
        target: baseline.target_dso,
        target_label: `Target ${baseline.target_dso}`,
        data: [
          { label: "Now", value: Number(baseline.dso || 0) },
          {
            label: "Scenario",
            value: Number(payload.dso_after_days || 0)
          }
        ]
      },
      gauge: {
        center: `${formatNumber(payload.dso_after_days)}d`,
        txt: `Target ${baseline.target_dso}d`
      }
    };
  }

  if (action === "simulate_cashflow") {
    const payload = result.result || result;
    const baseline = simulator.baseline || {};
    return {
      stats: [
        {
          id: "w5",
          label: "Week 5 cash",
          value: formatNumber(payload.week5_cash_idr_mn),
          delta: `was ${formatNumber(baseline.week5_cash)}`,
          tone:
            payload.week5_headroom_idr_mn >= 0 ? "good" : "bad"
        },
        {
          id: "below",
          label: "Weeks below buffer",
          value: String(payload.weeks_below_buffer),
          delta: `buffer ${formatNumber(payload.minimum_buffer_idr_mn)}`,
          tone: payload.weeks_below_buffer === 0 ? "good" : "bad"
        },
        {
          id: "fx",
          label: "FX downside avoided",
          value: formatNumber(payload.fx_downside_avoided_idr_mn),
          delta: `premium ${formatNumber(payload.forward_premium_idr_mn)}`,
          tone: "good"
        }
      ],
      chart: {
        title: "Week 5 cash",
        chart_type: "bar",
        target: baseline.buffer,
        target_label: "Buffer",
        data: [
          { label: "Now", value: Number(baseline.week5_cash || 0) },
          {
            label: "Scenario",
            value: Number(payload.week5_cash_idr_mn || 0)
          }
        ]
      },
      gauge: {
        center: `${formatNumber(payload.hedge_coverage_pct)}%`,
        txt: "Hedge coverage"
      }
    };
  }

  if (action === "simulate_leakage") {
    return {
      stats: [
        {
          id: "total",
          label: "Total protected",
          value: formatNumber(result.total_protected),
          delta: `${result.pct_of_at_risk}% of at risk`,
          tone: "good"
        },
        {
          id: "blocked",
          label: "Blocked",
          value: formatNumber(result.blocked),
          delta: "never leaves",
          tone: "good"
        },
        {
          id: "recovered",
          label: "Recovered",
          value: formatNumber(result.recovered),
          delta: "clawed back",
          tone: "good"
        }
      ],
      chart: {
        title: "Protected vs at risk",
        chart_type: "bar",
        data: [
          { label: "At risk", value: Number(result.at_risk || 0) },
          {
            label: "Protected",
            value: Number(result.total_protected || 0)
          }
        ]
      },
      gauge: result.gauge || empty.gauge
    };
  }

  return empty;
}

function formatNumber(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return numeric.toLocaleString(undefined, {
    maximumFractionDigits: 2
  });
}

function round1(value) {
  return Math.round(Number(value) * 10) / 10;
}
