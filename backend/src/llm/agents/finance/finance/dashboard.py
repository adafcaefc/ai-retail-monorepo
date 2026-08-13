"""Finance dashboard payload + illustrative scenario simulation."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.common.dashboard_blocks import (
    _bar_chart,
    _call_with_timeout,
    _category_group_filter,
    _donut_chart,
    _enriched,
    _entity_filter,
    _filters,
    _fmt,
    _line_chart,
    _num,
    _pct,
    _period_filter,
    _round_half_up,
    _row_get,
    _table_view,
    _waterfall_chart,
)
from src.llm.agents.finance.finance.tools.performance_data import (
    get_financial_performance_snapshot,
)


# The unit economics the simulator runs on now come from the snapshot's
# `cost_model`, measured per category from FACT_Sales and FACT_Opex. What used
# to sit here was three invented products — Industrial, Precision, Standard —
# with typed-in quantities and prices, driving real sliders beside real KPI
# tiles with nothing marking the difference.
#
# This fallback exists only for callers that supply no cost model: the test
# fixtures, and `_finance_dashboard({"profit_summary": []})`. It is deliberately
# empty rather than plausible, so a missing model shows up as an empty chart
# instead of quietly resurrecting invented figures.
_EMPTY_MODEL: dict[str, Any] = {"lines": [], "opex_by_type": {}, "opex_total": 0.0}

# Policy fallback for the EBITDA gauge when the snapshot carries no budget
# margin. The real target is read from budget (15.5%); this is the last resort.
_FINANCE_TARGET = 0.15

# Opex lines that a cost lever can actually move. Payroll and rent do not flex
# with a slider in the period the board covers; marketing and freight do. The
# dataset states the type per line, so the simulator no longer has to treat
# them alike.
_FLEXIBLE_OPEX = ("Variable", "Discretionary")

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

    The figures come from the snapshot's `simulator_levers`, so a preset can
    never quote a number the dataset does not hold — that is the mistake QC-009
    records for the EBITDA target. Finance now derives that row from newdata:
    the FX move is treasury's own adverse rate, and the price move is the rise
    that reaches budget margin. The column shape is unchanged, so this function
    did not have to be.

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

    model = _call_with_timeout(get_financial_performance_snapshot).get(
        "cost_model"
    ) or _EMPTY_MODEL
    base = _finance_comp(0, 0, 0, 0, 0, "all", model)
    scen = _finance_comp(price, cost, vol, fx, opex, scope, model)
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
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute the P&L under a set of lever settings.

    `model` carries the measured unit economics — one line per category, with
    the quantity, realised price, realised unit cost and imported share each
    actually has. With every lever at zero this reproduces the ledger, which
    is what makes a scenario comparable to the board beside it.
    """
    model = model or _EMPTY_MODEL
    # Puts line revenue into the same unit as opex (IDR mn). The model states
    # its own scale; a caller that omits it is already in one unit.
    scale = float(model.get("revenue_scale") or 1.0)

    rev = 0.0
    gm = 0.0
    lines: list[dict[str, Any]] = []
    for product in model.get("lines") or []:
        imported_share = float(product.get("imported_share") or 0.0)
        # "imported" scope moves only the lines that carry imported cost.
        apply = scope == "all" or imported_share > 0
        qty = float(product["qty"]) * (1 + (vol / 100 if apply else 0))
        unit_price = float(product["price"]) * (1 + (price / 100 if apply else 0))
        # FX reaches a line only through the share of its cost that is
        # imported. A wholly local line is untouched by an IDR/USD move.
        unit_cost = (
            float(product["cost"])
            * (1 + cost / 100)
            * (1 + fx / 100 * imported_share)
        )
        line_rev = qty * unit_price / scale
        line_cost = qty * unit_cost / scale
        rev += line_rev
        gm += line_rev - line_cost
        lines.append(
            {
                "name": product["name"],
                "rev": line_rev,
                "gm": line_rev - line_cost,
                "gm_pct": (line_rev - line_cost) / line_rev if line_rev else 0,
            }
        )

    # The lever moves Variable and Discretionary opex. Fixed lines hold: a
    # 10% operating-cost cut does not cut payroll 10% within the period.
    by_type = model.get("opex_by_type") or {}
    if by_type:
        flexible = sum(v for k, v in by_type.items() if k in _FLEXIBLE_OPEX)
        fixed = sum(v for k, v in by_type.items() if k not in _FLEXIBLE_OPEX)
        op = fixed + flexible * (1 + opex / 100)
    else:
        op = float(model.get("opex_total") or 0.0) * (1 + opex / 100)

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
    opex_lines: list[dict[str, Any]],
) -> tuple[list[list[Any]], bool]:
    """Opex lines vs budget, worst variance first.

    Reads `snapshot["operating_expenses"]`, which is `fact_opex` grouped by
    `opex_line` at the same scope as the KPI cards.

    This used to be reconstructed from `profit_summary` by probing for a
    `line_item` / `actual_idr_mn` shape. After the move to `newdata` those
    rows are KPI metrics keyed `metric_name` / `actual_value`, so nothing
    matched, and the table silently served an illustrative breakdown left
    over from the previous dataset -- a 7,480 total on a board whose KPI card
    was built on 98,772. The fallback is kept for a snapshot that genuinely
    carries no lines, but it is announced by the caller rather than passed
    off as data.

    Returns (rows, is_live).
    """

    rows: list[list[Any]] = []
    for row in opex_lines or []:
        label = str(
            _row_get(row, "opex_line", "line_item", "category", "name", "label")
            or ""
        ).strip()
        if not label:
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
    model = snap.get("cost_model") or _EMPTY_MODEL
    base = _finance_comp(0, 0, 0, 0, 0, "all", model)
    kpis_rows = snap.get("kpis") or []
    variance = snap.get("variance_drivers") or []
    profit = snap.get("profit_summary") or []
    opex_lines = snap.get("operating_expenses") or []
    levers = snap.get("simulator_levers") or []

    # Measured from `fact_sales.import_flag`. Where the snapshot carries no
    # `cogs_mix`, it is recomputed from the cost model's per-line imported
    # shares, weighted by each line's cost — which gives the same answer. What
    # it is never taken from is a constant: this figure is printed as a claim
    # about the company, and it used to read 55% against a ledger saying 65.2%.
    mix = snap.get("cogs_mix") or {}
    if "imported_pct" in mix:
        imported = float(mix["imported_pct"])
    else:
        line_costs = [
            (float(line["qty"]) * float(line["cost"]),
             float(line.get("imported_share") or 0.0))
            for line in (model.get("lines") or [])
        ]
        total_cost = sum(cost for cost, _ in line_costs)
        imported = (
            sum(cost * share for cost, share in line_costs) / total_cost * 100
            if total_cost else 0.0
        )

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

    # Bookend the live steps with the bridge's own endpoints. They have to
    # come from the same scope as the steps: the bridge is whole-ledger and
    # cannot be sliced by entity, so opening with an entity-scoped EBITDA gave
    # a waterfall whose bars did not reach its own closing bar. Where the
    # snapshot carries no endpoints, fall back to the EBITDA cards -- correct
    # whenever the board is unfiltered, which is the only time the two scopes
    # coincide.
    endpoints = snap.get("bridge_endpoints") or {}
    if waterfall_rows and not any(
        p.get("type") == "total" for p in waterfall_rows
    ):
        opening = endpoints.get("opening_idr_mn", ebitda_budget)
        closing = endpoints.get("closing_idr_mn", ebitda)
        if opening:
            waterfall_rows = (
                [
                    {
                        "label": str(endpoints.get("opening_label") or "Budget"),
                        "value": round(float(opening), 2),
                        "type": "total",
                    }
                ]
                + waterfall_rows
                + [
                    {
                        "label": str(endpoints.get("closing_label") or "Actual"),
                        "value": round(float(closing), 2),
                        "type": "total",
                    }
                ]
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

    opex_rows, opex_is_live = _finance_opex_rows(opex_lines)

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

    # The bridge cannot be recomputed per entity, period or category group
    # (see get_financial_performance_snapshot's docstring), so a reader who
    # just scoped every other chart is told this one did not follow, instead
    # of silently reading a stale whole-ledger bridge as if it had.
    drivers_note = "Largest negative steps are the margin culprits."
    if (
        snap.get("legal_entity_id")
        or snap.get("period_value")
        or snap.get("category_group")
    ):
        drivers_note += (
            " Shows the full reporting window across all entities — this "
            "bridge cannot be split by entity, period or category in the "
            "current dataset."
        )

    views = {
        "drivers": {
            **_waterfall_chart(
                "EBITDA drivers · budget to actual",
                waterfall_rows,
                note=drivers_note,
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
                else "Indicative split — this batch carries no operating "
                "expense lines, so the breakdown below is not from the data."
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
                    {"label": "Imported", "value": _round_half_up(imported, 1)},
                    {"label": "Local", "value": _round_half_up(100 - imported, 1)},
                ],
                tag="currency",
                note=(
                    f"{imported:.1f}% of COGS is imported, so that "
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

    # QC-043 — product and cost line are the two client-side lenses: they
    # narrow chart rows already on the wire. Entity, period and category
    # group are server-side filters instead (see `server_filters` below)
    # because they change what the query aggregated, not just which bars are
    # shown from an already-fetched set.
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
        "server_filters": [
            _entity_filter(
                snap.get("legal_entities"), snap.get("legal_entity_id")
            ),
            _period_filter(
                snap.get("available_months"), snap.get("period_value")
            ),
            _category_group_filter(
                snap.get("available_category_groups"),
                snap.get("category_group"),
            ),
        ],
        # QC-010-adjacent honesty: the EBITDA bridge cannot be entity-sliced
        # with the current dataset (see `_driver_rows`'s docstring) — the
        # frontend reads this to say so on the chart rather than showing a
        # stale whole-ledger bridge next to KPI tiles that did narrow.
        "bridge_scope": snap.get("bridge_scope", "all_entities"),
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


# The only agent whose data carries all three dimensions.
SUPPORTED_FILTERS: frozenset[str] = frozenset(
    {"legal_entity_id", "period", "category_group"}
)


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    return _enriched(
        _finance_dashboard(
            _call_with_timeout(
                lambda: get_financial_performance_snapshot(
                    scope.legal_entity_id, scope.period, scope.category_group
                )
            )
        )
    )
