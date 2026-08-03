"""Finance (performance) agent data tools, reading the `newdata` star schema.

The old `financial_performance.*` tables held finished answers — one row per
KPI, already computed by whoever authored the workbook. `newdata` holds facts,
so the same figures are aggregated here instead of read. That is the point of
the migration: a number the application derives can be filtered, drilled into
and argued with; a number it reads cannot.

The return contract is deliberately unchanged. This still returns
`import_batch_id`, `period`, `kpis`, `profit_summary`, `variance_drivers` and
`simulator_levers`, with the same row shapes and the same `metric_name`
spellings, because `dashboard.py` resolves its tiles by name and the chat agent
already calls this one function. Changing the source without changing the
contract is what moves the board and the chat together, in one commit.

Every figure here is checked by `scripts/verify_new_dataset.py` against sheet
`50_Agent_KPIs`, which ships its own derivations.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.llm.agents.common.tools.db import (
    _latest_batch_id,
    _read_connection,
    _rows,
)

# The reporting window: the twelve months to September 2026. It is the window
# both `90_Reconciliation` and `50_Agent_KPIs` use, so any other choice would
# put this module at odds with the dataset's own acceptance suite. It is an
# integer comparison rather than a date one to match those formulas exactly.
WINDOW_START = 202510

BATCH_NAME = "new_dataset"


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _totals(connection: Connection) -> dict[str, float]:
    """The nine aggregates every Finance figure below is built from."""
    window = f"month_index >= {WINDOW_START}"

    sales = connection.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(net_revenue_idr_mn), 0)  AS revenue,
                COALESCE(SUM(cogs_idr_mn), 0)         AS cogs,
                COALESCE(SUM(gross_margin_idr_mn), 0) AS gross_margin,
                COALESCE(SUM(qty), 0)                 AS qty,
                COALESCE(SUM(cogs_idr_mn) FILTER (
                    WHERE import_flag = 'Imported'), 0) AS cogs_imported
            FROM newdata.fact_sales
            WHERE {window}
            """
        )
    ).mappings().one()

    budget = connection.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(budget_revenue_idr_mn), 0)      AS revenue,
                COALESCE(SUM(budget_cogs_idr_mn), 0)         AS cogs,
                COALESCE(SUM(budget_gross_margin_idr_mn), 0) AS gross_margin
            FROM newdata.fact_budget
            WHERE {window}
            """
        )
    ).mappings().one()

    opex = connection.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(actual_idr_mn), 0) AS actual,
                COALESCE(SUM(budget_idr_mn), 0) AS budget
            FROM newdata.fact_opex
            WHERE {window}
            """
        )
    ).mappings().one()

    return {
        "revenue": float(sales["revenue"]),
        "cogs": float(sales["cogs"]),
        "gross_margin": float(sales["gross_margin"]),
        "qty": float(sales["qty"]),
        "cogs_imported": float(sales["cogs_imported"]),
        "budget_revenue": float(budget["revenue"]),
        "budget_cogs": float(budget["cogs"]),
        "budget_gross_margin": float(budget["gross_margin"]),
        "opex": float(opex["actual"]),
        "budget_opex": float(opex["budget"]),
    }


def _kpi_rows(
    totals: dict[str, float],
    import_batch_id: int,
) -> list[dict[str, Any]]:
    """The ten KPI rows, in the order and spelling the dashboard matches on.

    `dashboard.py` resolves its five headline tiles by lowercased
    `metric_name` (`_FINANCE_KPI_METRICS`), so these names are a contract, not
    a label. Renaming one silently empties a tile rather than erroring.
    """
    ebitda = totals["gross_margin"] - totals["opex"]
    budget_ebitda = totals["budget_gross_margin"] - totals["budget_opex"]

    specs: list[tuple[str, float, float, str, str]] = [
        (
            "Revenue (IDR mn)",
            totals["budget_revenue"],
            totals["revenue"],
            "IDR million",
            "Net revenue over the reporting window.",
        ),
        (
            "Revenue growth vs budget",
            0.0,
            _ratio(
                totals["revenue"] - totals["budget_revenue"],
                totals["budget_revenue"],
            ),
            "percentage",
            "Actual net revenue against budgeted revenue.",
        ),
        (
            "Gross margin (IDR mn)",
            totals["budget_gross_margin"],
            totals["gross_margin"],
            "IDR million",
            "Absolute margin: revenue less COGS.",
        ),
        (
            "Gross margin %",
            _ratio(totals["budget_gross_margin"], totals["budget_revenue"]),
            _ratio(totals["gross_margin"], totals["revenue"]),
            "percentage",
            "Gross margin divided by net revenue.",
        ),
        (
            "EBITDA (IDR mn)",
            budget_ebitda,
            ebitda,
            "IDR million",
            "Gross margin less operating expenses.",
        ),
        (
            "EBITDA %",
            _ratio(budget_ebitda, totals["budget_revenue"]),
            _ratio(ebitda, totals["revenue"]),
            "percentage",
            "EBITDA divided by net revenue.",
        ),
        (
            "Operating cost (IDR mn)",
            totals["budget_opex"],
            totals["opex"],
            "IDR million",
            "Payroll, freight and other operating expenses.",
        ),
        (
            "Opex to revenue %",
            _ratio(totals["budget_opex"], totals["budget_revenue"]),
            _ratio(totals["opex"], totals["revenue"]),
            "percentage",
            "Operating expenses as a share of net revenue.",
        ),
        (
            "Blended avg price (IDR '000)",
            0.0,
            _ratio(totals["revenue"] * 1000.0, totals["qty"]),
            "IDR thousand per unit",
            "Net revenue divided by units sold. Budget carries no unit count.",
        ),
        (
            "Blended avg unit cost (IDR '000)",
            0.0,
            _ratio(totals["cogs"] * 1000.0, totals["qty"]),
            "IDR thousand per unit",
            "COGS divided by units sold. Budget carries no unit count.",
        ),
    ]

    return [
        {
            "id": order,
            "import_batch_id": import_batch_id,
            "metric_name": name,
            "metric_order": order,
            "budget_value": budget,
            "actual_value": actual,
            "change_value": actual - budget,
            "unit": unit,
            "notes": notes,
            "source_sheet": "20_FACT_Sales / 21_FACT_Budget / 22_FACT_Opex",
            "created_at": None,
        }
        for order, (name, budget, actual, unit, notes) in enumerate(specs, start=1)
    ]


def _profit_rows(
    totals: dict[str, float],
    import_batch_id: int,
) -> list[dict[str, Any]]:
    """The P&L ladder.

    `51_Finance_PL` states the same five actuals, but carries no budget column,
    so both sides are aggregated from the facts instead. Check 4 in
    `90_Reconciliation` is what proves the two agree.
    """
    ebitda = totals["gross_margin"] - totals["opex"]
    budget_ebitda = totals["budget_gross_margin"] - totals["budget_opex"]

    specs = [
        ("Revenue", totals["budget_revenue"], totals["revenue"], "IDR million"),
        ("COGS", totals["budget_cogs"], totals["cogs"], "IDR million"),
        (
            "Gross margin",
            totals["budget_gross_margin"],
            totals["gross_margin"],
            "IDR million",
        ),
        (
            "Gross margin %",
            _ratio(totals["budget_gross_margin"], totals["budget_revenue"]),
            _ratio(totals["gross_margin"], totals["revenue"]),
            "percentage",
        ),
        (
            "Operating expenses",
            totals["budget_opex"],
            totals["opex"],
            "IDR million",
        ),
        ("EBITDA", budget_ebitda, ebitda, "IDR million"),
        (
            "EBITDA %",
            _ratio(budget_ebitda, totals["budget_revenue"]),
            _ratio(ebitda, totals["revenue"]),
            "percentage",
        ),
    ]

    return [
        {
            "id": order,
            "import_batch_id": import_batch_id,
            "metric_name": name,
            "metric_order": order,
            "budget_value": budget,
            "actual_value": actual,
            "variance_value": actual - budget,
            "unit": unit,
            "source_sheet": "51_Finance_PL",
            "created_at": None,
        }
        for order, (name, budget, actual, unit) in enumerate(specs, start=1)
    ]


def _driver_rows(
    connection: Connection,
    import_batch_id: int,
) -> list[dict[str, Any]]:
    """The EBITDA bridge, read as steps rather than recomputed.

    `52_Finance_EBITDA_Bridge` carries a `derivation` per step, so the
    description a CFO reads is the dataset's own account of the number rather
    than prose written beside it. The two `total` rows — opening Budget EBITDA
    and closing Actual EBITDA — are endpoints, not drivers, and are excluded.
    """
    rows = _rows(
        connection,
        """
        SELECT step, value_idr_mn, derivation
        FROM newdata.finance_ebitda_bridge
        WHERE type = 'step'
        ORDER BY _row_order
        """,
        {},
    )

    drivers = []
    for order, row in enumerate(rows, start=1):
        impact = float(row["value_idr_mn"] or 0.0)
        drivers.append(
            {
                "id": order,
                "import_batch_id": import_batch_id,
                "driver_name": row["step"],
                "driver_order": order,
                "impact_idr_mn": impact,
                "impact_direction": "Helped" if impact >= 0 else "Hurt",
                "driver_description": row["derivation"],
                "source_sheet": "52_Finance_EBITDA_Bridge",
                "created_at": None,
            }
        )
    return drivers


def _cost_model(connection: Connection) -> dict[str, Any]:
    """The unit economics the what-if simulator runs on, measured per category.

    This replaces `_FINANCE_PROD` — three invented products with typed-in
    quantities and prices — and `_FINANCE_OPEX`, a single typed-in total. Both
    predate the migration, and the simulator moved real sliders over them.

    Two things the old constants could not express and this can:

    `imported_share` is per category, so an FX move hits each line by the
    share of *its own* cost that is actually imported, instead of one blanket
    55% applied to everything.

    Opex is split by `opex_type`. A CFO cutting operating cost 10% cannot cut
    payroll 10%, and the dataset says which lines are Fixed, Variable or
    Discretionary. The simulator no longer has to pretend they are alike.
    """
    window = f"month_index >= {WINDOW_START}"

    lines = _rows(
        connection,
        f"""
        SELECT
            c.category_name                       AS name,
            SUM(s.qty)                            AS qty,
            SUM(s.net_revenue_idr_mn)             AS revenue,
            SUM(s.cogs_idr_mn)                    AS cogs,
            COALESCE(SUM(s.cogs_idr_mn) FILTER (
                WHERE s.import_flag = 'Imported'), 0) AS cogs_imported
        FROM newdata.fact_sales s
        JOIN newdata.dim_category c USING (category_id)
        WHERE {window}
        GROUP BY c.category_name
        HAVING SUM(s.qty) > 0
        ORDER BY SUM(s.net_revenue_idr_mn) DESC
        """,
        {},
    )

    model_lines = []
    for row in lines:
        qty = float(row["qty"] or 0.0)
        revenue = float(row["revenue"] or 0.0)
        cogs = float(row["cogs"] or 0.0)
        model_lines.append(
            {
                "name": row["name"],
                "qty": qty,
                # Realised unit economics, in IDR '000 per unit: the price and
                # cost actually achieved, not a list price nobody paid.
                "price": _ratio(revenue * 1000.0, qty),
                "cost": _ratio(cogs * 1000.0, qty),
                "imported_share": _ratio(float(row["cogs_imported"] or 0.0), cogs),
            }
        )

    opex = _rows(
        connection,
        f"""
        SELECT opex_type, SUM(actual_idr_mn) AS actual
        FROM newdata.fact_opex
        WHERE {window}
        GROUP BY opex_type
        """,
        {},
    )

    return {
        "lines": model_lines,
        # `qty * price` is in IDR '000, because price and cost are per-unit in
        # IDR '000. Opex is in IDR mn. Dividing by this puts both in IDR mn so
        # EBITDA is a subtraction of like for like — the scale is carried in
        # the model rather than assumed by the caller.
        "revenue_scale": 1000.0,
        "opex_by_type": {
            str(row["opex_type"]): float(row["actual"] or 0.0) for row in opex
        },
        "opex_total": sum(float(row["actual"] or 0.0) for row in opex),
    }


def _cogs_mix(totals: dict[str, float]) -> dict[str, float]:
    """The imported vs local split of COGS, as shares that sum to 100.

    `fact_sales.import_flag` makes this measurable. The old dashboard printed
    a hand-typed 55/45 in both the donut and its caption, which was the old
    dataset's figure and survived into a dataset where it is 65.2/34.8.
    Returning one computed pair means the chart and its caption cannot drift
    apart, which is how the two came to disagree in the first place.
    """
    imported = totals["cogs_imported"]
    total = totals["cogs"]
    imported_share = _ratio(imported, total) * 100.0
    return {
        "imported_idr_mn": imported,
        "local_idr_mn": total - imported,
        "imported_pct": imported_share,
        "local_pct": 100.0 - imported_share if total else 0.0,
    }


def _simulator_levers(
    connection: Connection,
    totals: dict[str, float],
) -> list[dict[str, Any]]:
    """The lever settings the preset buttons offer, sourced from newdata.

    These used to come from `financial_performance.simulator_levers` — a single
    stored row saying price +4%, fx +3%. That was the last read of the old
    schema in Finance, and after the migration it offered a scenario authored
    for a different company.

    Both numbers exist in the new dataset, so neither has to be invented:

    `fx_pct` is the adverse rate against spot in `43_FX_Assumptions`
    (18,488.5 vs 17,950 = 3.0%), which is treasury's own downside case rather
    than a round number someone liked.

    `price_pct` is the price rise that lands EBITDA margin on budget. Costs do
    not move with price, so (R(1+p) - C) / (R(1+p)) = t solves to
    1 + p = C / (R(1 - t)).
    """
    rates = {
        str(row["metric"]): float(row["value"] or 0.0)
        for row in _rows(
            connection,
            "SELECT metric, value FROM newdata.fx_assumptions",
            {},
        )
    }
    spot = rates.get("Spot rate (IDR/USD)", 0.0)
    adverse = rates.get("Adverse scenario rate (IDR/USD)", 0.0)
    fx_pct = _ratio(adverse - spot, spot) * 100.0 if spot else 0.0

    revenue = totals["revenue"]
    fixed_cost = totals["cogs"] + totals["opex"]
    target = _ratio(
        totals["budget_gross_margin"] - totals["budget_opex"],
        totals["budget_revenue"],
    )
    denominator = revenue * (1 - target)
    price_pct = (fixed_cost / denominator - 1) * 100.0 if denominator else 0.0

    # Returned in the column shape `_finance_presets` already reads, so the
    # buttons, their wording and their translations are untouched. Only the
    # source moves — the same trick the rest of this migration uses.
    #
    # Values are in points, not fractions, and rounded to the slider's own
    # precision: a preset that cannot be reproduced by dragging the control it
    # fills is worse than no preset.
    return [
        {
            "selling_price_change_percentage": (
                round(price_pct, 1) if 0 < price_pct <= 100 else 0.0
            ),
            "material_cost_change_percentage": 0.0,
            "sales_volume_change_percentage": 0.0,
            "usd_idr_change_percentage": round(fx_pct, 1),
            "operating_cost_change_percentage": 0.0,
            "imported_material_share_percentage": round(
                _ratio(totals["cogs_imported"], totals["cogs"]) * 100.0, 1
            ),
            "source_sheet": "43_FX_Assumptions / 21_FACT_Budget",
        }
    ]


def _period(connection: Connection) -> str:
    """The span this snapshot covers, read from the month dimension.

    QC-035 asked every chart to state its period. On the old dataset that had
    to be reverse-engineered from workbook filenames because no row carried a
    date — see the docstring on `common/tools/period.py`. `fact_sales.month`
    carries one, so the label is now a column read and cannot drift from the
    figures beside it.
    """
    row = connection.execute(
        text(
            f"""
            SELECT MIN(month) AS first_month, MAX(month) AS last_month
            FROM newdata.fact_sales
            WHERE month_index >= {WINDOW_START}
            """
        )
    ).mappings().one()

    first, last = row["first_month"], row["last_month"]
    if first is None or last is None:
        return "No period recorded"
    return f"{first:%B %Y} – {last:%B %Y} — actual vs budget"


def get_financial_performance_snapshot() -> dict[str, Any]:
    """Return the latest bounded KPI, profit, variance, and simulator data."""

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(connection, BATCH_NAME)
        totals = _totals(connection)

        return {
            "import_batch_id": import_batch_id,
            "period": _period(connection),
            "kpis": _kpi_rows(totals, import_batch_id),
            "profit_summary": _profit_rows(totals, import_batch_id),
            "variance_drivers": _driver_rows(connection, import_batch_id),
            "simulator_levers": _simulator_levers(connection, totals),
            # The imported/local COGS split, measured rather than assumed.
            # `fact_sales.import_flag` makes this a fact; before the migration
            # the dashboard printed a hand-typed 55%.
            "cogs_mix": _cogs_mix(totals),
            # Unit economics for the what-if simulator, replacing the three
            # invented products it used to run on.
            "cost_model": _cost_model(connection),
        }


TOOLS = {
    "get_financial_performance_snapshot": get_financial_performance_snapshot,
}


__all__ = ["TOOLS", "get_financial_performance_snapshot"]
