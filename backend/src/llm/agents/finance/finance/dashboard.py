"""Finance dashboard payload + illustrative scenario simulation."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_blocks import (
    _bar_chart,
    _call_with_timeout,
    _donut_chart,
    _enriched,
    _fmt,
    _line_chart,
    _pct,
    _row_get,
    _table_view,
    _waterfall_chart,
)
from src.llm.agents.finance.finance.tools.performance_data import (
    get_financial_performance_snapshot,
)


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


def _finance_opex_rows(
    profit: list[dict[str, Any]],
) -> tuple[list[list[Any]], bool]:
    """Opex lines vs budget, worst variance first.

    profit_summary is selected with `SELECT *`, so the column names are not
    guaranteed. Probe the plausible ones; if nothing resolves, fall back to
    the mockup's illustrative breakdown and let the caller say so in the note.
    Returns (rows, is_live).
    """

    rows: list[list[Any]] = []
    for row in profit:
        label = str(
            _row_get(
                row, "line_item", "opex_line", "category", "name", "label"
            )
            or ""
        ).strip()
        if not label:
            continue
        # Only opex lines; skip revenue/COGS rows that share the table.
        if any(skip in label.lower() for skip in ("revenue", "cogs", "sales")):
            continue

        actual = _row_get(row, "actual_idr_mn", "actual", "amount_idr_mn", "value")
        budget = _row_get(row, "budget_idr_mn", "budget", "plan_idr_mn", "plan")
        if actual is None or budget is None:
            continue
        try:
            act = float(actual)
            bud = float(budget)
        except (TypeError, ValueError):
            continue

        rows.append([label, act, bud, act - bud])

    is_live = bool(rows)
    if not is_live:
        rows = [
            ["Payroll", 3300.0, 3200.0, 100.0],
            ["Logistics & freight", 1650.0, 1400.0, 250.0],
            ["Rent & utilities", 920.0, 900.0, 20.0],
            ["Marketing & selling", 850.0, 800.0, 50.0],
            ["Other opex", 760.0, 700.0, 60.0],
        ]

    rows.sort(key=lambda r: r[3], reverse=True)
    total = [
        "Total operating expenses",
        sum(r[1] for r in rows),
        sum(r[2] for r in rows),
        sum(r[3] for r in rows),
    ]

    formatted = [
        [r[0], _fmt(r[1]), _fmt(r[2]), f"{'+' if r[3] >= 0 else ''}{_fmt(r[3])}"]
        for r in rows + [total]
    ]
    return formatted, is_live


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

    opex_rows, opex_is_live = _finance_opex_rows(profit)

    kpis = [
        {
            "id": "margin",
            "view": "drivers",
            "label": "EBITDA margin",
            "value": f"{margin * 100:.1f}%",
            "unit": "",
            "delta": f"target {_FINANCE_TARGET * 100:.0f}%",
            "alert": margin < _FINANCE_TARGET,
            # Three-tier RAG: at/above target = good, within 20% below = warn.
            "status": (
                "good"
                if margin >= _FINANCE_TARGET
                else "warn"
                if margin >= _FINANCE_TARGET * 0.8
                else "bad"
            ),
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
            "Operating expenses vs budget",
            ["Line", "Actual", "Budget", "Variance"],
            opex_rows,
            tag="cost",
            note=(
                "Worst variance first — the repeatable saving is at the top."
                if opex_is_live
                else "Illustrative breakdown; profit_summary has no opex "
                "line columns in this batch."
            ),
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


def build() -> dict[str, Any]:
    return _enriched(
        _finance_dashboard(_call_with_timeout(get_financial_performance_snapshot))
    )
