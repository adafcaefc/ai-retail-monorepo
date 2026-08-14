from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("src.retrieval")


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
        "vector_search_ms",
        "vector_total_ms",
        "planning_ms",
        "policy_ms",
        "compilation_ms",
        "evidence_aggregation_ms",
        "total_ms",
        "fallback_used",
        "error_category",
    }
    safe = {key: value for key, value in metadata.items() if key in allowed}
    logger.info("retrieval_event %s", json.dumps(safe, sort_keys=True, default=str))
