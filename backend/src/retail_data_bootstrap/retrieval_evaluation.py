from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .database import open_connection
from .embedding_config import EmbeddingConfig
from .embedding_provider import EmbeddingProvider
from .vector_store import semantic_search


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    query: str
    retrieval_domain: str
    doc_type: str | None
    expected_doc_key: str | None = None
    expected_doc_key_prefix: str | None = None
    expected_text_terms: tuple[str, ...] = ()


RETRIEVAL_CASES = (
    RetrievalCase(
        case_id="perishable_fruit",
        query="Which product is a perishable fruit item?",
        retrieval_domain="business_entity",
        doc_type="sku",
        expected_doc_key_prefix="sku:grc-",
        expected_text_terms=("fruit", "perishable"),
    ),
    RetrievalCase(
        case_id="days_of_supply",
        query="What does days of supply mean?",
        retrieval_domain="business_rule",
        doc_type="terminology",
        expected_doc_key="terminology:dos",
    ),
    RetrievalCase(
        case_id="average_daily_sales",
        query="How is average daily sales per store calculated?",
        retrieval_domain="business_rule",
        doc_type="formula",
        expected_doc_key="formula:ads-per-store",
    ),
    RetrievalCase(
        case_id="d365_demand_forecasting",
        query="Where does the demand forecasting field come from in D365?",
        retrieval_domain="integration",
        doc_type=None,
        expected_doc_key_prefix="d365-field-mapping:a1-demand-forecasting",
    ),
    RetrievalCase(
        case_id="purchasing_approval",
        query="Who approves a high-value purchasing action?",
        retrieval_domain="governance",
        doc_type="approval_rule",
        expected_doc_key="approval-rule:purchase-order",
    ),
    RetrievalCase(
        case_id="replenishment_agent",
        query="What agent handles replenishment decisions?",
        retrieval_domain="agent_configuration",
        doc_type="agent_spec",
        expected_doc_key="agent-spec:a3-replenishment",
    ),
)


def _is_expected(result: dict[str, Any], case: RetrievalCase) -> bool:
    key = str(result["doc_key"])
    if case.expected_doc_key and key != case.expected_doc_key:
        return False
    if case.expected_doc_key_prefix and not key.startswith(case.expected_doc_key_prefix):
        return False
    text = str(result.get("matched_chunk_text", "")).lower()
    return all(term.lower() in text for term in case.expected_text_terms)


def _summarize_run(result: dict[str, Any], case: RetrievalCase) -> dict[str, Any]:
    matches = [
        item for item in result["results"] if _is_expected(item, case)
    ]
    return {
        "passed": bool(matches),
        "matching_doc_keys": [item["doc_key"] for item in matches],
        "ranked_doc_keys": [item["doc_key"] for item in result["results"]],
        "top_distance": (
            result["results"][0]["cosine_distance"] if result["results"] else None
        ),
    }


def evaluate_retrieval_quality(
    provider: EmbeddingProvider,
    config: EmbeddingConfig,
    *,
    top_k: int = 10,
    connection=None,
) -> dict[str, Any]:
    owned = connection is None
    connection = connection or open_connection()
    try:
        results = []
        for case in RETRIEVAL_CASES:
            unfiltered = semantic_search(
                case.query,
                provider,
                config,
                top_k=top_k,
                connection=connection,
            )
            filtered = semantic_search(
                case.query,
                provider,
                config,
                top_k=top_k,
                retrieval_domain=case.retrieval_domain,
                doc_type=case.doc_type,
                connection=connection,
            )
            results.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "expected_domain": case.retrieval_domain,
                    "expected_doc_type": case.doc_type,
                    "unfiltered": _summarize_run(unfiltered, case),
                    "filtered": _summarize_run(filtered, case),
                }
            )
        return {
            "valid": all(
                item[mode]["passed"]
                for item in results
                for mode in ("unfiltered", "filtered")
            ),
            "top_k": top_k,
            "case_count": len(results),
            "unfiltered_passed": sum(item["unfiltered"]["passed"] for item in results),
            "filtered_passed": sum(item["filtered"]["passed"] for item in results),
            "results": results,
        }
    finally:
        if owned:
            connection.close()
