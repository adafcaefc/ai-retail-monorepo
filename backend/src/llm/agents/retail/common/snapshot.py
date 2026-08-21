"""What the three retail snapshot tools share.

A snapshot is not a dashboard payload. `warehouse.py` returns rows because the
browser aggregates them; a snapshot returns the aggregates, because the reader
is a language model with a token budget and no selectors.

The size rule matters more here than anywhere else in the codebase. Every
monitoring run inlines the whole snapshot into each of its three specialist
payloads, so a row added here is paid for three times per Recalculate per
board, whether or not the pass that received it had any use for it. Hence:
aggregates always, a bounded top-N when individual records are the point, and
never the raw 800 or 16,000 rows. An agent that needs more has `query_retail_*`
and a 100-row cap.

Formula ids travel as ids, not expressions, for the same reason -- and they are
imported from each dashboard's own `ENGINE_FORMULAS` rather than restated, so
an agent cannot cite a rule its board does not run.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.tools.db import _read_connection, _rows
from src.llm.agents.common.tools.scope import (
    active_category_group,
    active_legal_entity_id,
)
from src.llm.agents.retail.common import warehouse

# How many individual records a snapshot may name. Enough for a monitoring pass
# to cite the worst few by id; small enough that three copies of it is not the
# dominant cost of a run.
TOP_N = 12

# Said once, carried by every retail snapshot. These are the four ways to be
# confidently wrong about this dataset, and the model reads the snapshot before
# it reads anything else.
DATASET_NOTES: dict[str, str] = {
    "snapshot_date": (
        f"{warehouse.SNAPSHOT_DATE} is the only date in the data. There is no "
        "history, so nothing here can evidence a trend over time."
    ),
    "accuracy": (
        "Forecast accuracy 92.4% is a typed workbook constant, identical for "
        "all eight verticals. It is not a backtest and not a measurement."
    ),
    "empty_tables": (
        "fact_sales_daily, fact_price_daily, fact_promotion, "
        "fact_purchase_receipt and forecast_* are empty by design. Report a "
        "figure drawn from them as unavailable rather than substituting one."
    ),
    "grain": (
        "One grain: fact_inventory_daily, 16,000 rows, one per SKU per store. "
        "COUNTS ARE DISTINCT SKUs and money sums rows -- a SKU sits in about "
        "twenty stores, so a row count is roughly 20x any SKU figure (7,090 "
        "below-ROP rows against 524 below-ROP SKUs). Distinct counts do not "
        "add up across states or stores, because a SKU healthy in fourteen "
        "stores and stocked out in six is counted in both."
    ),
}


def scope_filters(
    legal_entity_id: str | None,
    category_group: str | None,
) -> tuple[str | None, str | None]:
    """Resolve an explicit argument, else the board filter the chat turn carries.

    The model is never told these parameters exist (see `common/tools/scope.py`
    for why), so in a chat turn both arrive as None and the ContextVars decide.
    A caller that passes a value explicitly always wins.
    """
    return (
        legal_entity_id if legal_entity_id is not None else active_legal_entity_id(),
        category_group if category_group is not None else active_category_group(),
    )


def where(
    legal_entity_id: str | None,
    category_group: str | None,
    *,
    entity_column: str,
    category_column: str | None = None,
    category_name_column: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """A WHERE fragment for the two filters, plus its bound parameters.

    Returns a fragment starting with ' AND ' or an empty string, matching
    `warehouse._scope_clause`, so it can be appended to a query that already
    has a WHERE.

    `category_group` matches `category_column` (the dashboard filter dropdown
    passes the real id, e.g. "GRC-C02") OR `category_name_column` when given
    (a chat turn has no way to know that id, so the model passes the label it
    was asked about, e.g. "Vegetable" -- matching only the id silently
    returns zero rows for every category a person would actually type).
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if legal_entity_id:
        clauses.append(f"{entity_column} = :legal_entity_id")
        params["legal_entity_id"] = legal_entity_id
    if category_group and category_column:
        if category_name_column:
            clauses.append(
                f"({category_column} = :category_group "
                f"OR {category_name_column} = :category_group)"
            )
        else:
            clauses.append(f"{category_column} = :category_group")
        params["category_group"] = category_group
    return (" AND " + " AND ".join(clauses) if clauses else "", params)


def envelope(
    agent_id: str,
    *,
    legal_entity_id: str | None,
    category_group: str | None,
    formulas: tuple[str, ...],
) -> dict[str, Any]:
    """The header every retail snapshot carries.

    `scope` is echoed back deliberately. A monitoring pass that received a
    narrowed snapshot and did not notice would raise a chain-wide alert from
    one vertical's figures.
    """
    return {
        "agent": agent_id,
        "as_of": warehouse.SNAPSHOT_DATE,
        "is_mock": True,
        "source_workbook": warehouse.SOURCE_WORKBOOK,
        "scope": {
            "legal_entity_id": legal_entity_id or "ALL",
            "category_group": category_group or "ALL",
        },
        "relevant_formulas": list(formulas),
        "formula_note": (
            "These are the rules this board evaluates. Call get_formula for an "
            "expression and evaluate_formula to compute one; do not restate a "
            "formula from memory or do the arithmetic yourself."
        ),
        "top_n": TOP_N,
        "top_n_note": (
            f"Ranked lists below are truncated to {TOP_N} rows. They are "
            "examples, not populations: never count them to get a total. "
            "Totals are in `totals` and the `by_*` breakdowns, which are "
            "computed over every row."
        ),
        "dataset_notes": DATASET_NOTES,
    }


def verticals(connection: Any) -> list[dict[str, Any]]:
    """The eight verticals, in the workbook's own order."""
    return _rows(
        connection,
        f"""
        SELECT vertical_id, dashboard_label
        FROM {warehouse.SCHEMA}.dim_vertical
        ORDER BY sort_order, vertical_id
        """,
        {},
    )


def reference(connection: Any, agent_id: str) -> list[dict[str, Any]]:
    """The workbook's own KPI figures for one agent, per vertical.

    Carried in every snapshot as the reconciliation anchor: a monitoring pass
    that computes a headline differing from these has either found something or
    made an error, and it cannot tell which without them.
    """
    return warehouse.agent_reference(connection, agent_id)


__all__ = [
    "DATASET_NOTES",
    "TOP_N",
    "envelope",
    "reference",
    "scope_filters",
    "verticals",
    "where",
    "_read_connection",
    "_rows",
]
