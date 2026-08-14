"""Deterministic compiler for policy-approved adaptive QuerySpecs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .policy import QuerySpec
from .catalog import CATALOG

LINEAGE_COLUMNS = ("source_load_id", "source_sheet", "source_row", "loaded_at")


def _quote(identifier: str) -> str:
    # QuerySpec has already checked this, but keep the compiler defensive if
    # called directly with an object assembled outside QueryPolicy.
    if not identifier.replace("_", "a").isalnum() or not (identifier[0].isalpha() or identifier[0] == "_"):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f"[{identifier}]"


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: tuple[Any, ...]
    metric_id: str
    source_table: str
    requirement_index: int
    max_rows: int
    result_fields: tuple[str, ...]


class DeterministicSqlCompiler:
    """Generate a fixed-shape, read-only Azure SQL statement."""

    def compile(self, spec: QuerySpec) -> CompiledQuery:
        metric = next((item for item in CATALOG.metrics if item.metric_id == spec.metric_id), None)
        if metric is None or metric.table != spec.table or metric.column != spec.column:
            raise ValueError("QuerySpec metric/source is not in the active catalog")
        if spec.aggregation != "none" and spec.aggregation not in metric.allowed_aggregations:
            raise ValueError("QuerySpec aggregation is not in the active catalog")
        if any(dimension not in metric.dimensions for dimension in spec.dimensions):
            raise ValueError("QuerySpec dimension is not in the active catalog")
        catalog_table = next((item for item in CATALOG.tables if item.name == spec.table), None)
        if catalog_table is None:
            raise ValueError("QuerySpec table is not in the active catalog")
        if spec.time_field != metric.time_field:
            raise ValueError("QuerySpec time field is not in the active catalog")
        if spec.time_window is not None and metric.time_field is None:
            raise ValueError("QuerySpec time window has no approved catalog field")
        catalog_columns = {item.name for item in catalog_table.columns}
        for item in spec.filters:
            if item.field not in catalog_table.approved_filters or item.field not in catalog_columns:
                raise ValueError("QuerySpec filter is not in the active catalog")
        table_name = spec.table.split(".", 1)
        if len(table_name) != 2 or table_name[0] != "retail":
            raise ValueError("Only retail sources may be compiled")
        table = _quote(table_name[0]) + "." + _quote(table_name[1])
        if spec.aggregation == "none":
            select_parts = [f"{_quote(field)} AS {_quote(field)}" for field in spec.dimensions]
            select_parts.append(f"{_quote(spec.column)} AS [metric_value]")
            result_fields = tuple(spec.dimensions) + ("metric_value",)
        else:
            function = {
                "sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX", "count": "COUNT"
            }[spec.aggregation]
            select_parts = [f"{_quote(field)} AS {_quote(field)}" for field in spec.dimensions]
            select_parts.append(f"{function}({_quote(spec.column)}) AS [metric_value]")
            result_fields = tuple(spec.dimensions) + ("metric_value",)
        # Lineage is selected only for row-grain results. Aggregate rows are
        # still citable by their deterministic query/row identity.
        if spec.aggregation == "none":
            for field in LINEAGE_COLUMNS:
                select_parts.append(f"{_quote(field)} AS {_quote(field)}")
                result_fields += (field,)

        clauses: list[str] = []
        params: list[Any] = []
        for item in spec.filters:
            field = _quote(item.field)
            if item.operator == "contains":
                value = str(item.value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                clauses.append(f"{field} LIKE ? ESCAPE '\\'")
                params.append(f"%{value}%")
            elif item.operator == "in":
                placeholders = ", ".join("?" for _ in item.value)
                clauses.append(f"{field} IN ({placeholders})")
                params.extend(item.value)
            else:
                operator = {"eq": "=", "neq": "<>", "gte": ">=", "lte": "<=", "gt": ">", "lt": "<"}[item.operator]
                clauses.append(f"{field} {operator} ?")
                params.append(item.value)
        if spec.time_window is not None and spec.time_field:
            if spec.time_window.start:
                clauses.append(f"{_quote(spec.time_field)} >= ?")
                params.append(spec.time_window.start)
            if spec.time_window.end:
                clauses.append(f"{_quote(spec.time_field)} <= ?")
                params.append(spec.time_window.end)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        group = " GROUP BY " + ", ".join(_quote(field) for field in spec.dimensions) if spec.dimensions and spec.aggregation != "none" else ""
        if spec.aggregation != "none" and spec.dimensions:
            order_fields = spec.dimensions
        elif spec.aggregation == "none":
            order_fields = [field for field in catalog_table.keys if field in catalog_columns]
        else:
            order_fields = []
        order = " ORDER BY " + ", ".join(_quote(field) for field in order_fields) if order_fields else ""
        sql = f"SELECT TOP (?) {', '.join(select_parts)} FROM {table}{where}{group}{order};"
        return CompiledQuery(
            sql=sql,
            params=(spec.max_rows, *params),
            metric_id=spec.metric_id,
            source_table=spec.table,
            requirement_index=spec.requirement_index,
            max_rows=spec.max_rows,
            result_fields=result_fields,
        )
