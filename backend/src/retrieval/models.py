from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.retail_data_bootstrap.semantic_contract import (
    DOC_TYPE_RETRIEVAL_DOMAIN,
    RETRIEVAL_DOMAINS,
)

MAX_QUERY_LENGTH = 1000
DEFAULT_TOP_K = 5
MAX_TOP_K = 20
MAX_ENTITY_HINTS = 8


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RouteMode(StrEnum):
    AUTO = "auto"
    SQL = "sql"
    VECTOR = "vector"
    HYBRID = "hybrid"


class SelectedRoute(StrEnum):
    SQL = "SQL"
    VECTOR = "VECTOR"
    HYBRID = "HYBRID"
    UNSUPPORTED = "UNSUPPORTED"


class RetrievalStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class RoutingConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EntityType(StrEnum):
    SKU = "sku"
    STORE = "store"
    VENDOR = "vendor"
    LEGAL_ENTITY = "legal_entity"
    CATEGORY = "category"
    BRAND = "brand"
    PROMOTION = "promotion"


class EntityHint(StrictModel):
    entity_type: EntityType
    value: str = Field(min_length=1, max_length=200)


class RetrievalRequest(StrictModel):
    query: str = Field(default="", max_length=MAX_QUERY_LENGTH)
    route_mode: RouteMode = RouteMode.AUTO
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K)
    retrieval_domain: str | None = None
    doc_type: str | None = None
    entity_hints: list[EntityHint] = Field(default_factory=list, max_length=MAX_ENTITY_HINTS)
    agent_context: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_semantic_filters(self) -> "RetrievalRequest":
        if self.retrieval_domain and self.retrieval_domain not in RETRIEVAL_DOMAINS:
            raise ValueError(f"Unknown retrieval domain: {self.retrieval_domain}")
        if self.doc_type and self.doc_type not in DOC_TYPE_RETRIEVAL_DOMAIN:
            raise ValueError(f"Unknown document type: {self.doc_type}")
        if self.doc_type and self.retrieval_domain:
            expected = DOC_TYPE_RETRIEVAL_DOMAIN[self.doc_type]
            if expected != self.retrieval_domain:
                raise ValueError(
                    f"Document type {self.doc_type!r} belongs to {expected!r}, "
                    f"not {self.retrieval_domain!r}"
                )
        return self


class RecognizedEntity(StrictModel):
    entity_type: EntityType
    identifier: str
    display_name: str | None = None
    resolution_method: str


class VectorFilters(StrictModel):
    retrieval_domain: str | None = None
    doc_type: str | None = None


class RoutingDecision(StrictModel):
    selected_route: SelectedRoute
    confidence: RoutingConfidence
    reason_codes: list[str] = Field(default_factory=list)
    recognized_intent: str
    recognized_entities: list[RecognizedEntity] = Field(default_factory=list)
    selected_sql_capabilities: list[str] = Field(default_factory=list)
    selected_vector_filters: VectorFilters = Field(default_factory=VectorFilters)
    fallback_allowed: bool = False
    warnings: list[str] = Field(default_factory=list)


class Diagnostic(StrictModel):
    code: str
    message: str
    branch: str | None = None


class SourceReference(StrictModel):
    citation_id: str
    source_kind: str
    schema_name: str | None = None
    tables: list[str] = Field(default_factory=list)
    business_keys: dict[str, Any] = Field(default_factory=dict)
    capability_key: str | None = None
    selected_fields: list[str] = Field(default_factory=list)
    source_load_id: int | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_load_at: str | None = None
    doc_key: str | None = None
    chunk_key: str | None = None
    matched_chunk_index: int | None = None
    retrieval_domain: str | None = None
    doc_type: str | None = None
    source_key: str | None = None
    cosine_distance: float | None = None
    cosine_similarity: float | None = None
    excerpt: str | None = None


class StructuredResult(StrictModel):
    capability_key: str
    row_index: int
    data: dict[str, Any]
    citation_ids: list[str]


class SemanticResult(StrictModel):
    rank: int
    cosine_distance: float
    cosine_similarity: float
    doc_key: str
    doc_type: str
    retrieval_domain: str
    source_sheet: str
    source_key: str
    matched_chunk_index: int
    matched_chunk_key: str
    excerpt: str
    citation_id: str


class RetrievalTiming(StrictModel):
    routing_ms: float = 0.0
    entity_resolution_ms: float = 0.0
    sql_ms: float = 0.0
    query_embedding_ms: float = 0.0
    vector_search_ms: float = 0.0
    vector_total_ms: float = 0.0
    serialization_ms: float = 0.0
    total_ms: float = 0.0


class ResultCounts(StrictModel):
    structured: int = 0
    semantic: int = 0
    citations: int = 0


class RetrievalResponse(StrictModel):
    request_id: str
    status: RetrievalStatus
    route: SelectedRoute
    routing: RoutingDecision
    entities: list[RecognizedEntity] = Field(default_factory=list)
    structured_results: list[StructuredResult] = Field(default_factory=list)
    semantic_results: list[SemanticResult] = Field(default_factory=list)
    citations: list[SourceReference] = Field(default_factory=list)
    warnings: list[Diagnostic] = Field(default_factory=list)
    errors: list[Diagnostic] = Field(default_factory=list)
    timing: RetrievalTiming = Field(default_factory=RetrievalTiming)
    result_counts: ResultCounts = Field(default_factory=ResultCounts)

