"""Deterministic Retail 360 retrieval evidence service."""

from .models import RetrievalRequest, RetrievalResponse
from .service import RetrievalService, retrieve_context
from .catalog import CatalogSearchResult, search_catalog
from .planner import (
    AdaptiveQueryPlanner,
    PlannerInput,
    PlannerValidationError,
    QueryPlan,
)
from .policy import QueryPolicy, QueryPolicyError, QuerySpec, ValidatedQueryPlan
from .compiler import CompiledQuery, DeterministicSqlCompiler
from .orchestrator import AdaptiveRetrievalOrchestrator
from .gateway import ChatRetrievalGateway
from .grounding import (
    CitationValidation,
    GroundingPacket,
    build_grounding_packet,
    grounding_notice,
    validate_citations,
)

__all__ = [
    "RetrievalRequest",
    "RetrievalResponse",
    "RetrievalService",
    "retrieve_context",
    "CatalogSearchResult",
    "search_catalog",
    "AdaptiveQueryPlanner",
    "PlannerInput",
    "PlannerValidationError",
    "QueryPlan",
    "QueryPolicy",
    "QueryPolicyError",
    "QuerySpec",
    "ValidatedQueryPlan",
    "CompiledQuery",
    "DeterministicSqlCompiler",
    "AdaptiveRetrievalOrchestrator",
    "ChatRetrievalGateway",
    "CitationValidation",
    "GroundingPacket",
    "build_grounding_packet",
    "grounding_notice",
    "validate_citations",
]
