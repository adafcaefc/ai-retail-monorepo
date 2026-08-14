"""Deterministic policy validation for adaptive structured retrieval.

The planner describes evidence requirements.  This module turns those
requirements into a much smaller, validated ``QuerySpec``.  The compiler is
the only consumer of that type; neither the user request nor model output is
ever treated as SQL.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from pydantic import Field, model_validator

from .authorization import PrincipalContext
from .catalog import CATALOG, CatalogMetric, CatalogTable
from .models import StrictModel
from .planner import QueryFilter, QueryPlan, SemanticRequirement, StructuredRequirement

MAX_ADAPTIVE_ROWS = 50
MAX_ADAPTIVE_REQUIREMENTS = 8
MAX_FILTERS_PER_QUERY = 12
MAX_IN_VALUES = 50
MAX_JOIN_COUNT = 2
MAX_DATE_RANGE_DAYS = 366
MAX_STRING_PARAMETER_LENGTH = 200
MAX_QUERY_COMPLEXITY = 12
QUERY_TIMEOUT_SECONDS = 10
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SQL_CONTROL_RE = re.compile(
    r"(?:;|--|/\*|\*/|\b(?:select|insert|update|delete|drop|alter|truncate|merge|create|exec(?:ute)?|union|declare|waitfor)\b)",
    re.IGNORECASE,
)


class QueryPolicyError(ValueError):
    """A plan cannot be safely represented by the approved query surface."""


class QuerySpec(StrictModel):
    """A policy-approved, non-SQL representation of one structured query."""

    requirement_index: int = Field(ge=0, lt=12)
    metric_id: str = Field(min_length=1, max_length=128)
    table: str = Field(min_length=1, max_length=128)
    column: str = Field(min_length=1, max_length=128)
    dimensions: list[str] = Field(default_factory=list, max_length=8)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=MAX_FILTERS_PER_QUERY)
    aggregation: str
    time_field: str | None = None
    time_window: Any | None = None
    max_rows: int = Field(default=MAX_ADAPTIVE_ROWS, ge=1, le=MAX_ADAPTIVE_ROWS)
    timeout_seconds: int = Field(default=QUERY_TIMEOUT_SECONDS, ge=1, le=QUERY_TIMEOUT_SECONDS)
    authorization_scope: tuple[str, ...] = ()
    required: bool = True

    @model_validator(mode="after")
    def validate_identifier_shapes(self) -> "QuerySpec":
        table_parts = self.table.split(".")
        identifiers = (*table_parts, self.column, *self.dimensions, *(item.field for item in self.filters))
        for value in identifiers:
            if not _IDENTIFIER_RE.fullmatch(value):
                raise ValueError(f"Unsafe identifier in QuerySpec: {value!r}")
        return self


class ValidatedQueryPlan(StrictModel):
    """The complete policy result passed to deterministic compilation."""

    plan_version: str
    catalog_version: str
    queries: list[QuerySpec] = Field(default_factory=list, max_length=MAX_ADAPTIVE_REQUIREMENTS)
    semantic_requirements: list[SemanticRequirement] = Field(default_factory=list, max_length=8)
    unavailable_requirements: list[str] = Field(default_factory=list, max_length=12)
    estimated_complexity: int = Field(ge=0, le=MAX_QUERY_COMPLEXITY)


def _check_string(value: str, *, field: str) -> None:
    if len(value) > MAX_STRING_PARAMETER_LENGTH:
        raise QueryPolicyError(f"{field} exceeds the parameter length limit")
    if _SQL_CONTROL_RE.search(value):
        raise QueryPolicyError(f"SQL control syntax is not allowed in {field}")


def _validate_value(value: Any, *, field: str) -> None:
    if isinstance(value, str):
        _check_string(value, field=field)
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise QueryPolicyError(f"Non-finite numeric value in {field}")
    else:
        raise QueryPolicyError(f"Unsupported filter value in {field}")


def _validate_filter(item: QueryFilter, table: CatalogTable, metric: CatalogMetric) -> None:
    if item.field not in table.approved_filters:
        raise QueryPolicyError(f"Filter field {item.field!r} is not approved for {table.name}")
    if item.field not in {column.name for column in table.columns}:
        raise QueryPolicyError(f"Filter field {item.field!r} is not a catalog column")
    if item.operator == "contains" and not isinstance(item.value, str):
        raise QueryPolicyError("contains filters require a string value")
    if item.operator == "in":
        if not isinstance(item.value, list) or not item.value:
            raise QueryPolicyError("in filters require a non-empty list")
        if len(item.value) > MAX_IN_VALUES:
            raise QueryPolicyError(f"in filters are limited to {MAX_IN_VALUES} values")
        values = item.value
    else:
        if isinstance(item.value, list):
            raise QueryPolicyError(f"Only in filters accept list values: {item.field}")
        values = [item.value]
    for value in values:
        _validate_value(value, field=f"filter {item.field}")


def _parse_date(value: str, *, field: str) -> date:
    _check_string(value, field=field)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as error:
        raise QueryPolicyError(f"{field} must be an ISO date or datetime") from error


def _validate_time(requirement: StructuredRequirement, metric: CatalogMetric) -> None:
    window = requirement.time_window
    if window is None:
        if metric.time_field:
            raise QueryPolicyError(
                f"Metric {metric.metric_id} requires a bounded time window"
            )
        return
    if window.horizon_days is not None:
        if window.horizon_days > MAX_DATE_RANGE_DAYS:
            raise QueryPolicyError("Time horizon exceeds the bounded date range")
        if metric.metric_id == "demand.forecast_7d":
            if window.horizon_days != 7:
                raise QueryPolicyError("The approved forecast metric supports exactly a seven-day horizon")
        elif not metric.time_field:
            raise QueryPolicyError(f"Metric {metric.metric_id} has no approved horizon field")
    if metric.time_field and not (window.start and window.end):
        raise QueryPolicyError(
            f"Metric {metric.metric_id} requires both bounded time-window boundaries"
        )
    if (window.start or window.end) and not metric.time_field:
        raise QueryPolicyError(f"Metric {metric.metric_id} has no approved time field")
    if window.start and window.end:
        start = _parse_date(window.start, field="time_window.start")
        end = _parse_date(window.end, field="time_window.end")
        if end < start:
            raise QueryPolicyError("time_window.end must not precede start")
        if (end - start).days > MAX_DATE_RANGE_DAYS:
            raise QueryPolicyError("Time window exceeds the bounded date range")
    elif window.start or window.end:
        _parse_date(window.start or window.end or "", field="time_window boundary")


def _catalog_table(name: str) -> CatalogTable | None:
    return next((table for table in CATALOG.tables if table.name == name), None)


class QueryPolicy:
    """Validate QueryPlan values against the immutable approved catalog."""

    def validate(
        self,
        plan: QueryPlan,
        *,
        principal: PrincipalContext | None = None,
        max_rows: int = MAX_ADAPTIVE_ROWS,
    ) -> ValidatedQueryPlan:
        if plan.catalog_version != CATALOG.catalog_version:
            raise QueryPolicyError("QueryPlan catalog version is not active")
        if max_rows < 1 or max_rows > MAX_ADAPTIVE_ROWS:
            raise QueryPolicyError("Requested row limit is outside the policy bound")
        if len(plan.structured_requirements) > MAX_ADAPTIVE_REQUIREMENTS:
            raise QueryPolicyError("Too many structured requirements")
        if len(plan.dependencies) > MAX_JOIN_COUNT:
            raise QueryPolicyError("Plan dependencies/join complexity exceeds the policy bound")
        if plan.dependencies:
            # QueryPlan dependencies are deliberately not a free-form join
            # language.  The current compiler emits one approved source per
            # requirement; until a typed join compiler exists, refusing even
            # an undeclared relationship is safer than silently ignoring it.
            raise QueryPolicyError("Plan dependencies require an approved typed join compiler")

        scope = tuple(principal.legal_entity_ids) if principal else ()
        for value in scope:
            _check_string(value, field="authorization scope")
        if scope and plan.semantic_requirements:
            # The frozen vector contract can filter by retrieval domain and
            # document type, but not by legal entity.  Refuse the complete
            # plan rather than allowing a semantic branch to bypass the
            # structured row-scope hook.
            raise QueryPolicyError(
                "Authorization scope cannot be enforced for adaptive semantic requirements"
            )
        queries: list[QuerySpec] = []
        unavailable = list(plan.unavailable_requirements)
        complexity = len(plan.dependencies)
        for index, requirement in enumerate(plan.structured_requirements):
            if requirement.availability == "UNAVAILABLE":
                if requirement.required:
                    unavailable.append(requirement.unavailable_reason or requirement.metric_id)
                continue
            metric = next((item for item in CATALOG.metrics if item.metric_id == requirement.metric_id), None)
            if metric is None:
                raise QueryPolicyError(f"Metric {requirement.metric_id!r} is not approved")
            table = _catalog_table(metric.table)
            if table is None or not metric.table.startswith("retail."):
                raise QueryPolicyError("Metric source is not an approved retail table")
            columns = {column.name for column in table.columns}
            if metric.column not in columns:
                raise QueryPolicyError(f"Metric column {metric.column!r} is not in the catalog")
            if requirement.aggregation != "none" and requirement.aggregation not in metric.allowed_aggregations:
                raise QueryPolicyError(
                    f"Aggregation {requirement.aggregation!r} is not approved for {metric.metric_id}"
                )
            if len(set(requirement.dimensions)) != len(requirement.dimensions):
                raise QueryPolicyError("Duplicate dimensions are not allowed")
            for dimension in requirement.dimensions:
                if dimension not in metric.dimensions or dimension not in columns:
                    raise QueryPolicyError(f"Dimension {dimension!r} is not approved for {metric.metric_id}")
            for item in requirement.filters:
                _validate_filter(item, table, metric)
            _validate_time(requirement, metric)

            filters = list(requirement.filters)
            if scope:
                if "legal_entity_id" not in table.approved_filters or "legal_entity_id" not in columns:
                    raise QueryPolicyError(
                        f"Authorization scope cannot be enforced for {metric.metric_id}"
                    )
                existing = [item for item in filters if item.field == "legal_entity_id"]
                for item in existing:
                    values = item.value if isinstance(item.value, list) else [item.value]
                    if item.operator not in {"eq", "in"} or any(str(value) not in scope for value in values):
                        raise QueryPolicyError("Query filter escapes the authorization scope")
                if not existing:
                    filters.append(QueryFilter(field="legal_entity_id", operator="in", value=list(scope)))
            queries.append(
                QuerySpec(
                    requirement_index=index,
                    metric_id=metric.metric_id,
                    table=metric.table,
                    column=metric.column,
                    dimensions=list(requirement.dimensions),
                    filters=filters,
                    aggregation=requirement.aggregation,
                    time_field=metric.time_field,
                    time_window=requirement.time_window,
                    max_rows=min(max_rows, MAX_ADAPTIVE_ROWS),
                    timeout_seconds=QUERY_TIMEOUT_SECONDS,
                    authorization_scope=scope,
                    required=requirement.required,
                )
            )
            complexity += 1 + len(requirement.filters) + len(requirement.dimensions)
        if complexity > MAX_QUERY_COMPLEXITY:
            raise QueryPolicyError("Query complexity exceeds the policy bound")
        return ValidatedQueryPlan(
            plan_version=plan.plan_version,
            catalog_version=plan.catalog_version,
            queries=queries,
            semantic_requirements=list(plan.semantic_requirements),
            unavailable_requirements=list(dict.fromkeys(unavailable)),
            estimated_complexity=complexity,
        )
