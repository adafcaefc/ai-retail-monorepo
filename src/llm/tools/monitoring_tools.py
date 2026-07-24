#all tools to do with monitoring the database will be here


#tool models
from typing import Literal, Any
from pydantic import BaseModel, Field


class MonitorCondition(BaseModel):
    field: str = Field(
        description="Column name to evaluate."
    )

    operator: Literal[
        ">",
        "<",
        ">=",
        "<=",
        "=",
        "!="
    ] = Field(
        description="Comparison operator."
    )

    value: Any = Field(
        description="Comparison value."
    )


class QueryRowsInput(BaseModel):
    table_name: str = Field(
        description="Name of the allowed table."
    )

    conditions: list[MonitorCondition] = Field(
        description="All conditions must be satisfied."
    )

class QueryRowsOutput(BaseModel):
    count: int
    rows: list[dict]




#tool functions
from sqlalchemy import text



def custom_query(
    query: str,
    engine,
) -> dict:
    """
    Execute a read-only SQL query and return results.
    """

    query_clean = query.strip().lower()

    if not query_clean.startswith("select"):
        raise ValueError(
            "Only SELECT statements are allowed."
        )

    forbidden_keywords = [
        "insert",
        "update",
        "delete",
        "drop",
        "truncate",
        "alter",
        "create",
        "merge",
        "replace",
        "grant",
        "revoke",
    ]

    for keyword in forbidden_keywords:
        if keyword in query_clean:
            raise ValueError(
                f"Forbidden operation detected: {keyword}"
            )

    with engine.connect() as conn:
        result = conn.execute(text(query))

        rows = [
            dict(row)
            for row in result.mappings().all()
        ]

    return {
        "count": len(rows),
        "rows": rows,
    }


ALLOWED_OPERATORS = {
    ">",
    "<",
    ">=",
    "<=",
    "=",
    "!=",
}


def value_compare_query(
    table_name: str,
    fields: list[str],
    operators: list[str],
    values: list,
    engine,
    allowed_tables: list[str]
) -> dict:
    """
    Return rows matching all supplied conditions.
    """

    if table_name not in allowed_tables:
        raise ValueError(
            f"Table '{table_name}' is not allowed."
        )

    if not (
        len(fields)
        == len(operators)
        == len(values)
    ):
        raise ValueError(
            "fields, operators and values must have the same length."
        )

    where_clauses = []
    params = {}

    for i, (field, operator, value) in enumerate(
        zip(fields, operators, values)
    ):

        if operator not in ALLOWED_OPERATORS:
            raise ValueError(
                f"Invalid operator: {operator}"
            )

        param_name = f"value_{i}"

        where_clauses.append(
            f"{field} {operator} :{param_name}"
        )

        params[param_name] = value

    where_sql = " AND ".join(where_clauses)

    sql = text(
        f"""
        SELECT *
        FROM {table_name}
        WHERE {where_sql}
        """
    )

    with engine.connect() as conn:
        result = conn.execute(sql, params)

        rows = [
            dict(row)
            for row in result.mappings().all()
        ]

    return {
        "count": len(rows),
        "rows": rows,
    }


#Simulate impact
import json
import re
from sqlalchemy import text


def parse_allowed_data(allowed_data):
    """
    Returns:
    {
        "employees": {
            "employee_id",
            "department",
            "salary"
        }
    }
    """
    if isinstance(allowed_data, str):
        allowed_data = json.loads(allowed_data)

    result = {}

    for table_name, table_info in allowed_data.items():
        result[table_name] = set(table_info["columns"].keys())

    return result


def extract_columns(expression: str) -> set[str]:
    """
    Extract likely column names from a SQL fragment.

    Ignores string literals, SQL keywords, and function names such as
    COUNT / LEAST / FILTER so validators do not treat functions as columns.
    """
    import sqlglot
    from sqlglot import exp
    from sqlglot.errors import ParseError

    text_expr = str(expression or "").strip()
    if not text_expr:
        return set()

    parse_candidates = (
        f"SELECT {text_expr}",
        f"SELECT 1 FROM _t WHERE {text_expr}",
        f"UPDATE _t SET {text_expr}",
    )
    for candidate in parse_candidates:
        try:
            tree = sqlglot.parse_one(candidate, read="postgres")
        except (ParseError, ValueError):
            continue
        columns = {
            column.name
            for column in tree.find_all(exp.Column)
            if column.name
        }
        if columns or "select 1 from" in candidate.lower():
            return columns

    # Fallback for odd fragments sqlglot cannot parse.
    cleaned = re.sub(r"'[^']*'", "", text_expr)
    # Drop function names: identifier immediately followed by '('.
    cleaned = re.sub(
        r"\b[a-zA-Z_][a-zA-Z0-9_]*\s*\(",
        "(",
        cleaned,
    )
    keywords = {
        "sum", "avg", "count", "min", "max",
        "and", "or", "in", "like", "between",
        "null", "is", "not", "case", "when",
        "then", "else", "end", "select", "from",
        "where", "join", "left", "right", "inner",
        "outer", "on", "as", "distinct", "coalesce",
        "true", "false", "asc", "desc", "limit",
        "offset", "group", "by", "order", "having",
        "union", "all", "exists", "any", "some",
        "cast", "over", "partition", "row", "rows",
        "completed", "started", "failed", "cancelled",
        "least", "greatest", "filter", "within",
        "array", "values", "with", "recursive",
        "lateral", "cross", "natural", "using",
        "interval", "current", "date", "time",
        "timestamp", "extract", "nullif", "greatest",
    }
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", cleaned)
    return {
        token
        for token in tokens
        if token.lower() not in keywords
    }


def validate_table(table_name, allowed_tables):
    if table_name not in allowed_tables:
        raise ValueError(
            f"Table '{table_name}' is not allowed."
        )


def validate_columns(
    table_name,
    expressions,
    allowed_tables,
):
    target_columns = allowed_tables[table_name]

    # Wildcard allow-list used by permissive workflows.
    if "*" in target_columns:
        return

    # Accept columns from any table in the domain allow-list so subqueries
    # that touch related tables (for example audit.import_batches) validate.
    allowed_columns = set()
    for table, columns in allowed_tables.items():
        allowed_columns.update(columns)
        if "." in table:
            schema, bare = table.split(".", 1)
            allowed_columns.add(schema)
            allowed_columns.add(bare)
        else:
            allowed_columns.add(table)

    used_columns = set()

    for expression in expressions:
        used_columns.update(
            extract_columns(expression)
        )

    invalid_columns = used_columns - allowed_columns

    if invalid_columns:
        raise ValueError(
            f"Invalid columns: {sorted(invalid_columns)}"
        )


def run_metrics(
    conn,
    table_name,
    where_clause,
    metric_expressions,
):
    results = {}

    for i, metric in enumerate(metric_expressions):
        # LLMs often emit "COUNT(*) AS label"; our wrapper already aliases
        # the result as metric_value, so strip any trailing AS alias.
        metric_sql = re.split(
            r"\s+AS\s+",
            str(metric).strip(),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        sql = f"""
        SELECT {metric_sql} AS metric_value
        FROM {table_name}
        WHERE {where_clause}
        """

        row = conn.execute(
            text(sql)
        ).mappings().first()

        results[metric] = (
            row["metric_value"]
            if row
            else None
        )

    return results

def simulate_impact(
    engine,
    table_name,
    where_clause,
    update_expression,
    metric_expressions,
    allowed_data,
):
    allowed_tables = parse_allowed_data(
        allowed_data
    )

    validate_table(
        table_name,
        allowed_tables,
    )

    expressions = [
        where_clause,
        update_expression,
        *metric_expressions,
    ]
    validate_columns(
        table_name,
        expressions,
        allowed_tables,
    )

    update_sql = f"""
    UPDATE {table_name}
    SET {update_expression}
    WHERE {where_clause}
    """

    with engine.connect() as conn:
        tx = conn.begin()

        try:
            before = run_metrics(
                conn,
                table_name,
                where_clause,
                metric_expressions,
            )

            result = conn.execute(
                text(update_sql)
            )

            after = run_metrics(
                conn,
                table_name,
                where_clause,
                metric_expressions,
            )

            tx.rollback()

            metrics = {}

            for metric in metric_expressions:
                before_value = before[metric]
                after_value = after[metric]

                metrics[metric] = {
                    "before": before_value,
                    "after": after_value,
                    "delta": (
                        after_value - before_value
                        if isinstance(before_value, (int, float))
                        and isinstance(after_value, (int, float))
                        else None
                    )
                }

            return {
                "rows_affected": result.rowcount,
                "metrics": metrics,
            }

        except Exception:
            tx.rollback()
            raise


def execute_impact(
    engine,
    table_name,
    where_clause,
    update_expression,
    metric_expressions,
    allowed_data,
):
    """
    Permanently apply an UPDATE and return before/after metrics.

    Unlike simulate_impact, this commits the transaction.
    """
    allowed_tables = parse_allowed_data(
        allowed_data
    )

    validate_table(
        table_name,
        allowed_tables,
    )

    expressions = [
        where_clause,
        update_expression,
        *metric_expressions,
    ]
    validate_columns(
        table_name,
        expressions,
        allowed_tables,
    )

    update_sql = f"""
    UPDATE {table_name}
    SET {update_expression}
    WHERE {where_clause}
    """

    with engine.connect() as conn:
        tx = conn.begin()

        try:
            before = run_metrics(
                conn,
                table_name,
                where_clause,
                metric_expressions,
            )

            result = conn.execute(
                text(update_sql)
            )

            after = run_metrics(
                conn,
                table_name,
                where_clause,
                metric_expressions,
            )

            tx.commit()

            metrics = {}

            for metric in metric_expressions:
                before_value = before[metric]
                after_value = after[metric]

                metrics[metric] = {
                    "before": before_value,
                    "after": after_value,
                    "delta": (
                        after_value - before_value
                        if isinstance(before_value, (int, float))
                        and isinstance(after_value, (int, float))
                        else None
                    )
                }

            return {
                "rows_affected": result.rowcount,
                "metrics": metrics,
                "committed": True,
            }

        except Exception:
            tx.rollback()
            raise


def _custom_query(query: str) -> dict:
    """Agent-facing wrapper that injects the shared SQLAlchemy engine."""
    from src.db.db import get_engine

    return custom_query(query, get_engine())


def _value_compare_query(
    table_name: str,
    fields: list[str],
    operators: list[str],
    values: list,
    allowed_data: str | dict | None = None,
) -> dict:
    """Agent-facing wrapper that injects the engine and optional table allow-list."""
    from src.db.db import get_engine

    if allowed_data is None:
        allowed_tables = [table_name]
    else:
        allowed_tables = list(parse_allowed_data(allowed_data).keys())

    return value_compare_query(
        table_name,
        fields,
        operators,
        values,
        get_engine(),
        allowed_tables,
    )


def _simulate_impact(
    table_name: str,
    where_clause: str,
    update_expression: str,
    metric_expressions: list[str],
    allowed_data: str | dict,
) -> dict:
    """Agent-facing wrapper that injects the shared SQLAlchemy engine."""
    from src.db.db import get_engine

    return simulate_impact(
        get_engine(),
        table_name,
        where_clause,
        update_expression,
        metric_expressions,
        allowed_data,
    )


def _execute_impact(
    table_name: str,
    where_clause: str,
    update_expression: str,
    metric_expressions: list[str],
    allowed_data: str | dict,
) -> dict:
    """Agent-facing wrapper that permanently applies an approved action."""
    from src.db.db import get_engine

    return execute_impact(
        get_engine(),
        table_name,
        where_clause,
        update_expression,
        metric_expressions,
        allowed_data,
    )


LOCAL_MONITORING_TOOLS = {
    "custom_query": _custom_query,
    "value_compare_query": _value_compare_query,
    "simulate_impact": _simulate_impact,
    "execute_impact": _execute_impact,
}