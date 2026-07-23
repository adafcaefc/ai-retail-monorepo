"""Build dashboard workboard payloads (KPI / focus / side / simulator) from DB tools."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from src.llm.tools.finance_data import (
    get_cashflow_baseline,
    get_collections_snapshot,
    get_financial_performance_snapshot,
    get_payment_leakage_snapshot,
)

_DB_TIMEOUT_SEC = 15.0


def _call_with_timeout(fn: Callable[[], Any], timeout: float = _DB_TIMEOUT_SEC) -> Any:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        return future.result(timeout=timeout)


def build_dashboard(agent: str) -> dict[str, Any]:
    key = agent.strip().lower()
    if key == "collections":
        return _collections_dashboard(
            _call_with_timeout(get_collections_snapshot)
        )
    if key == "treasury":
        return _treasury_dashboard(_call_with_timeout(get_cashflow_baseline))
    if key == "finance":
        return _finance_dashboard(
            _call_with_timeout(get_financial_performance_snapshot)
        )
    if key == "leakage":
        return _leakage_dashboard(
            _call_with_timeout(get_payment_leakage_snapshot)
        )
    raise ValueError(f"Unsupported dashboard agent: {agent}")


def _fmt(n: float, digits: int = 0) -> str:
    if digits <= 0:
        return f"{round(n):,}"
    return f"{n:,.{digits}f}"


def _pct(n: float, digits: int = 1) -> str:
    return f"{n * 100:.{digits}f}%" if abs(n) <= 2 else f"{n:.{digits}f}%"


def _bar_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    y_axis_title: str = "IDR mn",
    note: str = "",
    tag: str = "",
    target: float | None = None,
    target_label: str | None = None,
) -> dict[str, Any]:
    chart: dict[str, Any] = {
        "title": title,
        "chart_type": "bar",
        "y_axis_title": y_axis_title,
        "tag": tag,
        "data": rows,
    }
    if note:
        chart["note"] = note
    if target is not None:
        chart["target"] = target
        if target_label:
            chart["target_label"] = target_label
    return chart


def _line_chart(
    title: str,
    points: list[dict[str, Any]],
    *,
    y_axis_title: str = "IDR mn",
    note: str = "",
    tag: str = "",
    target: float | None = None,
    target_label: str | None = None,
) -> dict[str, Any]:
    chart: dict[str, Any] = {
        "title": title,
        "chart_type": "line",
        "x_axis_title": "Week",
        "y_axis_title": y_axis_title,
        "tag": tag,
        "data": [
            {
                "legend": "Closing cash",
                "values": points,
            }
        ],
    }
    if note:
        chart["note"] = note
    if target is not None:
        chart["target"] = target
        if target_label:
            chart["target_label"] = target_label
    return chart


def _waterfall_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    note: str = "",
    tag: str = "variance",
) -> dict[str, Any]:
    return {
        "title": title,
        "chart_type": "waterfall",
        "y_axis_title": "IDR mn",
        "tag": tag,
        "note": note,
        "data": rows,
    }


def _donut_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    note: str = "",
    tag: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "chart_type": "donut",
        "tag": tag,
        "note": note,
        "data": rows,
    }


def _table_view(
    title: str,
    headers: list[str],
    rows: list[list[Any]],
    *,
    note: str = "",
    tag: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "tag": tag,
        "note": note,
        "table": {
            "headers": headers,
            "rows": rows,
        },
    }


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def _collections_dashboard(snap: dict[str, Any]) -> dict[str, Any]:
    summary = snap.get("summary") or {}
    customers = snap.get("customers") or []
    risk_tiers = snap.get("risk_tiers") or []
    worklist = snap.get("worklist") or []

    total_ar = float(summary.get("total_ar_idr_mn") or 0)
    overdue = float(summary.get("overdue_ar_idr_mn") or 0)
    overdue_pct = float(summary.get("overdue_percentage") or 0)
    dso = float(summary.get("current_dso_days") or 0)
    target_dso = float(summary.get("target_dso_days") or 47)
    cash_freed = float(summary.get("cash_freed_at_target_idr_mn") or 0)
    high_risk = float(summary.get("high_risk_provision_idr_mn") or 0)
    if not high_risk:
        for tier in risk_tiers:
            if str(tier.get("risk_tier", "")).lower() == "high":
                high_risk = float(tier.get("exposure_idr_mn") or 0)
                break

    aging = {
        "Current": 0.0,
        "1-30": 0.0,
        "31-60": 0.0,
        "61-90": 0.0,
        "90+": 0.0,
    }
    for row in customers:
        aging["Current"] += float(row.get("current_idr_mn") or 0)
        # customer query may not include current_idr_mn — recompute from tool fields
        if "current_idr_mn" not in row:
            pass
        aging["1-30"] += float(row.get("overdue_1_30_idr_mn") or 0)
        aging["31-60"] += float(row.get("overdue_31_60_idr_mn") or 0)
        aging["61-90"] += float(row.get("overdue_61_90_idr_mn") or 0)
        aging["90+"] += float(row.get("overdue_90_plus_idr_mn") or 0)

    # If current missing from SELECT, infer from summary
    if aging["Current"] == 0 and summary.get("current_ar_idr_mn") is not None:
        aging["Current"] = float(summary["current_ar_idr_mn"])

    aging_rows = [
        {"label": label, "value": round(value, 2)}
        for label, value in aging.items()
    ]

    top_customer = worklist[0] if worklist else {}
    customer_name = str(
        top_customer.get("customer_name")
        or "PT Anugerah Prima (Customer A)"
    )
    max_pull = float(top_customer.get("overdue_idr_mn") or 10000)

    kpis = [
        {
            "id": "ar",
            "view": "aging",
            "label": "AR outstanding",
            "value": _fmt(total_ar),
            "unit": "mn",
            "delta": "IDR book",
            "alert": False,
        },
        {
            "id": "overdue",
            "view": "aging",
            "label": "Overdue",
            "value": _fmt(overdue),
            "unit": "mn",
            "delta": f"{overdue_pct * 100:.0f}% of AR"
            if overdue_pct <= 1
            else f"{overdue_pct:.0f}% of AR",
            "alert": overdue > 0,
        },
        {
            "id": "dso",
            "view": "prize",
            "label": "DSO",
            "value": f"{dso:.0f}d",
            "unit": "",
            "delta": f"target {target_dso:.0f}",
            "alert": dso > target_dso,
        },
        {
            "id": "prize",
            "view": "prize",
            "label": "Cash freed at target",
            "value": _fmt(cash_freed),
            "unit": "mn",
            "delta": "the prize",
            "alert": False,
        },
        {
            "id": "high_risk",
            "view": "tiers",
            "label": "High-risk exposure",
            "value": _fmt(high_risk),
            "unit": "mn",
            "delta": "provision / high tier",
            "alert": high_risk > 0,
        },
    ]

    views: dict[str, Any] = {
        "aging": {
            **_bar_chart(
                "Receivables aging (IDR mn)",
                aging_rows,
                tag="aging",
                note=f"Overdue {_fmt(overdue)} of {_fmt(total_ar)}.",
            ),
        },
        "worklist": _table_view(
            "Who to chase first · ranked worklist",
            [
                "Customer",
                "Overdue",
                "Bucket",
                "Tier",
                "Exp rec",
            ],
            [
                [
                    str(w.get("customer_name") or ""),
                    _fmt(float(w.get("overdue_idr_mn") or 0)),
                    str(w.get("oldest_aging_bucket") or ""),
                    str(w.get("risk_tier") or ""),
                    _fmt(float(w.get("expected_recovery_idr_mn") or 0)),
                ]
                for w in worklist[:8]
            ],
            tag="worklist",
        ),
        "prize": {
            **_bar_chart(
                "The prize · DSO to cash",
                [
                    {"label": "Now", "value": round(dso, 2)},
                    {"label": "Target", "value": round(target_dso, 2)},
                ],
                y_axis_title="days",
                tag="impact",
                target=target_dso,
                target_label=f"Target {target_dso:.0f}",
                note=(
                    f"Hitting {target_dso:.0f} days frees about "
                    f"{_fmt(cash_freed)} mn."
                ),
            ),
        },
        "tiers": {
            **_bar_chart(
                "Risk exposure by tier",
                [
                    {
                        "label": str(t.get("risk_tier") or ""),
                        "value": float(t.get("exposure_idr_mn") or 0),
                    }
                    for t in risk_tiers
                ],
                tag="risk",
            ),
        },
    }

    side = {
        "top": _donut_chart(
            "Aging mix",
            aging_rows,
            tag="aging",
        ),
        "bottom": {
            **_bar_chart(
                "DSO vs target",
                [
                    {"label": "Target", "value": round(target_dso, 2)},
                    {"label": "Now", "value": round(dso, 2)},
                ],
                y_axis_title="days",
                tag="impact",
            ),
        },
    }

    return {
        "agent": "collections",
        "import_batch_id": snap.get("import_batch_id"),
        "default_view": "aging",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            "action": "calculate_collection_scenario",
            "gauge_label": f"DSO vs {target_dso:.0f}-day target",
            "submit_data": {"customer_name": customer_name},
            "inputs": [
                {
                    "id": "cash_to_collect_idr_mn",
                    "label": "Pull from customer (mn)",
                    "min": 0,
                    "max": max(max_pull, 1),
                    "step": 100,
                    "default": min(5000, max_pull) if max_pull else 0,
                    "unit": "IDR mn",
                },
                {
                    "id": "discount_pct",
                    "label": "Discount %",
                    "min": 0,
                    "max": 3,
                    "step": 0.1,
                    "default": 1,
                    "unit": "%",
                },
            ],
            "baseline": {
                "dso": dso,
                "target_dso": target_dso,
                "total_ar": total_ar,
                "daily_credit_sales": float(
                    summary.get("daily_credit_sales_idr_mn") or 0
                ),
            },
        },
        "raw": {
            "summary": summary,
            "worklist_top": top_customer,
        },
    }


# ---------------------------------------------------------------------------
# Treasury
# ---------------------------------------------------------------------------


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

    kpis = [
        {
            "id": "w5",
            "view": "forecast",
            "label": "Week 5 cash",
            "value": _fmt(w5_cash),
            "unit": "mn",
            "delta": f"headroom {_fmt(w5_headroom)} vs buffer",
            "alert": w5_headroom < 0,
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
            "value": f"{net_usd / 1_000_000:.1f}"
            if abs(net_usd) >= 1000
            else _fmt(net_usd, 0),
            "unit": "M USD" if abs(net_usd) >= 1000 else "USD",
            "delta": f"recommended hedge {_fmt(recommended_hedge)}",
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
            "value": _fmt(recommended_hedge),
            "unit": "USD",
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
        "fx": {
            **_bar_chart(
                "FX impact if we do nothing",
                [
                    {"label": "Base", "value": 0},
                    {"label": "Adverse", "value": round(fx_loss, 2)},
                ],
                tag="currency",
                note="Derived from net USD exposure and adverse vs spot rate.",
            ),
        },
        "options": _table_view(
            "Drivers used by simulation",
            ["Driver", "Counterparty", "Amount", "Week"],
            [
                [
                    "Accelerate collection",
                    str(driver.get("counterparty_name") or ""),
                    _fmt(max_accel),
                    str(
                        driver.get("expected_week")
                        or driver.get("original_week")
                        or ""
                    ),
                ],
                [
                    "Defer payment",
                    str(defer.get("counterparty_name") or ""),
                    _fmt(max_defer),
                    str(defer.get("payment_week") or ""),
                ],
            ],
            tag="decision",
        ),
    }

    side = {
        "top": {
            **_bar_chart(
                "Exposure vs hedge",
                [
                    {"label": "Net", "value": round(net_usd, 2)},
                    {"label": "Hedge", "value": round(recommended_hedge, 2)},
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

    return {
        "agent": "treasury",
        "import_batch_id": baseline.get("import_batch_id"),
        "default_view": "forecast",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
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


_FINANCE_PROD = [
    {"n": "Industrial", "qty": 130, "price": 147, "cost": 112, "fx": 1},
    {"n": "Precision", "qty": 34, "price": 400, "cost": 255, "fx": 1},
    {"n": "Standard", "qty": 230, "price": 60, "cost": 50, "fx": 0},
]
_FINANCE_OPEX = 7480.0
_FINANCE_IMP = 0.55
_FINANCE_TARGET = 0.15


def simulate_finance_scenario(
    price: float = 0,
    cost: float = 0,
    vol: float = 0,
    fx: float = 0,
    opex: float = 0,
    scope: str = "all",
) -> dict[str, Any]:
    """Deterministic what-if from mockup product model (illustrative)."""

    base = _finance_comp(0, 0, 0, 0, 0, "all")
    scen = _finance_comp(price, cost, vol, fx, opex, scope)
    return {
        "success": True,
        "illustrative": True,
        "baseline": base,
        "scenario": scen,
        "stats": {
            "scenario_margin_pct": round(scen["margin"] * 100, 2),
            "ebitda_idr_mn": round(scen["ebitda"], 2),
            "vs_target_pts": round((scen["margin"] - _FINANCE_TARGET) * 100, 2),
            "delta_ebitda_idr_mn": round(scen["ebitda"] - base["ebitda"], 2),
            "delta_margin_pts": round(
                (scen["margin"] - base["margin"]) * 100,
                2,
            ),
        },
        "gauge": {
            "ratio": scen["margin"] / _FINANCE_TARGET
            if _FINANCE_TARGET
            else 0,
            "center": f"{scen['margin'] * 100:.1f}%",
            "txt": (
                f"{round(scen['margin'] / _FINANCE_TARGET * 100)}% of target"
                f" · gap {( _FINANCE_TARGET - scen['margin']) * 100:.1f} pts"
            ),
        },
    }


def _finance_comp(
    price: float,
    cost: float,
    vol: float,
    fx: float,
    opex: float,
    scope: str,
) -> dict[str, Any]:
    rev = 0.0
    gm = 0.0
    lines: list[dict[str, Any]] = []
    for product in _FINANCE_PROD:
        apply = scope == "all" or bool(product["fx"])
        qty = product["qty"] * (1 + (vol / 100 if apply else 0))
        unit_price = product["price"] * (1 + (price / 100 if apply else 0))
        unit_cost = (
            product["cost"]
            * (1 + cost / 100)
            * (1 + fx / 100 * _FINANCE_IMP)
        )
        line_rev = qty * unit_price
        line_cost = qty * unit_cost
        rev += line_rev
        gm += line_rev - line_cost
        lines.append(
            {
                "name": product["n"],
                "rev": line_rev,
                "gm": line_rev - line_cost,
                "gm_pct": (line_rev - line_cost) / line_rev if line_rev else 0,
            }
        )
    op = _FINANCE_OPEX * (1 + opex / 100)
    ebitda = gm - op
    return {
        "rev": rev,
        "gm": gm,
        "opex": op,
        "ebitda": ebitda,
        "margin": ebitda / rev if rev else 0,
        "lines": lines,
    }


def _row_get(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered and lowered[name.lower()] is not None:
            return lowered[name.lower()]
    return None


def _finance_dashboard(snap: dict[str, Any]) -> dict[str, Any]:
    base = _finance_comp(0, 0, 0, 0, 0, "all")
    kpis_rows = snap.get("kpis") or []
    variance = snap.get("variance_drivers") or []
    profit = snap.get("profit_summary") or []
    levers = snap.get("simulator_levers") or []

    # Prefer live KPI values when recognizable; else illustrative base
    margin = base["margin"]
    ebitda = base["ebitda"]
    revenue = base["rev"]
    gm_pct = base["gm"] / base["rev"] if base["rev"] else 0
    opex_rev = base["opex"] / base["rev"] if base["rev"] else 0

    for row in kpis_rows:
        name = str(_row_get(row, "kpi_name", "name", "metric", "label") or "").lower()
        value = _row_get(row, "kpi_value", "value", "actual", "actual_value")
        if value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if "ebitda margin" in name or name == "margin":
            margin = num / 100 if num > 1 else num
        elif name == "ebitda" or name.endswith(" ebitda"):
            ebitda = num
        elif "revenue" in name:
            revenue = num
        elif "gross margin" in name:
            gm_pct = num / 100 if num > 1 else num
        elif "opex" in name:
            opex_rev = num / 100 if num > 1 else num

    waterfall_rows: list[dict[str, Any]] = []
    for row in variance:
        label = str(
            _row_get(row, "driver_name", "name", "label", "step_name") or ""
        )
        value = _row_get(row, "amount_idr_mn", "value", "amount", "variance")
        step_type = str(_row_get(row, "step_type", "type") or "step").lower()
        if not label or value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        point: dict[str, Any] = {"label": label, "value": num}
        if step_type in {"total", "base", "end"}:
            point["type"] = "total"
        waterfall_rows.append(point)

    if not waterfall_rows:
        waterfall_rows = [
            {"label": "Bud", "value": 7200, "type": "total"},
            {"label": "Vol", "value": 1341},
            {"label": "Mix", "value": -1491},
            {"label": "Price", "value": -390},
            {"label": "Cost·FX", "value": -1880},
            {"label": "Opex", "value": -480},
            {"label": "Act", "value": round(ebitda), "type": "total"},
        ]

    product_bars = [
        {
            "label": line["name"][:3],
            "value": round(line["gm_pct"] * 100, 1),
        }
        for line in base["lines"]
    ]

    kpis = [
        {
            "id": "margin",
            "view": "drivers",
            "label": "EBITDA margin",
            "value": f"{margin * 100:.1f}%",
            "unit": "",
            "delta": f"target {_FINANCE_TARGET * 100:.0f}%",
            "alert": margin < _FINANCE_TARGET,
        },
        {
            "id": "ebitda",
            "view": "drivers",
            "label": "EBITDA",
            "value": _fmt(ebitda),
            "unit": "mn",
            "delta": "actual",
            "alert": False,
        },
        {
            "id": "revenue",
            "view": "revenue",
            "label": "Revenue",
            "value": _fmt(revenue),
            "unit": "mn",
            "delta": "on plan",
            "alert": False,
        },
        {
            "id": "gm",
            "view": "product",
            "label": "Gross margin",
            "value": f"{gm_pct * 100:.1f}%",
            "unit": "",
            "delta": "GM %",
            "alert": False,
        },
        {
            "id": "opex",
            "view": "opex",
            "label": "Opex/rev",
            "value": f"{opex_rev * 100:.1f}%",
            "unit": "",
            "delta": "opex intensity",
            "alert": False,
        },
    ]

    views = {
        "drivers": {
            **_waterfall_chart(
                "EBITDA drivers · budget to actual",
                waterfall_rows,
                note="Largest negative steps are the margin culprits.",
            ),
        },
        "revenue": {
            **_bar_chart(
                "Revenue by product",
                [
                    {"label": line["name"], "value": round(line["rev"], 2)}
                    for line in base["lines"]
                ],
                tag="drill-down",
            ),
        },
        "product": {
            **_bar_chart(
                "Gross margin by product",
                product_bars,
                y_axis_title="GM %",
                tag="drill-down",
            ),
        },
        "fx": {
            **_bar_chart(
                "FX sensitivity (illustrative)",
                [
                    {"label": "Now", "value": round(margin * 100, 1)},
                    {
                        "label": "−3%",
                        "value": round(
                            _finance_comp(0, 0, 0, 3, 0, "all")["margin"] * 100,
                            1,
                        ),
                    },
                    {
                        "label": "−5%",
                        "value": round(
                            _finance_comp(0, 0, 0, 5, 0, "all")["margin"] * 100,
                            1,
                        ),
                    },
                    {
                        "label": "−7%",
                        "value": round(
                            _finance_comp(0, 0, 0, 7, 0, "all")["margin"] * 100,
                            1,
                        ),
                    },
                ],
                y_axis_title="margin %",
                tag="currency",
            ),
        },
        "opex": _table_view(
            "Operating expenses (illustrative base)",
            ["Line", "Base"],
            [["Total opex", _fmt(base["opex"])]],
            tag="cost",
            note="Replace with profit_summary opex breakdown when columns confirmed.",
        ),
    }

    side = {
        "top": {
            **_bar_chart(
                "Margin by product",
                product_bars,
                y_axis_title="GM %",
                tag="GM %",
            ),
        },
        "bottom": {
            **_donut_chart(
                "Imported COGS share",
                [
                    {"label": "Imported", "value": 55},
                    {"label": "Local", "value": 45},
                ],
                tag="currency",
                note="Illustrative 55% import share from mockup model.",
            ),
        },
    }

    inputs = [
        {
            "id": "price",
            "label": "Price",
            "min": -10,
            "max": 15,
            "step": 0.5,
            "default": 0,
            "unit": "%",
        },
        {
            "id": "cost",
            "label": "Cost",
            "min": -10,
            "max": 15,
            "step": 0.5,
            "default": 0,
            "unit": "%",
        },
        {
            "id": "vol",
            "label": "Volume",
            "min": -10,
            "max": 15,
            "step": 0.5,
            "default": 0,
            "unit": "%",
        },
        {
            "id": "fx",
            "label": "FX",
            "min": -10,
            "max": 15,
            "step": 0.5,
            "default": 0,
            "unit": "%",
        },
        {
            "id": "opex",
            "label": "Opex",
            "min": -10,
            "max": 15,
            "step": 0.5,
            "default": 0,
            "unit": "%",
        },
    ]
    # Override bounds from DB levers when present
    for lever in levers:
        lid = str(_row_get(lever, "lever_id", "id", "name", "lever_name") or "").lower()
        for inp in inputs:
            if inp["id"] in lid or lid in inp["id"]:
                mn = _row_get(lever, "min", "min_value", "minimum")
                mx = _row_get(lever, "max", "max_value", "maximum")
                default = _row_get(lever, "default", "default_value", "value")
                if mn is not None:
                    inp["min"] = float(mn)
                if mx is not None:
                    inp["max"] = float(mx)
                if default is not None:
                    inp["default"] = float(default)

    return {
        "agent": "finance",
        "import_batch_id": snap.get("import_batch_id"),
        "default_view": "drivers",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            "action": "simulate_finance",
            "gauge_label": "Path to 15% target",
            "scope_options": ["all", "fx"],
            "inputs": inputs,
            "baseline": base,
            "illustrative": True,
            "db_kpis_count": len(kpis_rows),
            "db_profit_count": len(profit),
            "db_variance_count": len(variance),
        },
    }


# ---------------------------------------------------------------------------
# Leakage
# ---------------------------------------------------------------------------


def simulate_leakage_scenario(
    hold: float,
    dup_rec: float,
    ov_rec: float,
    *,
    duplicates_amount: float = 3050,
    overbill_amount: float = 400,
    other_blocked: float = 500,
    at_risk: float = 7845,
) -> dict[str, Any]:
    blocked = hold + other_blocked
    recovered = (
        duplicates_amount * dup_rec / 100
        + overbill_amount * ov_rec / 100
    )
    total = blocked + recovered
    return {
        "success": True,
        "illustrative": True,
        "blocked": round(blocked, 2),
        "recovered": round(recovered, 2),
        "total_protected": round(total, 2),
        "at_risk": at_risk,
        "pct_of_at_risk": round(total / at_risk * 100, 1) if at_risk else 0,
        "gauge": {
            "ratio": total / at_risk if at_risk else 0,
            "center": _fmt(total),
            "txt": f"{round(total / at_risk * 100) if at_risk else 0}% of at risk",
        },
    }


def _leakage_dashboard(snap: dict[str, Any]) -> dict[str, Any]:
    summary_rows = snap.get("summary") or []
    categories = snap.get("category_breakdowns") or []
    anomalies = snap.get("anomalies") or []
    worklist = snap.get("action_worklist") or []
    summary = summary_rows[0] if summary_rows else {}

    def cat_amount(row: dict[str, Any]) -> float:
        val = _row_get(row, "amount_idr_mn", "amount", "value", "exposure_idr_mn")
        try:
            return float(val or 0)
        except (TypeError, ValueError):
            return 0.0

    def cat_name(row: dict[str, Any]) -> str:
        return str(
            _row_get(row, "category_name", "category", "name", "label") or "Other"
        )

    cat_rows = [
        {"label": cat_name(c), "value": cat_amount(c)}
        for c in categories
    ]
    at_risk = float(
        _row_get(
            summary,
            "total_at_risk_idr_mn",
            "flagged_idr_mn",
            "total_idr_mn",
            "amount_idr_mn",
        )
        or sum(r["value"] for r in cat_rows)
        or 7845
    )
    fraud = 0.0
    duplicates = 0.0
    for row in cat_rows:
        low = row["label"].lower()
        if "fraud" in low or "bank" in low:
            fraud += row["value"]
        if "dup" in low:
            duplicates += row["value"]
    if not fraud:
        fraud = 3800.0
    if not duplicates:
        duplicates = 3050.0

    base_sim = simulate_leakage_scenario(
        hold=fraud,
        dup_rec=95,
        ov_rec=90,
        duplicates_amount=duplicates,
        at_risk=at_risk,
    )

    kpis = [
        {
            "id": "flagged",
            "view": "worklist",
            "label": "Flagged this cycle",
            "value": _fmt(at_risk),
            "unit": "mn",
            "delta": f"{len(anomalies) or len(worklist)} flags",
            "alert": True,
        },
        {
            "id": "fraud",
            "view": "categories",
            "label": "Fraud held",
            "value": _fmt(fraud),
            "unit": "mn",
            "delta": "bank change",
            "alert": fraud > 0,
        },
        {
            "id": "dup",
            "view": "vendors",
            "label": "Duplicates",
            "value": _fmt(duplicates),
            "unit": "mn",
            "delta": "recoverable",
            "alert": False,
        },
        {
            "id": "blocked",
            "view": "blockvs",
            "label": "Blocked",
            "value": _fmt(base_sim["blocked"]),
            "unit": "mn",
            "delta": "before payment",
            "alert": False,
        },
        {
            "id": "protected",
            "view": "recovery",
            "label": "Total protected",
            "value": _fmt(base_sim["total_protected"]),
            "unit": "mn",
            "delta": "this cycle",
            "alert": False,
        },
    ]

    if not cat_rows:
        cat_rows = [
            {"label": "Bank-change fraud", "value": fraud},
            {"label": "Duplicate pay", "value": duplicates},
            {"label": "Overbilling", "value": 900},
            {"label": "Lost discount", "value": 95},
        ]

    wl_headers = ["#", "Item", "Type", "Amount"]
    wl_rows: list[list[Any]] = []
    for idx, row in enumerate(worklist[:10], start=1):
        wl_rows.append(
            [
                idx,
                str(
                    _row_get(row, "vendor_name", "counterparty", "title", "name")
                    or ""
                ),
                str(_row_get(row, "anomaly_type", "type", "category") or ""),
                _fmt(
                    float(
                        _row_get(row, "amount_idr_mn", "amount", "value") or 0
                    )
                ),
            ]
        )
    if not wl_rows:
        for idx, row in enumerate(anomalies[:10], start=1):
            wl_rows.append(
                [
                    idx,
                    str(_row_get(row, "vendor_name", "name") or ""),
                    str(_row_get(row, "anomaly_type", "type") or ""),
                    _fmt(
                        float(
                            _row_get(row, "amount_idr_mn", "amount", "value")
                            or 0
                        )
                    ),
                ]
            )

    views = {
        "categories": {
            **_bar_chart(
                "Leakage & fraud by category",
                cat_rows,
                tag="breakdown",
            ),
        },
        "blockvs": {
            **_bar_chart(
                "Blocked vs recoverable",
                [
                    {"label": "Blocked", "value": base_sim["blocked"]},
                    {"label": "Recoverable", "value": duplicates + 400},
                ],
                tag="money",
            ),
        },
        "recovery": {
            **_bar_chart(
                "Protected vs at risk",
                [
                    {"label": "At risk", "value": at_risk},
                    {
                        "label": "Protected",
                        "value": base_sim["total_protected"],
                    },
                ],
                tag="recovery",
            ),
        },
        "worklist": _table_view(
            "Action worklist",
            wl_headers,
            wl_rows,
            tag="worklist",
        ),
        "vendors": _table_view(
            "Vendor / anomaly radar",
            wl_headers,
            wl_rows,
            tag="risk",
        ),
    }

    side = {
        "top": _donut_chart("Leakage mix", cat_rows, tag="risk"),
        "bottom": {
            **_bar_chart(
                "Protected vs at risk",
                [
                    {"label": "At risk", "value": at_risk},
                    {
                        "label": "Protected",
                        "value": base_sim["total_protected"],
                    },
                ],
                tag="recovery",
            ),
        },
    }

    return {
        "agent": "leakage",
        "import_batch_id": snap.get("import_batch_id"),
        "default_view": "categories",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            "action": "simulate_leakage",
            "gauge_label": f"Total protected vs {_fmt(at_risk)}",
            "inputs": [
                {
                    "id": "hold",
                    "label": "Hold amount mn",
                    "min": 0,
                    "max": max(fraud, 1),
                    "step": 50,
                    "default": fraud,
                    "unit": "IDR mn",
                },
                {
                    "id": "dupRec",
                    "label": "Dup recovery %",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "default": 95,
                    "unit": "%",
                },
                {
                    "id": "ovRec",
                    "label": "Overbill rec %",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "default": 90,
                    "unit": "%",
                },
            ],
            "baseline": {
                "duplicates_amount": duplicates,
                "overbill_amount": 400,
                "other_blocked": 500,
                "at_risk": at_risk,
                "fraud": fraud,
            },
            "illustrative": True,
        },
    }
