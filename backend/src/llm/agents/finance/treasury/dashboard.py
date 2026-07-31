"""Treasury dashboard payload."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_blocks import (
    _bar_chart,
    _call_with_timeout,
    _donut_chart,
    _enriched,
    _filters,
    _fmt,
    _line_chart,
    _pct,
    _row_get,
    _table_view,
    _waterfall_chart,
)
from src.llm.agents.finance.treasury.tools.treasury_data import (
    get_cashflow_baseline,
)


def _treasury_dashboard(baseline: dict[str, Any]) -> dict[str, Any]:
    weeks = baseline.get("weekly_positions") or []
    buffer = float(baseline.get("minimum_buffer_idr_mn") or 0)
    net_usd = float(baseline.get("net_usd_exposure") or 0)
    recommended_hedge = float(baseline.get("recommended_hedge_usd") or 0)

    week5 = next(
        (w for w in weeks if int(w.get("week_number") or 0) == 5),
        None,
    )
    w5_cash = float((week5 or {}).get("closing_cash_idr_mn") or 0)
    w5_headroom = float((week5 or {}).get("headroom_idr_mn") or (w5_cash - buffer))

    points = [
        {
            "label": f"W{int(w['week_number'])}",
            "value": float(w.get("closing_cash_idr_mn") or 0),
        }
        for w in weeks
    ]

    spot = float(baseline.get("spot_rate_idr_per_usd") or 0)
    adverse = float(baseline.get("adverse_rate_idr_per_usd") or 0)
    fx_loss = 0.0
    if spot > 0 and net_usd:
        # adverse vs spot on net USD exposure → IDR million
        fx_loss = abs(net_usd) * abs(adverse - spot) / 1_000_000.0

    driver = baseline.get("customer_delay_driver") or {}
    max_accel = float(driver.get("amount_idr_mn") or 8000)
    defer = baseline.get("deferrable_payment_driver") or {}
    max_defer = float(defer.get("amount_idr_mn") or 3000)

    # Forward points are not stored on the baseline; without them the premium
    # cannot be derived, so fall back to the mockup's 170 IDR/USD and say so.
    forward_points = float(baseline.get("forward_points_idr_per_usd") or 0)
    premium_is_live = forward_points > 0
    if not premium_is_live:
        forward_points = 170.0

    def _avoided(usd: float) -> float:
        if spot <= 0 or not usd:
            return 0.0
        return abs(usd) * abs(adverse - spot) / 1_000_000.0

    def _premium(usd: float) -> float:
        return abs(usd) * forward_points / 1_000_000.0

    # One scale for every USD figure in the KPI row. Mixing "3.3 M USD" with
    # "2,000,000 USD" made two comparable numbers look unrelated.
    _usd_millions = max(abs(net_usd), abs(recommended_hedge)) >= 1_000_000
    _usd_unit = "M USD" if _usd_millions else "USD"
    _usd_suffix = "M" if _usd_millions else ""

    def _usd(value: float) -> str:
        return f"{value / 1_000_000:.1f}" if _usd_millions else _fmt(value)

    # What the adverse move still costs after the recommended forward cover.
    residual_fx_loss = _avoided(max(0.0, abs(net_usd) - abs(recommended_hedge)))

    half_hedge = recommended_hedge / 2
    option_rows = [
        [
            "A · Do nothing",
            _fmt(0),
            _fmt(0),
            "No cash out · full exposure open",
        ],
        [
            "B · Forward-cover (recommended)",
            _fmt(_avoided(recommended_hedge)),
            _fmt(_premium(recommended_hedge)),
            "No cash out · rate locked today",
        ],
        [
            "C · Buy USD spot now",
            _fmt(_avoided(recommended_hedge)),
            _fmt(0),
            f"Cash out {_fmt(recommended_hedge * spot / 1_000_000.0)} mn now "
            "· worsens Week 5",
        ],
        [
            "D · Hedge 50%",
            _fmt(_avoided(half_hedge)),
            _fmt(_premium(half_hedge)),
            "No cash out · half the exposure still open",
        ],
    ]

    kpis = [
        {
            "id": "w5",
            "view": "forecast",
            "label": "Week 5 cash",
            "value": _fmt(w5_cash),
            "unit": "mn",
            "delta": f"headroom {_fmt(w5_headroom)} vs buffer",
            "alert": w5_headroom < 0,
            # Real weekly closing-cash series for a sparkline.
            "trend": [round(p["value"], 2) for p in points],
        },
        {
            "id": "buffer",
            "view": "forecast",
            "label": "Min buffer",
            "value": _fmt(buffer),
            "unit": "mn",
            "delta": "policy floor",
            "alert": False,
        },
        {
            "id": "usd",
            "view": "exposure",
            "label": "Net USD exposure",
            "value": _usd(net_usd),
            "unit": _usd_unit,
            "delta": (
                f"recommended hedge {_usd(recommended_hedge)}{_usd_suffix}"
            ),
            "alert": False,
        },
        {
            "id": "fx_loss",
            "view": "fx",
            "label": "FX loss if nothing",
            "value": _fmt(fx_loss),
            "unit": "mn",
            "delta": "at adverse rate",
            "alert": fx_loss > 0,
        },
        {
            "id": "hedge",
            "view": "options",
            "label": "Recommended hedge",
            "value": _usd(recommended_hedge),
            "unit": _usd_unit,
            "delta": "forward-cover",
            "alert": False,
        },
    ]

    views = {
        "forecast": {
            **_line_chart(
                "Cash forecast · closing by week",
                points,
                tag="liquidity",
                target=buffer,
                target_label=f"Buffer {_fmt(buffer)}",
                note=(
                    f"Week 5 closing {_fmt(w5_cash)} vs buffer {_fmt(buffer)}."
                ),
            ),
        },
        "exposure": {
            **_bar_chart(
                "Net USD exposure",
                [
                    {"label": "Net USD", "value": round(net_usd, 2)},
                    {
                        "label": "Recommended hedge",
                        "value": round(recommended_hedge, 2),
                    },
                ],
                y_axis_title="USD",
                tag="currency",
            ),
        },
        # A zero "Base" bar next to a value bar reads as a failed render and
        # says nothing. The live comparison is unhedged loss vs the loss left
        # over after the recommended forward cover.
        "fx": {
            **_bar_chart(
                "FX loss at the adverse rate",
                [
                    {"label": "Do nothing", "value": round(fx_loss, 2)},
                    {
                        "label": f"Hedge {_usd(recommended_hedge)}{_usd_suffix}",
                        "value": round(residual_fx_loss, 2),
                    },
                ],
                tag="currency",
                note=(
                    f"Net exposure {_usd(net_usd)}{_usd_suffix} at "
                    f"{_fmt(adverse)} vs spot {_fmt(spot)}. Forward cover "
                    f"leaves {_usd(max(0.0, net_usd - recommended_hedge))}"
                    f"{_usd_suffix} open."
                ),
            ),
        },
        "options": _table_view(
            "Agent option comparison · hedge the exposure",
            ["Option", "Avoided", "Premium", "Liquidity impact"],
            option_rows,
            tag="decision",
            note=(
                "Amounts in IDR mn."
                + (
                    ""
                    if premium_is_live
                    else " Premium assumes a 170 IDR/USD forward spread; this "
                    "baseline stores no forward points."
                )
            ),
        ),
    }

    side = {
        # Not `views:exposure` with shorter labels — that chart already pairs
        # net against hedge. This splits the same exposure into the part the
        # forward covers and the part still open, so the two bars add to net.
        "top": {
            **_bar_chart(
                "Exposure covered vs still open",
                [
                    {
                        "label": "Covered",
                        "value": round(min(recommended_hedge, net_usd), 2),
                    },
                    {
                        "label": "Open",
                        "value": round(
                            max(0.0, net_usd - recommended_hedge), 2
                        ),
                    },
                ],
                y_axis_title="USD",
                tag="currency",
            ),
        },
        "bottom": {
            **_bar_chart(
                "Week 5 vs buffer",
                [
                    {"label": "Buffer", "value": round(buffer, 2)},
                    {"label": "Week 5", "value": round(w5_cash, 2)},
                ],
                tag="liquidity",
            ),
        },
    }

    # QC-043 — the forecast is weekly, so the week is the dimension.
    filters = _filters(views, side, (
        ("week", "Week", "view:forecast", ("view:forecast",), 0),
        ("option", "Hedge option", "view:options", ("view:options",), 0),
    ))

    return {
        "agent": "treasury",
        # QC-035: the span these figures cover, stamped onto every
        # chart by _enriched().
        "period": baseline.get("period"),
        "filters": filters,
        "import_batch_id": baseline.get("import_batch_id"),
        "default_view": "forecast",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            # QC-052: named scenarios, so a presenter reaches the point
            # without dragging four sliders live.
            "presets": [
                {
                    "id": "close_the_gap",
                    "label": "Close the Week 5 gap",
                    "note": "Defer the one deferrable payable into Week 6.",
                    "values": {"defer_payment_idr_mn": max_defer},
                },
                {
                    "id": "collect_early",
                    "label": "Collect AR-012 early",
                    "note": "Pull the delayed receivable back into Week 5.",
                    "values": {"accelerate_collection_idr_mn": max_accel},
                },
                {
                    "id": "full_cover",
                    "label": "Cover the exposure in full",
                    "note": "Hedge every open USD, not just the recommendation.",
                    "values": {"hedge_usd": net_usd},
                },
            ],
            "action": "simulate_cashflow",
            "gauge_label": "% of USD exposure covered",
            "inputs": [
                {
                    "id": "accelerate_collection_idr_mn",
                    "label": "Accelerate collection",
                    "min": 0,
                    "max": max(max_accel, 1),
                    "step": 100,
                    "default": 0,
                    "unit": "IDR mn",
                },
                {
                    "id": "defer_payment_idr_mn",
                    "label": "Defer payment",
                    "min": 0,
                    "max": max(max_defer, 1),
                    "step": 100,
                    "default": 0,
                    "unit": "IDR mn",
                },
                {
                    "id": "credit_line_draw_idr_mn",
                    "label": "Credit line draw",
                    "min": 0,
                    "max": 5000,
                    "step": 100,
                    "default": 0,
                    "unit": "IDR mn",
                },
                {
                    "id": "hedge_usd",
                    "label": "Forward-cover USD",
                    "min": 0,
                    "max": max(net_usd, 1),
                    "step": 10000,
                    "default": min(recommended_hedge, net_usd)
                    if net_usd
                    else 0,
                    "unit": "USD",
                },
            ],
            "baseline": {
                "week5_cash": w5_cash,
                "buffer": buffer,
                "net_usd_exposure": net_usd,
            },
        },
    }


# ---------------------------------------------------------------------------
# Finance (flexible column mapping + illustrative sim base)
# ---------------------------------------------------------------------------


def build() -> dict[str, Any]:
    return _enriched(
        _treasury_dashboard(_call_with_timeout(get_cashflow_baseline))
    )
