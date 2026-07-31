import { useCallback, useEffect, useMemo, useState } from "react";

import ChartRenderer from "./ChartRenderer.jsx";
import InfoCard from "./InfoCard.jsx";
import {
  DashboardSkeleton,
  WhatIfGaugeSkeleton,
  WhatIfStatsSkeleton,
} from "./Skeleton.jsx";
import { findInfo } from "../infoRegistry.js";
import { applyFilters, focusFor, isEmptyAfterFilter } from "../filters.js";
import { translatePayload } from "../i18n.js";
import { useLanguage } from "../LanguageProvider.jsx";
import {
  fetchDashboard,
  recalculateDashboardSimulation,
} from "../api/dashboard.js";

// How much of the middle row the main chart takes, as a percentage. Clamped:
// below the floor the main chart cannot label its axes, above the ceiling the
// side panels collapse into slivers. The default mirrors the old 1.55fr/1fr.
const BOARD_SPLIT_KEY = "ledgerline.boardMainPct";
const BOARD_SPLIT_DEFAULT = 60;
const BOARD_SPLIT_MIN = 42;
const BOARD_SPLIT_MAX = 74;

// How much of the side column the upper card takes. Same idea, one axis over:
// on every agent that upper card is a chart worth more or less room depending
// on the question — the GM pool by product, the ageing mix, the leakage mix.
const SIDE_SPLIT_KEY = "ledgerline.sideTopPct";
const SIDE_SPLIT_DEFAULT = 50;
const SIDE_SPLIT_MIN = 28;
const SIDE_SPLIT_MAX = 72;

function clamp(value, min, max, fallback) {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, value));
}

function clampSplit(value) {
  return clamp(value, BOARD_SPLIT_MIN, BOARD_SPLIT_MAX, BOARD_SPLIT_DEFAULT);
}

function clampSideSplit(value) {
  return clamp(value, SIDE_SPLIT_MIN, SIDE_SPLIT_MAX, SIDE_SPLIT_DEFAULT);
}

function readStored(key, clampFn, fallback) {
  try {
    return clampFn(Number(window.localStorage.getItem(key)) || fallback);
  } catch {
    return fallback;
  }
}

// The board toolbar (Agent Action, Recalculate, alerts, Ask <agent>) lives in
// the app header now, so this component renders data only.
export default function Workboard({ agentId, agentName, onAskInsight, insightBusy = false }) {
  const { language, t } = useLanguage();
  const [dashboard, setDashboard] = useState(null);
  const [view, setView] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [values, setValues] = useState({});
  const [scope, setScope] = useState("all");
  const [simResult, setSimResult] = useState(null);
  const [simBusy, setSimBusy] = useState(false);
  const [simError, setSimError] = useState("");
  const [info, setInfo] = useState(null);
  // QC-043: filterId -> chosen option. Empty string means "all".
  const [picked, setPicked] = useState({});
  // Width of the main chart as % of the middle row. Persisted per user, not
  // per agent: a hand that finds the split it likes keeps it everywhere.
  const [split, setSplit] = useState(() =>
    readStored(BOARD_SPLIT_KEY, clampSplit, BOARD_SPLIT_DEFAULT)
  );
  const [sideSplit, setSideSplit] = useState(() =>
    readStored(SIDE_SPLIT_KEY, clampSideSplit, SIDE_SPLIT_DEFAULT)
  );

  // Open the info card for a clicked element. Elements with no
  // registry mapping stay inert rather than opening an empty card.
  function openInfo(infoKey, event, extra = {}) {
    const entry = findInfo(agentId, infoKey);
    if (!entry) {
      return;
    }

    setInfo({
      key: infoKey,
      entry,
      anchor: event.currentTarget.getBoundingClientRect(),
      context: extra.context || "",
      payload: extra.payload || null,
    });
  }

  // Only on agent switch. Not on `view`: a KPI click sets the view
  // and opens the card in the same batch, so watching `view` here
  // would close the card the instant it opened.
  useEffect(() => {
    setInfo(null);
  }, [agentId]);

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
        setScope(payload.simulator?.scope_options?.[0] || "all");
      } catch (loadError) {
        if (!cancelled) {
          setDashboard(null);
          setError(loadError.message || "Unable to load dashboard.");
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

  // Filter selections belong to the agent that offered them.
  useEffect(() => {
    setPicked({});
  }, [agentId]);

  // QC-059: back to the levers the payload shipped with, in one click.
  function resetLevers() {
    setValues({});
    setSimResult(null);
    setSimError("");
  }

  // QC-052: a named scenario replaces the levers it names and leaves the
  // rest at baseline, so two presets can never silently compound.
  function applyPreset(preset) {
    setValues({ ...preset.values });
    setSimResult(null);
    setSimError("");
  }

  function persist(key, value) {
    try {
      window.localStorage.setItem(key, String(value));
    } catch {
      // Private mode: the split still works for this session.
    }
  }

  function saveSplit(value) {
    const next = clampSplit(value);
    setSplit(next);
    persist(BOARD_SPLIT_KEY, next);
    return next;
  }

  function saveSideSplit(value) {
    const next = clampSideSplit(value);
    setSideSplit(next);
    persist(SIDE_SPLIT_KEY, next);
    return next;
  }

  /**
   * Drag a grid separator. The pointer is tracked across the whole row or
   * column, and the clamp is the guarantee that neither panel can be dragged
   * out of usefulness — a chart with no room to label its axes is worse than
   * one that is slightly too small.
   */
  function startResize(startEvent, { axis, set, save }) {
    startEvent.preventDefault();
    const container = startEvent.currentTarget.parentElement;
    if (!container) {
      return;
    }
    const rect = container.getBoundingClientRect();

    const pctAt = (event) =>
      axis === "x"
        ? ((event.clientX - rect.left) / rect.width) * 100
        : ((event.clientY - rect.top) / rect.height) * 100;

    const onMove = (moveEvent) => set(pctAt(moveEvent));
    const onUp = (upEvent) => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      save(pctAt(upEvent));
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function resizeKeyHandler(current, save, [less, more]) {
    return (event) => {
      const step = event.shiftKey ? 5 : 2;
      if (event.key === less) {
        event.preventDefault();
        save(current - step);
      } else if (event.key === more) {
        event.preventDefault();
        save(current + step);
      }
    };
  }

  function persist(key, value) {
    try {
      window.localStorage.setItem(key, String(value));
    } catch {
      // Private mode: the split still works for this session.
    }
  }

  function saveSplit(value) {
    const next = clampSplit(value);
    setSplit(next);
    persist(BOARD_SPLIT_KEY, next);
    return next;
  }

  function saveSideSplit(value) {
    const next = clampSideSplit(value);
    setSideSplit(next);
    persist(SIDE_SPLIT_KEY, next);
    return next;
  }

  /**
   * Drag a grid separator. The pointer is tracked across the whole row or
   * column, and the clamp is the guarantee that neither panel can be dragged
   * out of usefulness — a chart with no room to label its axes is worse than
   * one that is slightly too small.
   */
  function startResize(startEvent, { axis, set, save }) {
    startEvent.preventDefault();
    const container = startEvent.currentTarget.parentElement;
    if (!container) {
      return;
    }
    const rect = container.getBoundingClientRect();

    const pctAt = (event) =>
      axis === "x"
        ? ((event.clientX - rect.left) / rect.width) * 100
        : ((event.clientY - rect.top) / rect.height) * 100;

    const onMove = (moveEvent) => set(pctAt(moveEvent));
    const onUp = (upEvent) => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      save(pctAt(upEvent));
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function resizeKeyHandler(current, save, [less, more]) {
    return (event) => {
      const step = event.shiftKey ? 5 : 2;
      if (event.key === less) {
        event.preventDefault();
        save(current - step);
      } else if (event.key === more) {
        event.preventDefault();
        save(current + step);
      }
    };
  }

  // QC-058: the payload is translated once, here, so every chart, KPI,
  // filter and preset below reads in the chosen language without each
  // component knowing about it.
  const board = useMemo(
    () => translatePayload(dashboard, language),
    [dashboard, language]
  );

  const activeKey = view || board?.default_view || "";

  const activeView = useMemo(() => {
    if (!board) {
      return null;
    }
    const raw =
      board.views?.[view] ||
      board.views?.[board.default_view] ||
      null;
    return applyFilters(
      raw,
      `view:${activeKey}`,
      board.filters,
      picked,
      t("Others")
    );
  }, [board, view, activeKey, picked, t]);

  const sideTop = useMemo(
    () =>
      applyFilters(
        board?.side?.top,
        "side:top",
        board?.filters,
        picked,
        t("Others")
      ),
    [board, picked, t]
  );

  const sideBottom = useMemo(
    () =>
      applyFilters(
        board?.side?.bottom,
        "side:bottom",
        board?.filters,
        picked,
        t("Others")
      ),
    [board, picked, t]
  );

  async function runSimulation() {
    if (!board?.simulator?.action || simBusy) {
      return;
    }

    setSimBusy(true);
    setSimError("");

    try {
      const action = board.simulator.action;
      let body = { ...values };

      if (action === "calculate_collection_scenario") {
        body = {
          customer_name:
            board.simulator.submit_data?.customer_name || "Customer A",
          cash_to_collect_idr_mn: Number(values.cash_to_collect_idr_mn || 0),
          discount_pct: Number(values.discount_pct || 0),
        };
      } else if (action === "simulate_finance") {
        body = {
          price: Number(values.price || 0),
          cost: Number(values.cost || 0),
          vol: Number(values.vol || 0),
          fx: Number(values.fx || 0),
          opex: Number(values.opex || 0),
          scope,
          // Same EBITDA margin target the KPI card shows.
          target: board.simulator.baseline?.target ?? 0.15,
        };
      } else if (action === "simulate_leakage") {
        const baseline = board.simulator.baseline || {};
        body = {
          hold: Number(values.hold || 0),
          dupRec: Number(values.dupRec || 0),
          ovRec: Number(values.ovRec || 0),
          duplicates_amount: baseline.duplicates_amount,
          overbill_amount: baseline.overbill_amount,
          other_blocked: baseline.other_blocked,
          at_risk: baseline.at_risk,
        };
      } else if (action === "simulate_cashflow") {
        body = {
          accelerate_collection_idr_mn: Number(
            values.accelerate_collection_idr_mn || 0,
          ),
          defer_payment_idr_mn: Number(values.defer_payment_idr_mn || 0),
          credit_line_draw_idr_mn: Number(values.credit_line_draw_idr_mn || 0),
          hedge_usd: Number(values.hedge_usd || 0),
        };
      }

      const result = await recalculateDashboardSimulation(action, body);
      setSimResult(result);
    } catch (requestError) {
      setSimError(requestError.message || "Simulation recalculation failed.");
    } finally {
      setSimBusy(false);
    }
  }

  return (
    <section className="workboard" data-testid="workboard">
      {loading ? (
        <DashboardSkeleton label={`Loading ${agentName} dashboard`} />
      ) : error || !board ? (
        <div className="workboard-status error" role="alert">
          {error || "Dashboard unavailable."}
        </div>
      ) : (
        <>
          <div className="kpi-row" data-testid="kpi-row">
            {(board.kpis || []).map((kpi) => {
              const status = kpi.status || (kpi.alert ? "bad" : "good");
              const hasProgress = typeof kpi.progress === "number";
              const hasTrend =
                Array.isArray(kpi.trend) && kpi.trend.length >= 2;

              return (
                <button
                  key={kpi.id}
                  type="button"
                  className={
                    "kpi-tile status-" +
                    status +
                    (view === kpi.view ? " on" : "")
                  }
                  data-testid={`kpi-${kpi.id}`}
                  title={`What ${kpi.label} means`}
                  onClick={(event) => {
                    setView(kpi.view);
                    openInfo(`tile:${kpi.id}`, event, {
                      context: [kpi.value, kpi.unit, kpi.delta]
                        .filter(Boolean)
                        .join(" "),
                      payload: kpi,
                    });
                  }}
                >
                  <span className="kpi-cue">
                    <SparkIcon />
                    <span>Insight</span>
                  </span>

                  <span className="kpi-top">
                    <span className="kpi-status-dot" aria-hidden="true" />
                    <span className="kpi-label">{kpi.label}</span>
                  </span>

                  <strong
                    className="kpi-value"
                    data-testid={`kpi-${kpi.id}-value`}
                  >
                    {kpi.value}
                    {kpi.unit ? (
                      <span className="kpi-unit"> {kpi.unit}</span>
                    ) : null}
                  </strong>

                  <span className="kpi-delta">{kpi.delta}</span>

                  {hasTrend ? (
                    <KpiSparkline points={kpi.trend} />
                  ) : hasProgress ? (
                    <span
                      className="kpi-progress"
                      title={`${Math.round(kpi.progress * 100)}% of target`}
                    >
                      <span
                        className="kpi-progress-fill"
                        style={{
                          width: `${Math.min(100, kpi.progress * 100)}%`,
                        }}
                      />
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>

          <div className="board-controls">
            <FilterBar
              t={t}
              definitions={board.filters}
              picked={picked}
              onPick={(id, value) => {
                setPicked((current) => ({ ...current, [id]: value }));
                // Bring the panel the filter acts on into focus, or the
                // control appears to do nothing. Clearing does not move the
                // board — that would yank the view away mid-read.
                if (value) {
                  const definition = (board.filters || []).find(
                    (item) => item.id === id
                  );
                  const target = focusFor(definition, `view:${activeKey}`);
                  if (target) {
                    setView(target);
                  }
                }
              }}
              onClear={() => setPicked({})}
            />

          </div>

          <div
            className="workboard-mid"
            style={{ "--board-main": `${split}%` }}
          >
            <InfoTarget
              as="article"
              className="focus-card"
              testId="focus-panel"
              infoKey={`view:${view || board.default_view}`}
              agentId={agentId}
              onOpen={openInfo}
            >
              <FocusBody view={activeView} t={t} />
            </InfoTarget>

            {/* Slide to trade main-chart width against the side panels.
                Double-click restores the default split. */}
            <div
              className="board-resize-handle"
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize charts"
              aria-valuenow={Math.round(split)}
              aria-valuemin={BOARD_SPLIT_MIN}
              aria-valuemax={BOARD_SPLIT_MAX}
              tabIndex={0}
              title="Drag to resize · double-click to reset"
              data-testid="board-resize-handle"
              onMouseDown={(event) =>
                startResize(event, {
                  axis: "x",
                  set: (pct) => setSplit(clampSplit(pct)),
                  save: saveSplit,
                })
              }
              onKeyDown={resizeKeyHandler(split, saveSplit, [
                "ArrowLeft",
                "ArrowRight",
              ])}
              onDoubleClick={() => saveSplit(BOARD_SPLIT_DEFAULT)}
            />

            <div
              className="side-col"
              data-testid="side-panels"
              style={{ "--side-top": `${sideSplit}%` }}
            >
              <InfoTarget
                as="article"
                className="side-card"
                infoKey="side:top"
                agentId={agentId}
                onOpen={openInfo}
              >
                <FocusBody view={sideTop} t={t} compact />
              </InfoTarget>

              {/* Same slider, one axis over: trade height between the two
                  side charts. Every agent puts a chart worth resizing up
                  there — the GM pool, the ageing mix, the leakage mix. */}
              <div
                className="side-resize-handle"
                role="separator"
                aria-orientation="horizontal"
                aria-label="Resize side charts"
                aria-valuenow={Math.round(sideSplit)}
                aria-valuemin={SIDE_SPLIT_MIN}
                aria-valuemax={SIDE_SPLIT_MAX}
                tabIndex={0}
                title="Drag to resize · double-click to reset"
                data-testid="side-resize-handle"
                onMouseDown={(event) =>
                  startResize(event, {
                    axis: "y",
                    set: (pct) => setSideSplit(clampSideSplit(pct)),
                    save: saveSideSplit,
                  })
                }
                onKeyDown={resizeKeyHandler(sideSplit, saveSideSplit, [
                  "ArrowUp",
                  "ArrowDown",
                ])}
                onDoubleClick={() => saveSideSplit(SIDE_SPLIT_DEFAULT)}
              />

              <InfoTarget
                as="article"
                className="side-card"
                infoKey="side:bottom"
                agentId={agentId}
                onOpen={openInfo}
              >
                <FocusBody view={sideBottom} t={t} compact />
              </InfoTarget>
            </div>
          </div>

          <WhatIfBar
            t={t}
            simulator={board.simulator}
            values={values}
            scope={scope}
            setScope={setScope}
            onChange={(id, value) =>
              setValues((current) => ({
                ...current,
                [id]: value,
              }))
            }
            onCalculate={runSimulation}
            busy={simBusy}
            error={simError}
            result={simResult}
            onPreset={applyPreset}
            onReset={resetLevers}
            agentId={agentId}
            onOpenInfo={openInfo}
          />
        </>
      )}

      {info ? (
        <InfoCard
          entry={info.entry}
          anchor={info.anchor}
          context={info.context}
          busy={insightBusy}
          onClose={() => setInfo(null)}
          onContinue={() => {
            setInfo(null);
            onAskInsight?.({
              infoKey: info.key,
              entry: info.entry,
              context: info.context,
              kpi: info.payload,
            });
          }}
        />
      ) : null}
    </section>
  );
}

/**
 * Wraps a board panel so a click opens its info card. Panels with
 * no registry entry render as a plain element — no cursor, no
 * handler — so an unmapped chart is visibly inert rather than dead.
 */
function InfoTarget({
  as: Tag = "div",
  className,
  testId,
  infoKey,
  agentId,
  onOpen,
  children,
}) {
  const entry = findInfo(agentId, infoKey);

  if (!entry) {
    return (
      <Tag className={className} data-testid={testId}>
        {children}
      </Tag>
    );
  }

  return (
    <Tag
      className={`${className} has-info`}
      data-testid={testId}
      role="button"
      tabIndex={0}
      title={`What "${entry.el}" means`}
      onClick={(event) => onOpen(infoKey, event)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(infoKey, event);
        }
      }}
    >
      {children}
      <span className="info-badge" aria-hidden="true">
        ⓘ
      </span>
    </Tag>
  );
}

function SparkIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="12"
      height="12"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M12 2.5l1.9 4.9 4.9 1.9-4.9 1.9L12 16l-1.9-4.8L5.2 9.3l4.9-1.9L12 2.5zm6.5 10l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9.9-2.3z"
      />
    </svg>
  );
}

function KpiSparkline({ points }) {
  if (!Array.isArray(points) || points.length < 2) {
    return null;
  }

  const width = 100;
  const height = 24;
  const pad = 2;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = (width - pad * 2) / (points.length - 1);

  const coords = points.map((value, index) => {
    const x = pad + index * step;
    const y = pad + (height - pad * 2) * (1 - (value - min) / range);
    return [x, y];
  });

  const line = coords
    .map(
      ([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`,
    )
    .join(" ");

  const last = coords[coords.length - 1];
  const area = `${line} L ${last[0].toFixed(1)} ${height} L ${coords[0][0].toFixed(1)} ${height} Z`;

  return (
    <svg
      className="kpi-spark"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path className="kpi-spark-area" d={area} />
      <path className="kpi-spark-line" d={line} />
      <circle className="kpi-spark-dot" cx={last[0]} cy={last[1]} r="2.2" />
    </svg>
  );
}

function FocusBody({ view, t, compact = false }) {
  if (!view) {
    return <p className="workboard-empty">{t("No view data.")}</p>;
  }

  // QC-043: say the filter emptied it. An all-zero chart is what QC-024
  // reported, and a filter must not be able to recreate that reading.
  if (isEmptyAfterFilter(view)) {
    return (
      <p className="workboard-empty">
        {t("No rows match the current filter.")}
      </p>
    );
  }

  if (view.table) {
    return (
      <div className="focus-table-wrap">
        <div className="focus-title-row">
          <div>
            <h3>{view.title}</h3>
            {/* QC-035: a worklist without a period is as ambiguous as a bar
                without one. */}
            {view.period ? (
              <p className="focus-period">{view.period}</p>
            ) : null}
          </div>
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
      <ChartRenderer data={view} variant={compact ? "compact" : "fill"} />
    </div>
  );
}

// QC-043. Only the dimensions the payload says it can be sliced by appear —
// this dataset has no entity, store or month column, and an empty control
// would imply it did.
function FilterBar({ t, definitions, picked, onPick, onClear }) {
  if (!definitions?.length) {
    return null;
  }

  const activeCount = definitions.filter((d) => picked?.[d.id]).length;

  return (
    <div className="filter-bar" data-testid="filter-bar">
      {definitions.map((definition) => (
        <label key={definition.id} className="filter-control">
          <span>{definition.label}</span>
          <select
            value={picked?.[definition.id] || ""}
            onChange={(event) => onPick(definition.id, event.target.value)}
          >
            <option value="">{t("All")}</option>
            {definition.options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      ))}

      {activeCount > 0 ? (
        <button type="button" className="filter-clear" onClick={onClear}>
          Clear {activeCount} filter{activeCount > 1 ? "s" : ""}
        </button>
      ) : null}
    </div>
  );
}

// QC-052 presets and QC-059 reset to baseline.
//
// Presets come from the payload, not from here: only the agent knows which
// lever settings are worth a button.
function PresetBar({ t, presets, busy, atBaseline, onPreset, onReset }) {
  if (!presets?.length && atBaseline) {
    return null;
  }

  return (
    <div className="preset-bar" data-testid="preset-bar">
      <span className="whatif-label">{t("Presets")}</span>

      {(presets || []).map((preset) => (
        <button
          key={preset.id}
          type="button"
          className="preset-btn"
          title={preset.note}
          disabled={busy}
          onClick={() => onPreset(preset)}
        >
          {t(preset.label)}
        </button>
      ))}

      <button
        type="button"
        className="preset-btn preset-btn--quiet"
        data-testid="reset-to-baseline"
        disabled={busy || atBaseline}
        onClick={onReset}
      >
        {t("Reset to baseline")}
      </button>
    </div>
  );
}

function WhatIfBar({
  t,
  simulator,
  values,
  scope,
  setScope,
  onChange,
  onCalculate,
  busy,
  error,
  result,
  onPreset,
  onReset,
  agentId,
  onOpenInfo,
}) {
  if (!simulator) {
    return null;
  }

  const summary = summarizeResult(simulator.action, result, simulator);
  const inputs = simulator.inputs || [];
  const atBaseline = inputs.every(
    (input) =>
      Number(values[input.id] ?? input.default ?? 0) ===
      Number(input.default ?? 0)
  );

  return (
    <section className="whatif-bar" data-testid="whatif-bar">
      <div className="whatif-top">
        <strong>{t("What-if simulator")}</strong>
        <div className="whatif-controls">
          {Array.isArray(simulator.scope_options) &&
            simulator.scope_options.map((option) => (
              <button
                key={option}
                type="button"
                className={"scope-btn" + (scope === option ? " on" : "")}
                onClick={() => setScope(option)}
              >
                {t(option === "all" ? "All lines" : "FX lines")}
              </button>
            ))}
          <button
            type="button"
            className={"calc-btn" + (busy ? " is-busy" : "")}
            data-testid="calculate-simulation"
            disabled={busy}
            onClick={onCalculate}
          >
            {t(busy ? "Running scenario…" : "Calculate simulation")}
          </button>
        </div>
      </div>

      <PresetBar
        t={t}
        presets={simulator.presets}
        busy={busy}
        atBaseline={atBaseline}
        onPreset={onPreset}
        onReset={onReset}
      />

      <div className={"whatif-grid" + (busy ? " is-loading" : "")}>
        <div className="whatif-levers">
          <div className="whatif-label">{t("Levers")}</div>
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
                    onChange(input.id, Number(event.currentTarget.value))
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
                    onChange(input.id, Number(event.currentTarget.value))
                  }
                />
              </div>
            </label>
          ))}
        </div>

        {busy ? (
          <WhatIfStatsSkeleton />
        ) : (
          <div className="whatif-stats" data-testid="whatif-stats">
            {summary.stats.map((stat) => (
              <InfoTarget
                key={stat.label}
                className="whatif-stat"
                infoKey={`stat:${stat.id}`}
                agentId={agentId}
                onOpen={(key, event) =>
                  onOpenInfo(key, event, {
                    context: [stat.value, stat.delta]
                      .filter(Boolean)
                      .join(" · "),
                  })
                }
              >
                <span>{stat.label}</span>
                <strong data-testid={`stat-${stat.id}`}>{stat.value}</strong>
                <small className={stat.tone}>{stat.delta}</small>
              </InfoTarget>
            ))}

            {/* This is where a run gets drawn. It was removed when the board's
                own charts redrew on the scenario — but that feature is gone,
                so without this a calculation produced numbers and no picture
                at all. */}
            {summary.chart ? (
              <InfoTarget
                className="whatif-mini-chart"
                infoKey="simchart"
                agentId={agentId}
                onOpen={onOpenInfo}
              >
                <ChartRenderer data={summary.chart} variant="compact" />
              </InfoTarget>
            ) : null}
          </div>
        )}

        <InfoTarget
          className="whatif-gauge"
          testId="whatif-gauge"
          infoKey="gauge"
          agentId={agentId}
          onOpen={(key, event) =>
            onOpenInfo(key, event, {
              context: busy ? "" : summary.gauge.center,
            })
          }
        >
          <div className="whatif-label">
            {simulator.gauge_label || "Scenario"}
          </div>
          {busy ? (
            <WhatIfGaugeSkeleton />
          ) : (
            <>
              <div className="gauge-center" data-testid="gauge-center">
                {summary.gauge.center}
              </div>
              <p data-testid="gauge-txt">{summary.gauge.txt}</p>
            </>
          )}
        </InfoTarget>
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
        tone: "",
      },
      {
        id: "b",
        label: "Impact",
        value: "—",
        delta: "Set levers to begin",
        tone: "",
      },
      {
        id: "c",
        label: "Target",
        value: "—",
        delta: "Results after run",
        tone: "",
      },
    ],
    chart: null,
    gauge: {
      center: "—",
      txt: "Run scenario to update",
    },
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
          tone: stats.delta_margin_pts >= 0 ? "good" : "bad",
        },
        {
          id: "ebitda",
          label: "EBITDA",
          value: formatNumber(stats.ebitda_idr_mn),
          delta: `${stats.delta_ebitda_idr_mn >= 0 ? "+" : ""}${formatNumber(stats.delta_ebitda_idr_mn)} mn`,
          tone: stats.delta_ebitda_idr_mn >= 0 ? "good" : "bad",
        },
        {
          id: "target",
          label: "vs Target",
          value: `${stats.vs_target_pts} pts`,
          delta: stats.vs_target_pts >= 0 ? "at/above" : "below",
          tone: stats.vs_target_pts >= 0 ? "good" : "bad",
        },
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
            value: round1((baseline.margin || 0) * 100),
          },
          {
            label: "Scenario",
            value: round1((scenario.margin || 0) * 100),
          },
        ],
      },
      gauge: result.gauge || empty.gauge,
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
          tone: payload.dso_change_days <= 0 ? "good" : "bad",
        },
        {
          id: "cash",
          label: "Cash collected",
          value: formatNumber(payload.cash_collected_idr_mn),
          delta: "IDR mn",
          tone: "good",
        },
        {
          id: "discount",
          label: "Discount cost",
          value: formatNumber(payload.discount_cost_idr_mn),
          delta: `${payload.discount_pct}%`,
          tone: "",
        },
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
            value: Number(payload.dso_after_days || 0),
          },
        ],
      },
      gauge: {
        center: `${formatNumber(payload.dso_after_days)}d`,
        txt: `Target ${baseline.target_dso}d`,
      },
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
          tone: payload.week5_headroom_idr_mn >= 0 ? "good" : "bad",
        },
        {
          id: "below",
          label: "Weeks below buffer",
          value: String(payload.weeks_below_buffer),
          delta: `buffer ${formatNumber(payload.minimum_buffer_idr_mn)}`,
          tone: payload.weeks_below_buffer === 0 ? "good" : "bad",
        },
        {
          id: "fx",
          label: "FX downside avoided",
          value: formatNumber(payload.fx_downside_avoided_idr_mn),
          delta: `premium ${formatNumber(payload.forward_premium_idr_mn)}`,
          tone: "good",
        },
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
            value: Number(payload.week5_cash_idr_mn || 0),
          },
        ],
      },
      gauge: {
        center: `${formatNumber(payload.hedge_coverage_pct)}%`,
        txt: "Hedge coverage",
      },
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
          tone: "good",
        },
        {
          id: "blocked",
          label: "Blocked",
          value: formatNumber(result.blocked),
          delta: "never leaves",
          tone: "good",
        },
        {
          id: "recovered",
          label: "Recovered",
          value: formatNumber(result.recovered),
          delta: "clawed back",
          tone: "good",
        },
      ],
      chart: {
        title: "Protected vs at risk",
        chart_type: "bar",
        data: [
          { label: "At risk", value: Number(result.at_risk || 0) },
          {
            label: "Protected",
            value: Number(result.total_protected || 0),
          },
        ],
      },
      gauge: result.gauge || empty.gauge,
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
    maximumFractionDigits: 2,
  });
}

function round1(value) {
  return Math.round(Number(value) * 10) / 10;
}
