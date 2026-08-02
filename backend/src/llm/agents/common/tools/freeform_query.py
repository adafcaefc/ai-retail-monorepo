"""Generic free-form SQL execution with type, table, and row limits."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Sequence
from contextvars import ContextVar, Token
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal

import sqlglot
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlglot import exp
from sqlglot.errors import ParseError

from src.db.db import get_engine

SqlType = Literal[
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "WITH",
]

_SQL_DIALECT = "postgres"

# Finance reads the `newdata` star schema. The allow-list has to move with it:
# a chat agent free-querying `financial_performance.*` while the board is built
# from `newdata` is QC-002 returning through a different door — same screen, two
# datasets, no way for the reader to tell which is which.
#
# `simulator_levers` is the deliberate exception. The new dataset defines no
# levers, so that one table is still the old schema's, exactly as
# `performance_data._simulator_levers` reads it.
FINANCE_ALLOWED_TABLES = (
    "audit.import_batches",
    "newdata.dim_legal_entity",
    "newdata.dim_store",
    "newdata.dim_category",
    "newdata.dim_item",
    "newdata.fact_sales",
    "newdata.fact_budget",
    "newdata.fact_opex",
    "newdata.finance_pl",
    "newdata.finance_ebitda_bridge",
    "newdata.finance_by_entity",
    "newdata.finance_by_category",
    "newdata.finance_by_store",
    "newdata.finance_by_item",
    "newdata.finance_by_month",
    "newdata.agent_kpis",
    "financial_performance.simulator_levers",
)

CASHFLOW_ALLOWED_TABLES = (
    "audit.import_batches",
    "cashflow.assumptions",
    "cashflow.ar_collections",
    "cashflow.ap_payables",
    "cashflow.other_outflows",
    "cashflow.weekly_forecast",
    "cashflow.fx_scenarios",
    "cashflow.recommendations",
)

COLLECTIONS_ALLOWED_TABLES = (
    "audit.import_batches",
    "collections.assumptions",
    "collections.customer_credit_aging",
    "collections.risk_scores",
    "collections.dso_cash_impact",
    "collections.risk_tier_exposure",
    "collections.worklist",
    "collections.recommendations",
)

LEAKAGE_ALLOWED_TABLES = (
    "audit.import_batches",
    "payment_leakage.assumptions",
    "payment_leakage.ap_transactions",
    "payment_leakage.anomaly_detections",
    "payment_leakage.category_breakdowns",
    "payment_leakage.summary",
    "payment_leakage.action_worklist",
    "payment_leakage.recommendations",
)

DOMAIN_ALLOWED_TABLES: dict[str, tuple[str, ...]] = {
    "finance": FINANCE_ALLOWED_TABLES,
    "cashflow": CASHFLOW_ALLOWED_TABLES,
    "collection": COLLECTIONS_ALLOWED_TABLES,
    "leakage": LEAKAGE_ALLOWED_TABLES,
}

# Domain whose agent is currently running. Simulation/execution tools read
# this instead of trusting a model-supplied allow-list.
_simulation_domain: ContextVar[str | None] = ContextVar(
    "simulation_domain",
    default=None,
)

DOMAIN_QUERY_MAX_ROWS = 100

_STATEMENT_TYPE_BY_NODE: dict[type[exp.Expression], str] = {
    exp.Select: "SELECT",
    exp.Union: "SELECT",
    exp.Except: "SELECT",
    exp.Intersect: "SELECT",
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Delete: "DELETE",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _normalize_table_name(raw: str) -> str:
    parts = [
        part.strip().strip('"').lower()
        for part in raw.split(".")
        if part.strip()
    ]
    return ".".join(parts)


def _normalize_allowed_tables(
    allowed_tables: Iterable[str],
) -> set[str]:
    return {
        _normalize_table_name(table)
        for table in allowed_tables
    }


def _normalize_allowed_types(
    allowed_types: Iterable[str],
) -> set[str]:
    return {
        statement_type.strip().upper()
        for statement_type in allowed_types
    }


def _parse_single_statement(query: str) -> exp.Expression:
    try:
        statements = sqlglot.parse(
            query,
            read=_SQL_DIALECT,
        )
    except ParseError as exc:
        raise ValueError(
            f"Failed to parse SQL: {exc}"
        ) from exc

    expressions = [
        statement
        for statement in statements
        if statement is not None
    ]
    if not expressions:
        raise ValueError("Query must not be empty.")
    if len(expressions) > 1:
        raise ValueError(
            "Only one SQL statement is allowed per list item."
        )
    return expressions[0]


def _detect_statement_type(
    expression: exp.Expression,
) -> str:
    for node_type, statement_type in _STATEMENT_TYPE_BY_NODE.items():
        if isinstance(expression, node_type):
            if (
                statement_type == "SELECT"
                and expression.args.get("with") is not None
            ):
                return "WITH"
            return statement_type

    raise ValueError(
        f"Unsupported SQL statement type: {type(expression).__name__}. "
        "Allowed: SELECT, WITH, INSERT, UPDATE, DELETE."
    )


def _cte_aliases(expression: exp.Expression) -> set[str]:
    aliases: set[str] = set()
    for cte in expression.find_all(exp.CTE):
        alias = cte.alias_or_name
        if alias:
            aliases.add(alias.strip('"').lower())
    return aliases


def _table_qualified_name(table: exp.Table) -> str:
    parts: list[str] = []
    if table.catalog:
        parts.append(table.catalog)
    if table.db:
        parts.append(table.db)
    if table.name:
        parts.append(table.name)
    return _normalize_table_name(".".join(parts))


def _extract_table_names(
    expression: exp.Expression,
) -> set[str]:
    cte_aliases = _cte_aliases(expression)
    tables: set[str] = set()
    for table in expression.find_all(exp.Table):
        qualified = _table_qualified_name(table)
        if not qualified:
            continue
        # CTE references are not physical tables.
        if (
            "." not in qualified
            and qualified in cte_aliases
        ):
            continue
        tables.add(qualified)
    return tables


def _statement_type_allowed(
    statement_type: str,
    allowed_types: set[str],
) -> bool:
    if statement_type in allowed_types:
        return True
    # WITH ... SELECT is allowed whenever SELECT is allowed.
    if statement_type == "WITH" and "SELECT" in allowed_types:
        return True
    return False


def _resolve_tables_against_allowlist(
    referenced: set[str],
    allowed_tables: set[str],
) -> list[str]:
    unresolved: list[str] = []
    for table in sorted(referenced):
        if table in allowed_tables:
            continue
        if "." not in table:
            matches = [
                allowed
                for allowed in allowed_tables
                if allowed.endswith(f".{table}")
            ]
            if len(matches) == 1:
                continue
            if len(matches) > 1:
                unresolved.append(
                    f"{table} (ambiguous; use a schema-qualified name)"
                )
                continue
        unresolved.append(table)
    return unresolved


def _validate_query(
    query: str,
    *,
    allowed_types: set[str],
    allowed_tables: set[str],
) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("Query must not be empty.")

    expression = _parse_single_statement(cleaned)
    statement_type = _detect_statement_type(expression)

    if not _statement_type_allowed(
        statement_type,
        allowed_types,
    ):
        raise ValueError(
            f"Statement type {statement_type} is not allowed. "
            f"Allowed types: {sorted(allowed_types)}."
        )

    referenced = _extract_table_names(expression)
    if not referenced:
        raise ValueError(
            "Could not determine which tables the query references."
        )

    unresolved = _resolve_tables_against_allowlist(
        referenced,
        allowed_tables,
    )
    if unresolved:
        raise ValueError(
            "Query references tables outside the allow-list: "
            + ", ".join(unresolved)
            + f". Allowed tables: {sorted(allowed_tables)}."
        )

    return cleaned.rstrip().rstrip(";")


def freeform_query(
    queries: Sequence[str],
    *,
    allowed_types: Sequence[str],
    allowed_tables: Sequence[str],
    max_rows: int,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """
    Execute a list of free-form SQL statements under type/table/row constraints.

    Parameters
    ----------
    queries:
        One SQL statement per list item.
    allowed_types:
        Statement kinds permitted for this call (e.g. ``["SELECT"]``).
        ``WITH`` CTE queries are treated as SELECT when SELECT is allowed.
    allowed_tables:
        Schema-qualified table names the statements may reference.
    max_rows:
        Maximum number of result rows returned per query (extra rows truncated).
    """

    if max_rows < 1:
        raise ValueError("max_rows must be at least 1.")
    if not queries:
        raise ValueError("queries must contain at least one SQL statement.")

    type_allow = _normalize_allowed_types(allowed_types)
    table_allow = _normalize_allowed_tables(allowed_tables)
    if not type_allow:
        raise ValueError("allowed_types must not be empty.")
    if not table_allow:
        raise ValueError("allowed_tables must not be empty.")

    sql_engine = engine or get_engine()
    read_only = type_allow <= {"SELECT", "WITH"}
    results: list[dict[str, Any]] = []

    with sql_engine.connect() as connection:
        if read_only:
            connection.execute(text("SET TRANSACTION READ ONLY"))

        for index, raw_query in enumerate(queries):
            validated = _validate_query(
                raw_query,
                allowed_types=type_allow,
                allowed_tables=table_allow,
            )
            result = connection.execute(text(validated))

            if result.returns_rows:
                mappings = result.mappings().all()
                truncated = len(mappings) > max_rows
                rows = [
                    {
                        str(key): _json_value(value)
                        for key, value in row.items()
                    }
                    for row in mappings[:max_rows]
                ]
                results.append(
                    {
                        "index": index,
                        "query": validated,
                        "count": len(rows),
                        "truncated": truncated,
                        "max_rows": max_rows,
                        "rows": rows,
                    }
                )
            else:
                if read_only:
                    connection.rollback()
                    raise ValueError(
                        "Write statements are not permitted for this tool configuration."
                    )
                connection.commit()
                results.append(
                    {
                        "index": index,
                        "query": validated,
                        "count": result.rowcount,
                        "truncated": False,
                        "max_rows": max_rows,
                        "rows": [],
                        "rowcount": result.rowcount,
                    }
                )

    return {
        "result_count": len(results),
        "max_rows": max_rows,
        "results": results,
    }


def _domain_query(
    queries: list[str],
    *,
    allowed_tables: Sequence[str],
) -> dict[str, Any]:
    return freeform_query(
        queries,
        allowed_types=["SELECT"],
        allowed_tables=allowed_tables,
        max_rows=DOMAIN_QUERY_MAX_ROWS,
    )


def query_financial_performance(
    queries: list[str],
) -> dict[str, Any]:
    """
    Run free-form SELECT queries against the newdata finance tables.

    Accepts a list of SQL SELECT statements (one statement per list item).
    Each result set is capped at 100 rows (truncated=true when more matched).
    Allowed tables: the newdata dimensions (dim_*), facts (fact_sales,
    fact_budget, fact_opex) and derived Finance packs (finance_*).
    Prefer get_financial_performance_snapshot for a standard overview; use this
    when you need custom filters, joins, or columns beyond the snapshot.

    Do NOT filter by import_batch_id: the newdata tables do not have that
    column. The whole workbook is one batch, so there is nothing to
    discriminate. Scope a query by legal_entity_id and by month or
    month_index instead. The snapshot covers month_index >= 202510, the twelve
    months to September 2026; use the same window to agree with the dashboard.
    """

    return _domain_query(
        queries,
        allowed_tables=FINANCE_ALLOWED_TABLES,
    )


def query_cashflow(
    queries: list[str],
) -> dict[str, Any]:
    """
    Run free-form SELECT queries against cashflow tables.

    Accepts a list of SQL SELECT statements (one statement per list item).
    Each result set is capped at 100 rows (truncated=true when more matched).
    Allowed tables: audit.import_batches and all cashflow.* tables.
    Prefer get_cashflow_baseline for the standard forecast view; use this when
    you need custom filters, joins, or columns beyond the baseline.
    Always scope domain rows with the latest completed import_batch_id.
    """

    return _domain_query(
        queries,
        allowed_tables=CASHFLOW_ALLOWED_TABLES,
    )


def query_collections(
    queries: list[str],
) -> dict[str, Any]:
    """
    Run free-form SELECT queries against collections tables.

    Accepts a list of SQL SELECT statements (one statement per list item).
    Each result set is capped at 100 rows (truncated=true when more matched).
    Allowed tables: audit.import_batches and all collections.* tables.
    Prefer get_collections_snapshot for the standard portfolio view; use this
    when you need custom filters, joins, or columns beyond the snapshot.
    Always scope domain rows with the latest completed import_batch_id.
    """

    return _domain_query(
        queries,
        allowed_tables=COLLECTIONS_ALLOWED_TABLES,
    )


def query_payment_leakage(
    queries: list[str],
) -> dict[str, Any]:
    """
    Run free-form SELECT queries against payment_leakage tables.

    Accepts a list of SQL SELECT statements (one statement per list item).
    Each result set is capped at 100 rows (truncated=true when more matched).
    Allowed tables: audit.import_batches and all payment_leakage.* tables.
    Prefer get_payment_leakage_snapshot for the standard overview; use this
    when you need custom filters, joins, or columns beyond the snapshot.
    Always scope domain rows with the latest completed import_batch_id.
    """

    return _domain_query(
        queries,
        allowed_tables=LEAKAGE_ALLOWED_TABLES,
    )


def _short_type(row: dict[str, Any]) -> str:
    """Collapse information_schema type columns into one short token."""
    data_type = str(row["data_type"])
    if data_type == "character varying":
        length = row["character_maximum_length"]
        return f"varchar({length})" if length else "varchar"
    if data_type == "timestamp with time zone":
        return "timestamptz"
    if data_type == "timestamp without time zone":
        return "timestamp"
    if data_type == "double precision":
        return "float8"
    if data_type == "USER-DEFINED":
        return str(row["udt_name"])
    return data_type


def describe_tables(
    *,
    allowed_tables: Sequence[str],
    tables: Sequence[str] | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """
    Return live PostgreSQL column metadata and CHECK constraints.

    Results are cached per (allow-list, requested tables): every monitoring
    pass asks for the same schema, and each miss costs several remote round
    trips. Call clear_schema_cache() after a migration. An explicit engine
    (tests) bypasses the cache.
    """
    if engine is not None:
        return _describe_tables_uncached(
            allowed_tables=allowed_tables,
            tables=tables,
            engine=engine,
        )
    cached = _describe_tables_cached(
        tuple(allowed_tables),
        tuple(tables) if tables is not None else None,
    )
    return copy.deepcopy(cached)


@lru_cache(maxsize=32)
def _describe_tables_cached(
    allowed_tables: tuple[str, ...],
    tables: tuple[str, ...] | None,
) -> dict[str, Any]:
    return _describe_tables_uncached(
        allowed_tables=allowed_tables,
        tables=tables,
    )


def clear_schema_cache() -> None:
    """Drop cached describe_tables results (call after a schema migration)."""
    _describe_tables_cached.cache_clear()


def _describe_tables_uncached(
    *,
    allowed_tables: Sequence[str],
    tables: Sequence[str] | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """
    Return live PostgreSQL column metadata and CHECK constraints.

    Use this before writing SQL so column names match the real database.
    Unknown requested tables are ignored with a warning; only allow-listed
    tables are described.
    """
    allowed = _normalize_allowed_tables(allowed_tables)
    ignored_tables: list[str] = []
    if tables:
        requested = {
            _normalize_table_name(table)
            for table in tables
        }
        ignored_tables = sorted(requested - allowed)
        target_tables = sorted(requested & allowed)
        # Soft-fail: never raise on invented names. Always return
        # allowed_tables so the model can retry with real names.
        if not target_tables:
            return {
                "allowed_tables": sorted(allowed),
                "tables": {},
                "check_constraints": {},
                "table_count": 0,
                "column_count": 0,
                "ignored_tables": ignored_tables,
                "warning": (
                    "None of the requested tables are allowed. "
                    f"Requested={sorted(requested)}. "
                    "Call describe_*_tables() with no tables argument, or "
                    "only pass names from allowed_tables."
                ),
            }
    else:
        target_tables = sorted(allowed)

    where_parts: list[str] = []
    params: dict[str, Any] = {}
    for index, table in enumerate(target_tables):
        if "." not in table:
            raise ValueError(
                f"Table {table!r} must be schema-qualified "
                "(example: payment_leakage.summary)."
            )
        schema, name = table.split(".", 1)
        where_parts.append(
            f"(table_schema = :schema_{index} AND table_name = :table_{index})"
        )
        params[f"schema_{index}"] = schema
        params[f"table_{index}"] = name

    db = engine or get_engine()
    rows: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    with db.connect() as connection:
        result = connection.execute(
            text(
                f"""
                SELECT
                    table_schema,
                    table_name,
                    column_name,
                    data_type,
                    udt_name,
                    is_nullable,
                    character_maximum_length
                FROM information_schema.columns
                WHERE {" OR ".join(where_parts)}
                ORDER BY
                    table_schema,
                    table_name,
                    ordinal_position
                """
            ),
            params,
        )
        rows = [dict(row) for row in result.mappings().all()]

        check_where = []
        check_params: dict[str, Any] = {}
        for index, table in enumerate(target_tables):
            schema, name = table.split(".", 1)
            check_where.append(
                f"(n.nspname = :cs_{index} AND c.relname = :ct_{index})"
            )
            check_params[f"cs_{index}"] = schema
            check_params[f"ct_{index}"] = name
        check_result = connection.execute(
            text(
                f"""
                SELECT
                    n.nspname AS table_schema,
                    c.relname AS table_name,
                    con.conname AS constraint_name,
                    pg_get_constraintdef(con.oid) AS definition
                FROM pg_constraint con
                JOIN pg_class c
                  ON c.oid = con.conrelid
                JOIN pg_namespace n
                  ON n.oid = c.relnamespace
                WHERE con.contype = 'c'
                  AND ({" OR ".join(check_where)})
                ORDER BY n.nspname, c.relname, con.conname
                """
            ),
            check_params,
        )
        checks = [dict(row) for row in check_result.mappings().all()]

    by_table: dict[str, list[dict[str, Any]]] = {
        table: [] for table in target_tables
    }
    for row in rows:
        qualified = (
            f"{row['table_schema']}.{row['table_name']}".lower()
        )
        if qualified not in by_table:
            continue
        # Compact "name type" strings rather than one object per column. The
        # agents only ever need the name and the type; the verbose form tripled
        # the token cost of a payload that is re-sent on every turn.
        column = f"{row['column_name']} {_short_type(row)}"
        if row["is_nullable"] != "YES":
            column += " NOT NULL"
        by_table[qualified].append(column)

    check_by_table: dict[str, list[str]] = {
        table: [] for table in target_tables
    }
    for row in checks:
        qualified = (
            f"{row['table_schema']}.{row['table_name']}".lower()
        )
        if qualified not in check_by_table:
            continue
        check_by_table[qualified].append(str(row["definition"]))

    payload: dict[str, Any] = {
        "allowed_tables": sorted(allowed),
        "tables": by_table,
        "check_constraints": check_by_table,
        "table_count": len(by_table),
        "column_count": sum(len(cols) for cols in by_table.values()),
    }
    if ignored_tables:
        payload["ignored_tables"] = ignored_tables
        payload["warning"] = (
            "Ignored tables outside the allow-list: "
            f"{ignored_tables}. Use only allowed_tables."
        )
    return payload


def set_simulation_domain(domain: str) -> Token:
    """Scope simulation/execution tools to one domain's tables."""
    return _simulation_domain.set(domain)


def reset_simulation_domain(token: Token) -> None:
    _simulation_domain.reset(token)


def current_simulation_domain() -> str | None:
    return _simulation_domain.get()


def domain_for_table(table_name: str) -> str | None:
    """Return the domain owning a table, ignoring shared audit tables."""
    normalized = _normalize_table_name(table_name)
    for domain, tables in DOMAIN_ALLOWED_TABLES.items():
        for table in tables:
            if table.startswith("audit."):
                continue
            if table == normalized:
                return domain
    return None


def _split_column_entry(entry: Any) -> tuple[str, str]:
    """
    Split a describe_tables column entry into (name, type).

    describe_tables emits compact "name type [NOT NULL]" strings; older callers
    passed dicts, so both shapes are accepted.
    """
    if isinstance(entry, dict):
        return (
            str(entry.get("column") or ""),
            str(entry.get("data_type") or "unknown"),
        )
    parts = str(entry).split(" ", 1)
    if len(parts) == 1:
        return parts[0], "unknown"
    return parts[0], parts[1].removesuffix(" NOT NULL").strip() or "unknown"


@lru_cache(maxsize=8)
def _allowed_data_for_tables(
    allowed_tables: tuple[str, ...],
) -> dict[str, Any]:
    schema = describe_tables(allowed_tables=allowed_tables)
    allowed: dict[str, Any] = {}
    for table, columns in (schema.get("tables") or {}).items():
        allowed[table] = {
            "columns": dict(
                _split_column_entry(column) for column in columns
            ),
            "check_constraints": (
                (schema.get("check_constraints") or {}).get(table) or []
            ),
        }
    return allowed


def allowed_data_for_domain(domain: str) -> dict[str, Any]:
    """
    Return the allow-list of tables/columns/CHECK constraints for a domain.

    Reads live column names from information_schema so invented columns fail
    validation before any SQL runs. Cached per process; the result is a copy
    so callers cannot poison the cache.
    """
    tables = DOMAIN_ALLOWED_TABLES.get(domain)
    if tables is None:
        raise ValueError(
            f"Unknown domain {domain!r}. "
            f"Allowed: {', '.join(sorted(DOMAIN_ALLOWED_TABLES))}."
        )
    return copy.deepcopy(_allowed_data_for_tables(tables))


def clear_allowed_data_cache() -> None:
    """Drop cached schema, for use after a migration."""
    _allowed_data_for_tables.cache_clear()


def describe_financial_performance_tables(
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """
    List live columns for financial_performance allow-listed tables.

    Call this before writing custom SQL or impact simulations so you only use
    real column names. Optional tables filter must stay inside the allow-list.
    """
    return describe_tables(
        allowed_tables=FINANCE_ALLOWED_TABLES,
        tables=tables,
    )


def describe_cashflow_tables(
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """
    List live columns for cashflow allow-listed tables.

    Call this before writing custom SQL or impact simulations so you only use
    real column names. Optional tables filter must stay inside the allow-list.
    """
    return describe_tables(
        allowed_tables=CASHFLOW_ALLOWED_TABLES,
        tables=tables,
    )


def describe_collections_tables(
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """
    List live columns for collections allow-listed tables.

    Call this before writing custom SQL or impact simulations so you only use
    real column names. Optional tables filter must stay inside the allow-list.
    """
    return describe_tables(
        allowed_tables=COLLECTIONS_ALLOWED_TABLES,
        tables=tables,
    )


def describe_payment_leakage_tables(
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """
    List live columns for payment_leakage allow-listed tables.

    Call this before writing custom SQL or impact simulations so you only use
    real column names. Optional tables filter must stay inside the allow-list.
    Note: audit.import_batches uses import_status (not status).
    """
    return describe_tables(
        allowed_tables=LEAKAGE_ALLOWED_TABLES,
        tables=tables,
    )


LOCAL_FREEFORM_QUERY_TOOLS = {
    "query_financial_performance": query_financial_performance,
    "query_cashflow": query_cashflow,
    "query_collections": query_collections,
    "query_payment_leakage": query_payment_leakage,
    "describe_financial_performance_tables": describe_financial_performance_tables,
    "describe_cashflow_tables": describe_cashflow_tables,
    "describe_collections_tables": describe_collections_tables,
    "describe_payment_leakage_tables": describe_payment_leakage_tables,
}


__all__ = [
    "CASHFLOW_ALLOWED_TABLES",
    "COLLECTIONS_ALLOWED_TABLES",
    "DOMAIN_QUERY_MAX_ROWS",
    "FINANCE_ALLOWED_TABLES",
    "LEAKAGE_ALLOWED_TABLES",
    "LOCAL_FREEFORM_QUERY_TOOLS",
    "clear_schema_cache",
    "describe_cashflow_tables",
    "describe_collections_tables",
    "describe_financial_performance_tables",
    "describe_payment_leakage_tables",
    "describe_tables",
    "freeform_query",
    "query_cashflow",
    "query_collections",
    "query_financial_performance",
    "query_payment_leakage",
]
