"""Bounded adaptive planning, compilation, and evidence orchestration."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.retail_data_bootstrap.database import open_connection

from .authorization import (
    AuthorizationPolicy,
    InternalPocAuthorizationPolicy,
    PrincipalContext,
    cli_principal,
)
from .compiler import CompiledQuery, DeterministicSqlCompiler
from .models import (
    Diagnostic,
    ResultCounts,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalStatus,
    RetrievalTiming,
    RoutingDecision,
    RoutingConfidence,
    SelectedRoute,
    SemanticResult,
    SourceReference,
    StructuredResult,
    VectorFilters,
)
from .planner import AdaptiveQueryPlanner, SemanticRequirement, QueryPlan
from .observability import log_retrieval_event, query_fingerprint
from .policy import QUERY_TIMEOUT_SECONDS, QueryPolicy, QueryPolicyError
from .service import RetrievalService


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _adaptive_citation_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "adaptive-sql:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class AdaptiveRetrievalOrchestrator:
    """Run one plan through policy, deterministic compilation, and bounded branches.

    ``structured_executor`` and ``semantic_executor`` are injectable seams for
    tests and for future chatbot integration.  The planner receives neither
    callable and no planner result is executed until policy validation has
    completed.
    """

    def __init__(
        self,
        *,
        planner: AdaptiveQueryPlanner | Any | None = None,
        policy: QueryPolicy | None = None,
        compiler: DeterministicSqlCompiler | None = None,
        connection_factory: Callable[[], Any] = open_connection,
        structured_executor: Callable[[CompiledQuery], Any] | None = None,
        semantic_executor: Callable[[SemanticRequirement, RetrievalRequest, PrincipalContext], Any] | None = None,
        semantic_service: RetrievalService | None = None,
        authorization_policy: AuthorizationPolicy | None = None,
        max_workers: int = 4,
    ) -> None:
        self.planner = planner or AdaptiveQueryPlanner()
        self.policy = policy or QueryPolicy()
        self.compiler = compiler or DeterministicSqlCompiler()
        self.connection_factory = connection_factory
        self.structured_executor = structured_executor or self._execute_sql
        # Keep one vector service per orchestrator.  It owns the process-local
        # embedding-provider cache and lock; constructing a fresh service for
        # every semantic requirement would reload BGE and permit unsafe
        # concurrent model use.
        self.semantic_service = semantic_service or RetrievalService()
        self.semantic_executor = semantic_executor or self._execute_vector
        self.authorization_policy = authorization_policy or InternalPocAuthorizationPolicy()
        self.max_workers = max(1, min(int(max_workers), 8))

    def retrieve(
        self,
        request: RetrievalRequest,
        *,
        principal: PrincipalContext | None = None,
        conversation_context: Sequence[str] | None = None,
        entity_context: Sequence[Any] | None = None,
        agent_context: str | None = None,
    ) -> RetrievalResponse:
        principal = principal or cli_principal()
        request_id = str(uuid.uuid4())
        try:
            self.authorization_policy.authorize(principal, request)
        except PermissionError:
            response = self._failure(
                request_id,
                request,
                "AUTHORIZATION_DENIED",
                "Adaptive retrieval is not authorized for this principal.",
                RetrievalTiming(),
            )
            self._log(request, response)
            return response
        planning_started = time.perf_counter()
        try:
            plan = self.planner.plan(
                request.query,
                conversation_context=conversation_context,
                entity_context=entity_context,
                agent_context=agent_context or request.agent_context,
            )
        except Exception:
            timing = RetrievalTiming(planning_ms=self._elapsed(planning_started))
            response = self._failure(request_id, request, "PLANNER_FAILED", "Adaptive planning failed.", timing)
            self._log(request, response)
            return response
        timing = RetrievalTiming(planning_ms=self._elapsed(planning_started))
        response = self.execute_plan(request, plan, principal=principal, request_id=request_id, timing=timing)
        response.timing.total_ms = round(response.timing.total_ms + response.timing.planning_ms, 3)
        self._log(request, response)
        return response

    def execute_plan(
        self,
        request: RetrievalRequest,
        plan: QueryPlan,
        *,
        principal: PrincipalContext | None = None,
        request_id: str | None = None,
        timing: RetrievalTiming | None = None,
    ) -> RetrievalResponse:
        principal = principal or cli_principal()
        request_id = request_id or str(uuid.uuid4())
        timing = timing or RetrievalTiming()
        try:
            self.authorization_policy.authorize(principal, request)
        except PermissionError:
            return self._failure(
                request_id,
                request,
                "AUTHORIZATION_DENIED",
                "Adaptive retrieval is not authorized for this principal.",
                timing,
            )
        execute_started = time.perf_counter()
        policy_started = time.perf_counter()
        try:
            validated = self.policy.validate(plan, principal=principal, max_rows=request.top_k)
        except (QueryPolicyError, ValueError) as error:
            timing.policy_ms = self._elapsed(policy_started)
            timing.total_ms = self._elapsed(policy_started)
            return self._failure(request_id, request, "QUERY_POLICY_REJECTED", str(error), timing)
        timing.policy_ms = self._elapsed(policy_started)

        compilation_started = time.perf_counter()
        try:
            compiled = [self.compiler.compile(spec) for spec in validated.queries]
        except (ValueError, KeyError) as error:
            timing.compilation_ms = self._elapsed(compilation_started)
            timing.total_ms = self._elapsed(compilation_started)
            return self._failure(request_id, request, "SQL_COMPILATION_REJECTED", str(error), timing)
        timing.compilation_ms = self._elapsed(compilation_started)

        decision = RoutingDecision(
            selected_route=SelectedRoute.PLANNER_REQUIRED,
            confidence=RoutingConfidence.HIGH,
            reason_codes=["ADAPTIVE_PLAN_EXECUTED"],
            recognized_intent="adaptive_retrieval",
            fallback_allowed=False,
            selected_vector_filters=VectorFilters(),
        )
        structured: list[StructuredResult] = []
        semantic: list[SemanticResult] = []
        citations: list[SourceReference] = []
        warnings: list[Diagnostic] = []
        errors: list[Diagnostic] = []

        for unavailable in validated.unavailable_requirements:
            errors.append(Diagnostic(code="REQUIRED_EVIDENCE_UNAVAILABLE", message=unavailable, branch="adaptive"))

        branches: list[tuple[str, int, Callable[[], Any], bool]] = []
        for spec, query in zip(validated.queries, compiled):
            branches.append(("sql", spec.requirement_index, lambda query=query: self.structured_executor(query), spec.required))
        for index, requirement in enumerate(validated.semantic_requirements):
            branches.append(("vector", index, lambda requirement=requirement: self.semantic_executor(requirement, request, principal), requirement.required))

        aggregation_started = time.perf_counter()
        if branches:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(branches)), thread_name_prefix="adaptive-retrieval") as pool:
                def timed(callback, branch):
                    started = time.perf_counter()
                    result = callback()
                    return result, self._elapsed(started), branch

                futures = {pool.submit(timed, callback, branch): (branch, index, required) for branch, index, callback, required in branches}
                for future in as_completed(futures):
                    branch, index, required = futures[future]
                    try:
                        result, branch_ms, _ = future.result()
                        if branch == "sql":
                            timing.sql_ms += branch_ms
                        else:
                            timing.vector_total_ms += branch_ms
                        if branch == "sql":
                            branch_results, branch_citations = result
                            structured.extend(branch_results)
                            citations.extend(branch_citations)
                            if required and not branch_results:
                                errors.append(Diagnostic(code="ADAPTIVE_SQL_NO_RESULTS", message="No structured evidence matched the approved query.", branch="sql"))
                        else:
                            branch_response = result
                            semantic.extend(branch_response.semantic_results)
                            citations.extend(branch_response.citations)
                            if required:
                                errors.extend(branch_response.errors)
                            else:
                                warnings.extend(
                                    Diagnostic(code=item.code, message=item.message, branch=item.branch or "vector")
                                    for item in branch_response.errors
                                )
                            warnings.extend(branch_response.warnings)
                            if required and not branch_response.semantic_results and not branch_response.errors:
                                errors.append(Diagnostic(code="ADAPTIVE_VECTOR_NO_RESULTS", message="No semantic evidence matched the approved requirement.", branch="vector"))
                    except Exception:
                        code = "ADAPTIVE_SQL_BRANCH_FAILED" if branch == "sql" else "ADAPTIVE_VECTOR_BRANCH_FAILED"
                        diagnostic = Diagnostic(code=code, message="Adaptive retrieval branch failed.", branch=branch)
                        (errors if required else warnings).append(diagnostic)
        else:
            errors.append(Diagnostic(code="NO_AVAILABLE_EVIDENCE", message="The plan contains no executable or semantic evidence requirement.", branch="adaptive"))
        timing.evidence_aggregation_ms = self._elapsed(aggregation_started)

        structured.sort(key=lambda item: (item.capability_key, item.row_index))
        semantic.sort(key=lambda item: (item.rank, item.citation_id))
        citations.sort(key=lambda item: (item.source_kind, item.citation_id))
        warnings.sort(key=lambda item: (item.code, item.branch or "", item.message))
        errors.sort(key=lambda item: (item.code, item.branch or "", item.message))
        if not structured and not semantic and not errors:
            errors.append(
                Diagnostic(
                    code="NO_EVIDENCE_RETRIEVED",
                    message="No verified evidence was retrieved for the plan.",
                    branch="adaptive",
                )
            )
        # Unavailable required evidence remains an error even if other branches
        # succeed: exact missing facts cannot be silently replaced by context.
        timing.total_ms = self._elapsed(execute_started)
        if errors and (structured or semantic):
            status = RetrievalStatus.PARTIAL
        elif errors:
            status = RetrievalStatus.FAILED
        else:
            status = RetrievalStatus.COMPLETE
        return RetrievalResponse(
            request_id=request_id,
            status=status,
            route=SelectedRoute.PLANNER_REQUIRED,
            routing=decision,
            structured_results=structured,
            semantic_results=semantic,
            citations=citations,
            warnings=warnings,
            errors=errors,
            timing=timing,
            result_counts=ResultCounts(structured=len(structured), semantic=len(semantic), citations=len(citations)),
        )

    def _execute_sql(self, compiled: CompiledQuery) -> tuple[list[StructuredResult], list[SourceReference]]:
        connection = self.connection_factory()
        try:
            # mssql-python exposes a connection timeout.  Test doubles and
            # alternate DB-API drivers may not; the bounded policy still
            # controls rows and query shape in those environments.
            if hasattr(connection, "timeout"):
                connection.timeout = QUERY_TIMEOUT_SECONDS
            cursor = connection.cursor()
            cursor.execute(compiled.sql, compiled.params)
            columns = [str(item[0]) for item in cursor.description]
            structured: list[StructuredResult] = []
            citations: list[SourceReference] = []
            for row_index, raw in enumerate(cursor.fetchall(), 1):
                row = {name: _json_value(value) for name, value in zip(columns, raw)}
                data = {field: row.get(field) for field in compiled.result_fields if field not in {"source_load_id", "source_sheet", "source_row", "loaded_at"}}
                data[compiled.metric_id] = data.pop("metric_value", None)
                identity = {"metric_id": compiled.metric_id, "requirement_index": compiled.requirement_index, "row_index": row_index, "data": data}
                citation_id = _adaptive_citation_id(identity)
                citation = SourceReference(
                    citation_id=citation_id,
                    source_kind="sql",
                    schema_name="retail",
                    tables=[compiled.source_table.split(".", 1)[1]],
                    business_keys={field: data[field] for field in compiled.result_fields if field in data and field != "metric_value"},
                    capability_key=f"adaptive.{compiled.metric_id}",
                    selected_fields=list(data),
                    source_load_id=int(row["source_load_id"]) if row.get("source_load_id") is not None else None,
                    source_sheet=str(row["source_sheet"]) if row.get("source_sheet") is not None else None,
                    source_row=int(row["source_row"]) if row.get("source_row") is not None else None,
                    source_load_at=str(row["loaded_at"]) if row.get("loaded_at") is not None else None,
                )
                citations.append(citation)
                structured.append(StructuredResult(capability_key=f"adaptive.{compiled.metric_id}", row_index=row_index, data=data, citation_ids=[citation_id]))
            return structured, citations
        finally:
            connection.close()

    def _execute_vector(self, requirement: SemanticRequirement, request: RetrievalRequest, principal: PrincipalContext) -> RetrievalResponse:
        vector_request = RetrievalRequest(
            query=requirement.query,
            route_mode="vector",
            top_k=request.top_k,
            retrieval_domain=requirement.retrieval_domain,
            doc_type=requirement.doc_type,
            agent_context=request.agent_context,
        )
        return self.semantic_service.retrieve(vector_request, principal=principal)

    @staticmethod
    def _elapsed(started: float) -> float:
        return round((time.perf_counter() - started) * 1000.0, 3)

    @staticmethod
    def _failure(request_id: str, request: RetrievalRequest, code: str, message: str, timing: RetrievalTiming) -> RetrievalResponse:
        decision = RoutingDecision(
            selected_route=SelectedRoute.PLANNER_REQUIRED,
            confidence=RoutingConfidence.HIGH,
            reason_codes=[code],
            recognized_intent="adaptive_retrieval",
        )
        return RetrievalResponse(
            request_id=request_id,
            status=RetrievalStatus.FAILED,
            route=SelectedRoute.PLANNER_REQUIRED,
            routing=decision,
            errors=[Diagnostic(code=code, message=message, branch="adaptive")],
            timing=timing,
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
            vector_search_ms=response.timing.vector_search_ms,
            vector_total_ms=response.timing.vector_total_ms,
            planning_ms=response.timing.planning_ms,
            policy_ms=response.timing.policy_ms,
            compilation_ms=response.timing.compilation_ms,
            evidence_aggregation_ms=response.timing.evidence_aggregation_ms,
            total_ms=response.timing.total_ms,
            fallback_used=False,
            error_category=response.errors[0].code if response.errors else None,
        )
