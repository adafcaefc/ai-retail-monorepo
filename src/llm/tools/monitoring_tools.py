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
    Extract column names from a SQL fragment.

    department = 'Sales'
    salary = salary * 1.1
ary)

    -> {"department", "salary"}
    """

    expression = re.sub(r"'[^']*'", "", expression)

    keywords = {
        "sum", "avg", "count", "min", "max",
        "and", "or", "in", "like",
        "null", "is", "case", "when",
        "then", "else", "end",
    }

    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", expression)

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
    allowed_columns = allowed_tables[table_name]

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
        sql = f"""
        SELECT {metric} AS metric_value
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

    validate_columns(
        table_name,
        [
            where_clause,
            update_expression,
            metric_expressions,
        ],
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