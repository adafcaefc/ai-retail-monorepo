"""Reads the Retail boards share: dimensions, filter options, and the rules.

WHAT THE BACKEND RETURNS, AND WHY IT IS NOT A FINISHED DASHBOARD
---------------------------------------------------------------
These builders return rows, not totals. The aggregation that turns 800 items
into KPI tiles, state charts and a risk register stays in
`frontend/src/agents/retail/*/data/selectors.js`, which has a test suite behind
it and is the only implementation of it anywhere.

Porting that to Python would create a second implementation of the same
arithmetic, which then has to be kept in step with the first forever. This
project spent its whole first phase removing exactly that duplication for
business rules — they live once, in `retail.formula`, read by both languages
and by the agents. Aggregation deserves the same treatment.

The consequence is worth stating plainly: because both paths run the same
selectors over the same rows, moving a board from its fixture to this API
cannot change a number on screen. `test_retail_dashboard_builders.py` asserts
that by comparing this payload to the checked-in fixture field by field.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.db.db import get_engine
from src.llm.agents.common.dashboard_scope import DashboardScope

SCHEMA = "retail"

# The workbook's own snapshot day. Written by `seed_retail_facts_from_json.py`;
# read here so a board never silently mixes two loads.
SNAPSHOT_DATE = "2026-07-01"

SOURCE_WORKBOOK = "Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx"

# Severity order, worst first. Shared because A2 ranks by it and A1 and A3 both
# describe rows with it.
STATE_ORDER: tuple[str, ...] = (
    "Stockout",
    "Low",
    "Expiry",
    "Overstock",
    "Slow-mover",
    "Healthy",
)

# The two states that sit below the reorder point, by construction of `f07`.
REPLENISH_STATES = frozenset({"Stockout", "Low"})

# What the route can actually narrow in SQL. The remaining scope fields are
# applied by the selectors over the rows returned here, so an API caller that
# is not the board sees them reported in `ignored_filters` — which is the truth
# for that caller.
SUPPORTED_FILTERS: frozenset[str] = frozenset({"legal_entity_id", "category_group"})


def _catalogue() -> dict[str, str]:
    """The whole catalogue, keyed by id — the same rules the browser evaluates.

    Reads `retail.formula`, which is also what the Formula Manager writes and
    what the agents' formula tools quote. It used to read
    `resources/dbtemp/formula.json` directly, and that was fine while the
    Formula Manager was the only other reader — but once an agent could cite a
    rule, a file the API had rewritten in another process meant the board and
    the agent could disagree about what a formula says. One store, one answer.

    Deliberately not cached. The old `lru_cache(maxsize=1)` was correct for a
    file that could not change within a process; a table the Formula Manager
    edits can, and a board still drawing last hour's rule after someone fixed
    it is the bug this move was meant to end. A 22-row read on a warmed pool is
    not what makes a dashboard request slow.
    """
    from src.formulas import repository

    return {entry["id"]: entry["expression"] for entry in repository.load()}


def formulas(wanted: tuple[str, ...]) -> dict[str, str]:
    """The expressions one agent's engine needs, and no others.

    Sent as data rather than evaluated here, because the What-If engine runs in
    the browser — a lever drag re-evaluates 800 rows and a round trip per frame
    would make the control unusable. Narrowed per agent so a board carries the
    rules it runs and nothing else.

    A missing id raises rather than being skipped: the browser would fail on it
    anyway, and failing here names the formula instead of the symptom.
    """
    catalogue = _catalogue()
    missing = [name for name in wanted if name not in catalogue]
    if missing:
        raise ValueError(
            f"retail.formula is missing {', '.join(missing)}. "
            "Seed it: python scripts/import_formulas_to_db.py"
        )
    return {name: catalogue[name] for name in wanted}


def _rows(connection: Any, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    return [dict(row) for row in connection.execute(text(sql), params or {}).mappings()]


def _scope_clause(
    scope: DashboardScope,
    entity_col: str,
    category_col: str | None,
    store_col: str | None = None,
):
    """The WHERE fragment and parameters for the columns a query really has.

    ``store_id`` is optional because the chain fact tables deliberately do not
    have a store key.  Callers must pass the real store dimension column when
    the query is store-grain; omitting it means no pretend predicate is added
    to a chain-level query.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if scope.legal_entity_id:
        clauses.append(f"{entity_col} = :legal_entity_id")
        params["legal_entity_id"] = scope.legal_entity_id
    if scope.category_group and category_col:
        clauses.append(f"{category_col} = :category_group")
        params["category_group"] = scope.category_group
    if scope.store_id and store_col:
        clauses.append(f"{store_col} = :store_id")
        params["store_id"] = scope.store_id
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def filter_options(connection: Any) -> dict[str, list]:
    """Every dropdown's full list.

    Deliberately not narrowed by the scope: the selectors narrow categories and
    stores to the chosen vertical themselves, and a dropdown that only offers
    what is already selected cannot be used to change the selection.
    """
    verticals = _rows(
        connection,
        f"""
        SELECT vertical_id, name, dashboard_label
        FROM {SCHEMA}.dim_vertical
        -- The workbook's own order, not alphabetical: Grocery has been the
        -- first entry on these boards since before there was a database.
        ORDER BY sort_order, vertical_id
        """,
    )
    categories = _rows(
        connection,
        f"""
        SELECT DISTINCT category_id, category_name, vertical_id
        FROM {SCHEMA}.dim_item
        WHERE category_id IS NOT NULL
        ORDER BY category_id
        """,
    )
    stores = _rows(
        connection,
        f"""
        SELECT store_id, name, vertical_id, cluster
        FROM {SCHEMA}.dim_store
        ORDER BY store_id
        """,
    )

    return {
        "legal_entities": [
            {
                "value": row["vertical_id"],
                "label": f"{row['vertical_id']} · {row['name']}",
                "dashboard_label": row["dashboard_label"],
            }
            for row in verticals
        ],
        "categories": [
            {
                "value": row["category_id"],
                "label": row["category_name"],
                "legal_entity_id": row["vertical_id"],
            }
            for row in categories
        ],
        "stores": [
            {
                "value": row["store_id"],
                "label": f"{row['store_id']} · {row['name']}",
                "legal_entity_id": row["vertical_id"],
                "cluster": row["cluster"],
            }
            for row in stores
        ],
        "states": list(STATE_ORDER),
    }


def chain_store_size(connection: Any) -> dict[str, float]:
    """Each vertical's total store-size index.

    Summed from `dim_store` rather than read from the vertical's own
    `sum_store_size`, which the workbook rounds to four places — enough drift
    to move `f01` off the figures every board reconciles against.
    """
    rows = _rows(
        connection,
        f"""
        SELECT vertical_id, sum(size_index) AS total
        FROM {SCHEMA}.dim_store
        GROUP BY vertical_id
        """,
    )
    return {row["vertical_id"]: float(row["total"]) for row in rows}


def constants() -> dict[str, float]:
    """Model parameters, from the catalogue's own reference rather than a table.

    `dow_sum` and `month_index` are inputs to `f08` and `f01`. They are not
    facts about a day, so they do not belong in a fact table — a second home
    for one number is how two numbers appear.
    """
    return {"dow_sum": 7.45, "month_index": 6}


def agent_reference(connection: Any, agent_id: str) -> list[dict[str, Any]]:
    """One agent's own KPI sheet, per vertical — the reconciliation anchors.

    Stored long-format so agents 4 to 9 join in without a schema change, and
    pivoted back here to the wide shape the sheet states them in.

    Ordered by `vertical_id`, which is alphabetical and deliberately NOT the
    `sort_order` the item lists follow. The reference block is a table nobody
    scrolls in the UI; the fixture builders sorted it by id, and matching that
    is what keeps the two paths byte-comparable.

    Whole values come back whole. Long format has one `DOUBLE PRECISION`
    column, so every metric would otherwise arrive as a float and a card would
    read "46.0 SKUs". Rather than list which metrics are counts per agent, the
    rule is simply that a value the workbook stored whole stays whole — which
    is true of `stockout_risk_skus` and of `inventory_value` alike, and stays
    true for agents 4 to 9 without anybody maintaining a list.
    """
    rows = _rows(
        connection,
        f"""
        SELECT r.vertical_id, r.metric, r.value, v.dashboard_label
        FROM {SCHEMA}.agent_kpi_reference r
        JOIN {SCHEMA}.dim_vertical v ON v.vertical_id = r.vertical_id
        WHERE r.agent_id = :agent
        ORDER BY r.vertical_id, r.metric
        """,
        {"agent": agent_id},
    )

    by_vertical: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_vertical.setdefault(
            row["vertical_id"],
            {
                "legal_entity_id": row["vertical_id"],
                "vertical_label": row["dashboard_label"],
            },
        )
        value = row["value"]
        entry[row["metric"]] = (
            int(value) if value is not None and float(value).is_integer() else value
        )

    return list(by_vertical.values())


def envelope(agent: str, note: str) -> dict[str, Any]:
    """The metadata every Retail payload carries.

    `is_mock` stays true. The rows are real workbook figures, but they are one
    demonstration snapshot, not a live ERP position, and the boards say so on
    screen. It flips when D365 is the source, not when Postgres is.
    """
    return {
        "schema_version": 1,
        "agent": agent,
        "generated_at": f"{SNAPSHOT_DATE}T00:00:00+00:00",
        "is_mock": True,
        "note": note,
        "source_workbook": SOURCE_WORKBOOK,
    }


__all__ = [
    "REPLENISH_STATES",
    "SCHEMA",
    "SNAPSHOT_DATE",
    "STATE_ORDER",
    "SUPPORTED_FILTERS",
    "chain_store_size",
    "constants",
    "envelope",
    "filter_options",
    "formulas",
    "get_engine",
    "_rows",
    "_scope_clause",
]
