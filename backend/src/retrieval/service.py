from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from src.retail_data_bootstrap.database import open_connection
from src.retail_data_bootstrap.embedding_config import EmbeddingConfig
from src.retail_data_bootstrap.embedding_provider import create_embedding_provider
from src.retail_data_bootstrap.vector_store import semantic_search

from .authorization import (
    AuthorizationPolicy,
    InternalPocAuthorizationPolicy,
    PrincipalContext,
    cli_principal,
)
from .capabilities import CAPABILITIES, StructuredSqlExecutor
from .entities import EntityResolver, required_entity_types
from .models import (
    Diagnostic,
    ResultCounts,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalStatus,
    RetrievalTiming,
    RoutingDecision,
    SelectedRoute,
    SemanticResult,
    SourceReference,
)
from .observability import TraceSink, emit_trace, log_retrieval_event, query_fingerprint
from .routing import DeterministicRouter


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def _semantic_citation_id(result: dict[str, Any]) -> str:
    identity = {
        "doc_key": result["doc_key"],
        "chunk_key": result["matched_chunk_key"],
        "profile_key": result["profile_key"],
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "semantic:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _semantic_source_sheets(
    connection,
    results: list[dict[str, Any]],
) -> dict[str, str]:
    missing = list(
        dict.fromkeys(
            str(result["doc_key"])
            for result in results
            if not result.get("source_sheet")
        )
    )
    if not missing:
        return {
            str(result["doc_key"]): str(result["source_sheet"])
            for result in results
        }
    placeholders = ", ".join("?" for _ in missing)
    cursor = connection.cursor()
    cursor.execute(
        "SELECT doc_key, source_sheet FROM ai.RetailDocument "
        f"WHERE is_active = 1 AND doc_key IN ({placeholders});",
        tuple(missing),
    )
    found = {str(row[0]): str(row[1]) for row in cursor.fetchall()}
    if set(found) != set(missing):
        raise RuntimeError("Semantic provenance is incomplete for ranked documents")
    return found


class _TimedQueryProvider:
    def __init__(self, provider):
        self._provider = provider
        self.query_embedding_ms = 0.0

    def __getattr__(self, name: str):
        return getattr(self._provider, name)

    def embed_query(self, text: str):
        started = time.perf_counter()
        try:
            return self._provider.embed_query(text)
        finally:
            self.query_embedding_ms += _elapsed_ms(started)


class RetrievalService:
    def __init__(
        self,
        *,
        router: DeterministicRouter | None = None,
        entity_resolver: EntityResolver | None = None,
        sql_executor: StructuredSqlExecutor | None = None,
        authorization_policy: AuthorizationPolicy | None = None,
        connection_factory: Callable[[], Any] = open_connection,
        config_factory: Callable[[], EmbeddingConfig] = EmbeddingConfig.from_env,
        provider_factory: Callable[[EmbeddingConfig], Any] = create_embedding_provider,
        semantic_search_fn: Callable[..., dict[str, Any]] = semantic_search,
        trace_sink: TraceSink | None = None,
    ):
        self.router = router or DeterministicRouter()
        self.entity_resolver = entity_resolver or EntityResolver()
        self.sql_executor = sql_executor or StructuredSqlExecutor()
        self.authorization_policy = authorization_policy or InternalPocAuthorizationPolicy()
        self.connection_factory = connection_factory
        self.config_factory = config_factory
        self.provider_factory = provider_factory
        self.semantic_search_fn = semantic_search_fn
        self.trace_sink = trace_sink
        self._embedding_config: EmbeddingConfig | None = None
        self._embedding_provider: Any | None = None
        self._provider_lock = threading.Lock()
        self._vector_lock = threading.Lock()

    def _configured_provider(self) -> tuple[EmbeddingConfig, Any]:
        with self._provider_lock:
            if self._embedding_config is None or self._embedding_provider is None:
                self._embedding_config = self.config_factory()
                self._embedding_provider = self.provider_factory(self._embedding_config)
            return self._embedding_config, self._embedding_provider

    def embedding_config(self) -> EmbeddingConfig:
        """Return the configured profile while preserving the cached provider."""
        config, _ = self._configured_provider()
        return config

    def warm_embedding_provider(self) -> EmbeddingConfig:
        """Warm the already-configured provider used by vector retrieval.

        This deliberately does not run a semantic search or create another
        provider.  It initializes the exact provider held by this service.
        """
        config, provider = self._configured_provider()
        warm_up = getattr(provider, "warm_up", None)
        if callable(warm_up):
            warm_up()
        return config

    def embedding_provider_is_warm(self) -> bool:
        with self._provider_lock:
            provider = self._embedding_provider
            return bool(provider is not None and getattr(provider, "is_warm", False))

    def retrieve(
        self,
        request: RetrievalRequest,
        *,
        principal: PrincipalContext,
    ) -> RetrievalResponse:
        request_id = str(uuid.uuid4())
        total_started = time.perf_counter()
        timing = RetrievalTiming()
        warnings: list[Diagnostic] = []
        errors: list[Diagnostic] = []
        structured_results = []
        semantic_results: list[SemanticResult] = []
        citations: list[SourceReference] = []
        entities = []
        connection = None

        self.authorization_policy.authorize(principal, request)
        emit_trace(self.trace_sink, "router.analysis_started")
        routing_started = time.perf_counter()
        try:
            decision = self.router.decide(request)
        except ValueError as error:
            decision = RoutingDecision(
                selected_route=SelectedRoute.UNSUPPORTED,
                confidence="HIGH",
                reason_codes=["INVALID_FILTER"],
                recognized_intent="invalid_filter",
            )
            errors.append(Diagnostic(code="INVALID_FILTER", message=str(error)))
        timing.routing_ms = _elapsed_ms(routing_started)
        emit_trace(
            self.trace_sink,
            "router.decision",
            elapsed_ms=timing.routing_ms,
            route=decision.selected_route.value,
            confidence=decision.confidence.value,
            reason_codes=list(decision.reason_codes),
            recognized_intent=decision.recognized_intent,
            capabilities=list(decision.selected_sql_capabilities),
            vector_domain=decision.selected_vector_filters.retrieval_domain,
            vector_doc_type=decision.selected_vector_filters.doc_type,
            entity_count=len(decision.recognized_entities),
        )

        if decision.selected_route == SelectedRoute.UNSUPPORTED:
            code = decision.reason_codes[0] if decision.reason_codes else "UNSUPPORTED_INTENT"
            if not errors:
                errors.append(
                    Diagnostic(
                        code=code,
                        message="The request cannot be retrieved safely by an allowlisted Phase 6 route.",
                    )
                )
            timing.total_ms = _elapsed_ms(total_started)
            response = self._response(
                request_id, decision, entities, structured_results, semantic_results,
                citations, warnings, errors, timing,
            )
            self._log(request, response)
            return response

        if decision.selected_route == SelectedRoute.PLANNER_REQUIRED:
            errors.append(
                Diagnostic(
                    code="PLANNER_REQUIRED",
                    message="The safe Retail request exceeds the fixed Phase 6 capabilities and requires adaptive planning.",
                )
            )
            timing.total_ms = _elapsed_ms(total_started)
            response = self._response(
                request_id, decision, entities, structured_results, semantic_results,
                citations, warnings, errors, timing,
            )
            self._log(request, response)
            return response

        try:
            connection = self.connection_factory()
        except Exception:
            code = "SQL_UNAVAILABLE" if decision.selected_route == SelectedRoute.SQL else (
                "VECTOR_UNAVAILABLE" if decision.selected_route == SelectedRoute.VECTOR else "HYBRID_SQL_BRANCH_FAILED"
            )
            errors.append(Diagnostic(code=code, message="Azure SQL is unavailable.", branch="sql"))
            if decision.selected_route == SelectedRoute.HYBRID:
                warnings.append(Diagnostic(code="HYBRID_SQL_BRANCH_FAILED", message="Neither hybrid branch can run without the shared Azure SQL connection.", branch="sql"))
            timing.total_ms = _elapsed_ms(total_started)
            response = self._response(
                request_id, decision, entities, structured_results, semantic_results,
                citations, warnings, errors, timing,
            )
            self._log(request, response)
            return response

        try:
            entity_started = time.perf_counter()
            required = required_entity_types(decision.selected_sql_capabilities)
            resolution = self.entity_resolver.resolve(
                request.query, request.entity_hints, required, connection
            )
            timing.entity_resolution_ms = _elapsed_ms(entity_started)
            entities = resolution.entities
            decision.recognized_entities = list(entities)
            if resolution.ambiguous:
                details = {
                    entity_type.value: candidates
                    for entity_type, candidates in resolution.ambiguous.items()
                }
                errors.append(
                    Diagnostic(
                        code="AMBIGUOUS_ENTITY",
                        message="Multiple exact entity matches were found: " + json.dumps(details, sort_keys=True),
                        branch="sql" if decision.selected_route != SelectedRoute.VECTOR else None,
                    )
                )
            if resolution.missing:
                errors.append(
                    Diagnostic(
                        code="ENTITY_NOT_FOUND",
                        message="Required entities were not found: " + ", ".join(item.value for item in resolution.missing),
                        branch="sql",
                    )
                )

            sql_blocked = bool(resolution.ambiguous or resolution.missing)
            if decision.selected_route in {SelectedRoute.SQL, SelectedRoute.HYBRID} and not sql_blocked:
                capability_metadata = [
                    {
                        "capability": capability,
                        "intent": CAPABILITIES[capability].intent,
                        "source_tables": [f"retail.{table}" for table in CAPABILITIES[capability].tables],
                    }
                    for capability in decision.selected_sql_capabilities
                    if capability in CAPABILITIES
                ]
                emit_trace(
                    self.trace_sink,
                    "sql.started",
                    capabilities=list(decision.selected_sql_capabilities),
                    sources=capability_metadata,
                )
                sql_started = time.perf_counter()
                try:
                    for capability in decision.selected_sql_capabilities:
                        results, sources, limit_applied = self.sql_executor.execute(
                            capability,
                            resolution.by_type,
                            connection,
                            row_limit=request.top_k,
                        )
                        structured_results.extend(results)
                        citations.extend(sources)
                        if limit_applied:
                            warnings.append(
                                Diagnostic(
                                    code="RESULT_LIMIT_APPLIED",
                                    message=f"Capability {capability} returned its bounded limit.",
                                    branch="sql",
                                )
                            )
                except Exception:
                    code = "SQL_UNAVAILABLE" if decision.selected_route == SelectedRoute.SQL else "HYBRID_SQL_BRANCH_FAILED"
                    errors.append(Diagnostic(code=code, message="Structured retrieval failed.", branch="sql"))
                timing.sql_ms = _elapsed_ms(sql_started)
                emit_trace(
                    self.trace_sink,
                    "sql.completed",
                    elapsed_ms=timing.sql_ms,
                    row_count=len(structured_results),
                    capabilities=list(decision.selected_sql_capabilities),
                    error_codes=[item.code for item in errors if item.branch == "sql"],
                )
            elif sql_blocked and decision.selected_route == SelectedRoute.HYBRID:
                warnings.append(
                    Diagnostic(
                        code="HYBRID_SQL_BRANCH_FAILED",
                        message="The SQL branch was not executed because required entity resolution failed.",
                        branch="sql",
                    )
                )

            if decision.selected_route in {SelectedRoute.VECTOR, SelectedRoute.HYBRID}:
                vector_started = time.perf_counter()
                try:
                    config, shared_provider = self._configured_provider()
                    provider_was_warm = bool(getattr(shared_provider, "is_warm", False))
                    provider = _TimedQueryProvider(shared_provider)
                    filters = decision.selected_vector_filters
                    emit_trace(
                        self.trace_sink,
                        "vector.started",
                        provider_key=config.provider_key,
                        model_name=config.model_name,
                        cached=provider_was_warm,
                        retrieval_domain=filters.retrieval_domain,
                        doc_type=filters.doc_type,
                        top_k=request.top_k,
                    )
                    # SentenceTransformer is process-cached and guarded because the
                    # FastAPI sync endpoint may execute concurrently in worker threads.
                    with self._vector_lock:
                        search = self.semantic_search_fn(
                            request.query,
                            provider,
                            config,
                            top_k=request.top_k,
                            retrieval_domain=filters.retrieval_domain,
                            doc_type=filters.doc_type,
                            allow_building=False,
                            connection=connection,
                        )
                    timing.query_embedding_ms = provider.query_embedding_ms
                    search_timing = search.get("timing", {})
                    timing.vector_distance_ms = round(
                        float(search_timing.get("vector_distance_ms", 0.0)), 3
                    )
                    source_sheets = _semantic_source_sheets(
                        connection, search["results"]
                    )
                    for raw in search["results"]:
                        enriched = {**raw, "profile_key": search["profile_key"]}
                        citation_id = _semantic_citation_id(enriched)
                        semantic = SemanticResult(
                            rank=int(raw["rank"]),
                            cosine_distance=float(raw["cosine_distance"]),
                            cosine_similarity=float(raw["cosine_similarity"]),
                            doc_key=str(raw["doc_key"]),
                            doc_type=str(raw["doc_type"]),
                            retrieval_domain=str(raw["retrieval_domain"]),
                            source_sheet=source_sheets[str(raw["doc_key"])],
                            source_key=str(raw["source_key"]),
                            matched_chunk_index=int(raw["matched_chunk_index"]),
                            matched_chunk_key=str(raw["matched_chunk_key"]),
                            excerpt=str(raw["excerpt"]),
                            citation_id=citation_id,
                        )
                        semantic_results.append(semantic)
                        citations.append(
                            SourceReference(
                                citation_id=citation_id,
                                source_kind="semantic",
                                doc_key=semantic.doc_key,
                                chunk_key=semantic.matched_chunk_key,
                                matched_chunk_index=semantic.matched_chunk_index,
                                retrieval_domain=semantic.retrieval_domain,
                                doc_type=semantic.doc_type,
                                source_sheet=semantic.source_sheet,
                                source_key=semantic.source_key,
                                cosine_distance=semantic.cosine_distance,
                                cosine_similarity=semantic.cosine_similarity,
                                excerpt=semantic.excerpt,
                            )
                        )
                except RuntimeError as error:
                    message = str(error).lower()
                    code = (
                        "ACTIVE_EMBEDDING_PROFILE_UNAVAILABLE"
                        if "no active" in message or "no searchable" in message
                        else "EMBEDDING_PROVIDER_MISMATCH"
                    )
                    if decision.selected_route == SelectedRoute.HYBRID:
                        warnings.append(Diagnostic(code="HYBRID_VECTOR_BRANCH_FAILED", message="Semantic retrieval failed.", branch="vector"))
                    errors.append(Diagnostic(code=code, message="Semantic retrieval is unavailable.", branch="vector"))
                except Exception:
                    code = "VECTOR_UNAVAILABLE" if decision.selected_route == SelectedRoute.VECTOR else "HYBRID_VECTOR_BRANCH_FAILED"
                    errors.append(Diagnostic(code=code, message="Semantic retrieval failed.", branch="vector"))
                timing.vector_total_ms = _elapsed_ms(vector_started)
                timing.vector_search_ms = round(max(0.0, timing.vector_total_ms - timing.query_embedding_ms), 3)
                emit_trace(
                    self.trace_sink,
                    "vector.completed",
                    elapsed_ms=timing.vector_total_ms,
                    query_embedding_ms=timing.query_embedding_ms,
                    vector_distance_ms=timing.vector_distance_ms,
                    vector_search_ms=timing.vector_search_ms,
                    result_count=len(semantic_results),
                    error_codes=[item.code for item in errors if item.branch == "vector"],
                )

            if decision.selected_route in {SelectedRoute.SQL, SelectedRoute.HYBRID} and re.search(
                r"\b(current|today|now|latest|currently)\b", request.query, re.I
            ):
                warnings.append(
                    Diagnostic(
                        code="BUSINESS_AS_OF_UNAVAILABLE",
                        message="Source load lineage is available, but a business-effective as-of timestamp is not.",
                        branch="sql",
                    )
                )
        finally:
            connection.close()

        timing.total_ms = _elapsed_ms(total_started)
        aggregation_started = time.perf_counter()
        response = self._response(
            request_id, decision, entities, structured_results, semantic_results,
            citations, warnings, errors, timing,
        )
        response.timing.evidence_aggregation_ms = _elapsed_ms(aggregation_started)
        emit_trace(
            self.trace_sink,
            "evidence.aggregated",
            elapsed_ms=response.timing.evidence_aggregation_ms,
            structured_count=response.result_counts.structured,
            semantic_count=response.result_counts.semantic,
            citation_count=response.result_counts.citations,
        )
        serialization_started = time.perf_counter()
        response.model_dump(mode="json")
        response.timing.serialization_ms = _elapsed_ms(serialization_started)
        response.timing.total_ms = _elapsed_ms(total_started)
        self._log(request, response)
        return response

    @staticmethod
    def _response(
        request_id,
        decision,
        entities,
        structured_results,
        semantic_results,
        citations,
        warnings,
        errors,
        timing,
    ) -> RetrievalResponse:
        if not structured_results and not semantic_results and not errors:
            errors = [
                Diagnostic(
                    code="NO_EVIDENCE_RETRIEVED",
                    message="No verified evidence was retrieved for the request.",
                    branch="retrieval",
                )
            ]
        if errors and (structured_results or semantic_results):
            status = RetrievalStatus.PARTIAL
        elif errors:
            status = RetrievalStatus.FAILED
        else:
            status = RetrievalStatus.COMPLETE
        return RetrievalResponse(
            request_id=request_id,
            status=status,
            route=decision.selected_route,
            routing=decision,
            entities=entities,
            structured_results=structured_results,
            semantic_results=semantic_results,
            citations=citations,
            warnings=warnings,
            errors=errors,
            timing=timing,
            result_counts=ResultCounts(
                structured=len(structured_results),
                semantic=len(semantic_results),
                citations=len(citations),
            ),
        )

    @staticmethod
    def _log(request: RetrievalRequest, response: RetrievalResponse) -> None:
        log_retrieval_event(
            request_id=response.request_id,
            query_fingerprint=query_fingerprint(request.query),
            route=response.route.value,
            reason_codes=response.routing.reason_codes,
            entity_outcome=[entity.entity_type.value for entity in response.entities],
            sql_capabilities=response.routing.selected_sql_capabilities,
            vector_filters=response.routing.selected_vector_filters.model_dump(),
            sql_row_count=response.result_counts.structured,
            semantic_result_count=response.result_counts.semantic,
            routing_ms=response.timing.routing_ms,
            entity_resolution_ms=response.timing.entity_resolution_ms,
            sql_ms=response.timing.sql_ms,
            query_embedding_ms=response.timing.query_embedding_ms,
            vector_distance_ms=response.timing.vector_distance_ms,
            vector_search_ms=response.timing.vector_search_ms,
            vector_total_ms=response.timing.vector_total_ms,
            evidence_aggregation_ms=response.timing.evidence_aggregation_ms,
            total_ms=response.timing.total_ms,
            fallback_used=False,
            error_category=response.errors[0].code if response.errors else None,
        )


_DEFAULT_SERVICE = RetrievalService()


def retrieve_context(
    request: RetrievalRequest,
    *,
    principal: PrincipalContext | None = None,
    service: RetrievalService | None = None,
) -> RetrievalResponse:
    return (service or _DEFAULT_SERVICE).retrieve(
        request,
        principal=principal or cli_principal(),
    )
