"""Finance dashboard payload + illustrative scenario simulation."""

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
    _num,
    _pct,
    _round_half_up,
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

# Exact `metric_name` values from financial_performance.kpis, best match first.
# Substring matching cannot be used here: "revenue" also hits "Revenue growth
# vs budget" and "Opex to revenue %", and whichever row was scanned last won.
_FINANCE_KPI_METRICS = {
    "margin": ("ebitda %", "ebitda margin %", "ebitda margin"),
    "ebitda": ("ebitda (idr mn)", "ebitda"),
    "revenue": ("revenue (idr mn)", "revenue"),
    "gm_pct": ("gross margin %",),
    "opex_rev": ("opex to revenue %", "opex/revenue %"),
}


def _metric_name(row: dict[str, Any]) -> str:
    return (
        str(_row_get(row, "metric_name", "kpi_name", "name", "metric", "label") or "")
        .strip()
        .lower()
    )


_ACTUAL_COLUMNS = ("actual_value", "kpi_value", "value", "actual")
_BUDGET_COLUMNS = ("budget_value", "budget_idr_mn", "budget", "plan")


def _finance_live_metrics(
    kpis_rows: list[dict[str, Any]],
    columns: tuple[str, ...] = _ACTUAL_COLUMNS,
) -> dict[str, float]:
    """Resolve the five headline metrics from the stored KPI rows.

    Ranked rather than first-wins so a more specific alias always beats a
    looser one regardless of row order.
    """

    ranked: dict[str, tuple[int, float]] = {}
    for row in kpis_rows:
        name = _metric_name(row)
        value = _row_get(row, *columns)
        if not name or value is None:
            continue
        num = _num(value, default=float("nan"))
        if num != num:  # NaN — unparseable
            continue
        for slot, candidates in _FINANCE_KPI_METRICS.items():
            if name not in candidates:
                continue
            rank = candidates.index(name)
            if slot not in ranked or rank < ranked[slot][0]:
                ranked[slot] = (rank, num)
    return {slot: value for slot, (_, value) in ranked.items()}


def _finance_presets(levers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lever settings the Finance simulator can jump to.

    The figures come from `financial_performance.simulator_levers`, so a preset
    can never quote a number the dataset does not hold — that is the mistake
    QC-009 records for the EBITDA target.

    Each preset is named after what it *does*, not after where it came from. A
    button labelled "recommendation" asks to be trusted; one labelled with its
    own levers can be checked against the sliders it moves.

    Percentages are stored as fractions in some batches and points in others.
    """
    row = levers[0] if levers else {}

    def pct(*names: str) -> float:
        value = _num(_row_get(row, *names))
        return round(value * 100 if abs(value) <= 1 else value, 2)

    price = pct("selling_price_change_percentage")
    cost = pct("material_cost_change_percentage")
    fx = pct("usd_idr_change_percentage")

    if not any((price, cost, fx)):
        # No stored scenario: offer nothing rather than invent a number. An
        # empty preset row is honest; a made-up one is what this fixes.
        return []

    moved = {"price": price, "cost": cost, "fx": fx}
    stated = ", ".join(
        f"{name} {value:+.1f}%" for name, value in moved.items() if value
    )

    presets = [
        {
            "id": "combined",
            "label": "All levers together",
            "note": f"Every stored lever at once: {stated}.",
            "values": moved,
        }
    ]
    if price:
        presets.append(
            {
                "id": "price_only",
                "label": f"Price {price:+.1f}% alone",
                "note": "Price moves; cost and FX stay where they are.",
                "values": {"price": price},
            }
        )
    if fx:
        presets.append(
            {
                "id": "fx_only",
                "label": f"IDR weakens {fx:.1f}%",
                "note": "Imported share of COGS reprices; nothing else moves.",
                "values": {"fx": fx},
            }
        )
    return presets


def simulate_finance_scenario(
    price: float = 0,
    cost: float = 0,
    vol: float = 0,
    fx: float = 0,
    opex: float = 0,
    scope: str = "all",
    target: float = _FINANCE_TARGET,
) -> dict[str, Any]:
    """Deterministic what-if from the product cost model.

    `target` is the EBITDA margin the gauge measures against. It is passed in
    rather than read from the module constant so the simulator cannot quote a
    different target than the KPI card.
    """

    base = _finance_comp(0, 0, 0, 0, 0, "all")
    scen = _finance_comp(price, cost, vol, fx, opex, scope)
    return {
        "success": True,
        "baseline": base,
        "scenario": scen,
        "stats": {
            "scenario_margin_pct": round(scen["margin"] * 100, 2),
            "ebitda_idr_mn": round(scen["ebitda"], 2),
            "vs_target_pts": round((scen["margin"] - target) * 100, 2),
            "delta_ebitda_idr_mn": round(scen["ebitda"] - base["ebitda"], 2),
            "delta_margin_pts": round(
                (scen["margin"] - base["margin"]) * 100,
                2,
            ),
        },
        "gauge": {
            "ratio": scen["margin"] / target if target else 0,
            "center": _pct(scen["margin"]),
            "txt": (
                f"{_fmt(scen['margin'] / target * 100) if target else 0}% of "
                f"target · gap {_fmt((target - scen['margin']) * 100, 1)} pts"
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

    def _as_fraction(num: float) -> float:
        """Percentages are stored as fractions in some batches, points in others."""
        return num / 100 if num > 1 else num

    live = _finance_live_metrics(kpis_rows)
    if "margin" in live:
        margin = _as_fraction(live["margin"])
    if "ebitda" in live:
        ebitda = live["ebitda"]
    if "revenue" in live:
        revenue = live["revenue"]
    if "gm_pct" in live:
        gm_pct = _as_fraction(live["gm_pct"])
    if "opex_rev" in live:
        opex_rev = _as_fraction(live["opex_rev"])

    # Budget EBITDA opens the waterfall; the drivers table stores only steps.
    # The same budget row also carries the margin target, so the gauge, the
    # card caption and the waterfall all reference one number: two surfaces
    # quoting 15% and 15.7% was formula check #15.
    budget = _finance_live_metrics(
        list(kpis_rows) + list(profit), _BUDGET_COLUMNS
    )
    ebitda_budget = budget.get("ebitda", 0.0)
    target = (
        _as_fraction(budget["margin"])
        if budget.get("margin")
        else _FINANCE_TARGET
    )

    waterfall_rows: list[dict[str, Any]] = []
    for row in variance:
        label = str(
            _row_get(row, "driver_name", "name", "label", "step_name") or ""
        )
        value = _row_get(
            row, "impact_idr_mn", "amount_idr_mn", "value", "amount", "variance"
        )
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

    # Bookend the live steps with the budget and actual totals so the closing
    # bar is the same EBITDA the card shows.
    if waterfall_rows and ebitda_budget and not any(
        p.get("type") == "total" for p in waterfall_rows
    ):
        waterfall_rows = (
            [{"label": "Budget", "value": round(ebitda_budget, 2), "type": "total"}]
            + waterfall_rows
            + [{"label": "Actual", "value": round(ebitda, 2), "type": "total"}]
        )

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
            # QC-043: the bar is abbreviated to fit, so the product filter has
            # nothing to match on unless the full name travels with the point.
            "key": line["name"],
            # Half-up: Precision is exactly 4,930/13,600 = 36.25%, which
            # Python's banker's rounding would print as 36.2.
            "value": _round_half_up(line["gm_pct"] * 100, 1),
        }
        for line in base["lines"]
    ]

    opex_rows, opex_is_live = _finance_opex_rows(profit)

    kpis = [
        {
            "id": "margin",
            "view": "drivers",
            "label": "EBITDA margin",
            "value": _pct(margin),
            "unit": "",
            "delta": f"target {_pct(target)}",
            "alert": margin < target,
            # Three-tier RAG: at/above target = good, within 20% below = warn.
            "status": (
                "good"
                if margin >= target
                else "warn"
                if margin >= target * 0.8
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
                "FX sensitivity · margin at weaker IDR",
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
                else "Indicative split — this batch stores only the operating "
                "expenses total, and that total row is actual."
            ),
        ),
    }

    side = {
        # Not `views:product` again — that one is the margin *rate*. This is
        # the margin *pool*, which is where the profit actually comes from: a
        # high-rate product on low volume contributes little.
        "top": {
            **_bar_chart(
                "Gross margin pool by product",
                [
                    {"label": line["name"], "value": round(line["gm"], 2)}
                    for line in base["lines"]
                ],
                tag="GM mn",
                note="Rate is in the main chart; this is the IDR it earns.",
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
                note=(
                    f"{_FINANCE_IMP * 100:.0f}% of COGS is imported, so that "
                    "share carries the IDR/USD move."
                ),
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

    # QC-043 — the product mix is the only dimension this dataset carries.
    # Entity, store, channel and month arrive with the new dataset.
    filters = _filters(views, side, (
        ("product", "Product", "view:revenue",
         ("view:revenue", "view:product", "side:top"), 0),
        ("cost_line", "Cost line", "view:opex", ("view:opex",), 0),
    ))

    return {
        "agent": "finance",
        # QC-035: the span these figures cover, stamped onto every
        # chart by _enriched().
        "period": snap.get("period"),
        "filters": filters,
        "import_batch_id": snap.get("import_batch_id"),
        "default_view": "drivers",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            # QC-052: the three levers a CFO actually reaches for first.
            "presets": _finance_presets(levers),
            "action": "simulate_finance",
            "gauge_label": f"Path to {_pct(target)} target",
            "scope_options": ["all", "fx"],
            "inputs": inputs,
            "baseline": {**base, "target": target},
        },
    }


# ---------------------------------------------------------------------------


def build() -> dict[str, Any]:
    return _enriched(
        _finance_dashboard(_call_with_timeout(get_financial_performance_snapshot))
    )
