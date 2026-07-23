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