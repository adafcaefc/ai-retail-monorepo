"""Versioned, bounded catalog of approved structured Retail facts.

The catalog is planner metadata, not an executable query surface. It is kept
separate from the frozen semantic JSONL corpus and contains only the
allowlisted structured sources that later policy/compiler milestones may use.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field

from .models import StrictModel

CATALOG_PATH = Path(__file__).with_name("catalog.json")
MAX_CATALOG_QUERY_LENGTH = 1000
MAX_CATALOG_RESULTS = 12
_STOPWORDS = {
    "a", "an", "and", "are", "by", "for", "from", "how", "is", "me",
    "next", "of", "on", "the", "to", "using", "what", "with",
}


class CatalogColumn(StrictModel):
    name: str
    data_type: str
    business_meaning: str
    role: str


class CatalogTable(StrictModel):
    name: str
    business_meaning: str
    grain: str
    keys: list[str]
    time_fields: list[str]
    approved_filters: list[str]
    allowed_aggregations: list[str]
    columns: list[CatalogColumn]


class CatalogMetric(StrictModel):
    metric_id: str
    name: str
    aliases: list[str]
    table: str
    column: str
    meaning: str
    grain: str
    unit: str
    allowed_aggregations: list[str]
    dimensions: list[str]
    time_field: str | None = None


class CatalogRelationship(StrictModel):
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    meaning: str


class UnavailableCatalogItem(StrictModel):
    term: str
    aliases: list[str]
    reason: str


class CatalogDocument(StrictModel):
    catalog_version: str
    source_contract: str
    tables: list[CatalogTable]
    metrics: list[CatalogMetric]
    relationships: list[CatalogRelationship]
    known_unavailable: list[UnavailableCatalogItem]


class CatalogSearchResult(StrictModel):
    catalog_version: str
    query: str
    tables: list[CatalogTable] = Field(default_factory=list)
    metrics: list[CatalogMetric] = Field(default_factory=list)
    relationships: list[CatalogRelationship] = Field(default_factory=list)
    unavailable: list[UnavailableCatalogItem] = Field(default_factory=list)

    def model_context(self) -> dict[str, Any]:
        """Return only the bounded planner context, never the full catalog."""
        return self.model_dump(mode="json")

    def prompt_text(self) -> str:
        return json.dumps(self.model_context(), ensure_ascii=False, separators=(",", ":"))


def load_catalog() -> CatalogDocument:
    return CatalogDocument.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))


CATALOG = load_catalog()


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _score(query_tokens: set[str], values: list[str]) -> int:
    searchable = _tokens(" ".join(values))
    return len(query_tokens & searchable)


def search_catalog(query: str, *, limit: int = 8) -> CatalogSearchResult:
    """Return a small relevant slice of the catalog using deterministic search."""
    if not isinstance(query, str) or len(query) > MAX_CATALOG_QUERY_LENGTH:
        raise ValueError(f"Catalog query must be at most {MAX_CATALOG_QUERY_LENGTH} characters")
    normalized = " ".join(query.split())
    if not normalized:
        raise ValueError("Catalog query must not be empty")
    limit = max(1, min(int(limit), MAX_CATALOG_RESULTS))
    query_tokens = _tokens(normalized)

    metric_scored = sorted(
        (
            _score(query_tokens, [metric.metric_id, metric.name, *metric.aliases, metric.meaning, *metric.dimensions]),
            index,
            metric,
        )
        for index, metric in enumerate(CATALOG.metrics)
    )
    metric_scored = [item for item in reversed(metric_scored) if item[0] > 0][:limit]
    metrics = [item[2] for item in metric_scored]

    table_scored = sorted(
        (
            _score(query_tokens, [table.name, table.business_meaning, table.grain, *table.keys, *table.approved_filters, *(column.name for column in table.columns), *(column.business_meaning for column in table.columns)]),
            index,
            table,
        )
        for index, table in enumerate(CATALOG.tables)
    )
    table_scored = [item for item in reversed(table_scored) if item[0] > 0][:limit]
    tables = [item[2] for item in table_scored]

    selected_tables = {table.name for table in tables} | {metric.table for metric in metrics}
    relationships = [
        relationship
        for relationship in CATALOG.relationships
        if relationship.from_table in selected_tables or relationship.to_table in selected_tables
    ][:limit]

    query_text = normalized.casefold()
    unavailable = [
        item for item in CATALOG.known_unavailable
        if any(alias.casefold() in query_text for alias in item.aliases)
    ][:limit]
    return CatalogSearchResult(
        catalog_version=CATALOG.catalog_version,
        query=normalized,
        tables=tables,
        metrics=metrics,
        relationships=relationships,
        unavailable=unavailable,
    )


@lru_cache(maxsize=128)
def cached_search_catalog(query: str, limit: int = 8) -> CatalogSearchResult:
    return search_catalog(query, limit=limit)
