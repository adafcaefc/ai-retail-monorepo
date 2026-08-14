from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("src.retrieval")


@dataclass(frozen=True)
class RetrievalTraceEvent:
    """Optional structured runtime event for diagnostics and demonstrations.

    The production retrieval path does not install a sink, so these events are
    silent by default.  Event payloads are bounded metadata rather than query
    text, SQL parameter values, credentials, or retrieved document contents.
    """

    name: str
    data: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float | None = None


TraceSink = Callable[[RetrievalTraceEvent], None]


def emit_trace(
    sink: TraceSink | None,
    name: str,
    *,
    elapsed_ms: float | None = None,
    **data: Any,
) -> None:
    """Deliver an optional trace event without changing retrieval behavior."""
    if sink is None:
        return
    try:
        sink(RetrievalTraceEvent(name=name, data=data, elapsed_ms=elapsed_ms))
    except Exception:  # pragma: no cover - observability must never break retrieval
        logger.debug("retrieval trace sink failed", exc_info=True)


def query_fingerprint(query: str) -> str:
    normalized = " ".join(query.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def log_retrieval_event(**metadata: Any) -> None:
    """Log bounded metadata only; never accept query text or vector values."""
    allowed = {
        "request_id",
        "query_fingerprint",
        "route",
        "reason_codes",
        "entity_outcome",
        "sql_capabilities",
        "vector_filters",
        "sql_row_count",
        "semantic_result_count",
        "routing_ms",
        "entity_resolution_ms",
        "sql_ms",
        "query_embedding_ms",
        "vector_distance_ms",
        "vector_search_ms",
        "vector_total_ms",
        "catalog_ms",
        "planning_ms",
        "gateway_ms",
        "planner_model_ms",
        "planner_validation_ms",
        "fallback_decision_ms",
        "fallback_ms",
        "policy_ms",
        "compilation_ms",
        "evidence_aggregation_ms",
        "total_ms",
        "fallback_used",
        "error_category",
    }
    safe = {key: value for key, value in metadata.items() if key in allowed}
    logger.info("retrieval_event %s", json.dumps(safe, sort_keys=True, default=str))
