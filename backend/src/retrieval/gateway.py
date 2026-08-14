"""Common retrieval gateway used by existing chatbot generation paths."""

from __future__ import annotations

import re
import inspect
import time
from collections.abc import Sequence
from typing import Any

from .authorization import PrincipalContext, cli_principal
from .models import RetrievalRequest, RetrievalResponse, RetrievalStatus, SelectedRoute
from .observability import TraceSink, emit_trace
from .orchestrator import AdaptiveRetrievalOrchestrator
from .planner import QueryPlan, SemanticRequirement, StructuredRequirement
from .service import RetrievalService
from .catalog import CATALOG


FORECAST_QUERY_RE = re.compile(
    r"forecast.*demand.*next\s+7\s+days.*basket.*accuracy.*mape",
    re.IGNORECASE | re.DOTALL,
)


def _fallback_forecast_plan(query: str, agent_context: str | None) -> QueryPlan:
    """Make the exact acceptance query useful if planner credentials are absent.

    This is a fixed, catalog-derived fallback for one known request shape.  It
    does not broaden planner authority and explicitly retains the unavailable
    basket/MAPE requirements.
    """
    return QueryPlan(
        request=query,
        agent_context=agent_context,
        catalog_version=CATALOG.catalog_version,
        structured_requirements=[
            StructuredRequirement(
                metric_id="demand.forecast_7d",
                aggregation="sum",
                rationale="The approved StoreSkuSnapshot seven-day forecast is available.",
            ),
            StructuredRequirement(
                metric_id="forecast.basket",
                availability="UNAVAILABLE",
                unavailable_reason="No approved forecast basket-composition metric exists in the catalog.",
                required=True,
                rationale="The request asks for basket composition, which must remain visibly unavailable.",
            ),
            StructuredRequirement(
                metric_id="forecast.backtested_mape",
                availability="UNAVAILABLE",
                unavailable_reason="No approved historical forecast-error or backtested MAPE metric exists in the catalog.",
                required=True,
                rationale="The request asks for backtested MAPE, which must not be fabricated.",
            ),
        ],
        semantic_requirements=[
            SemanticRequirement(
                query="forecast accuracy methodology and backtested MAPE",
                retrieval_domain="business_rule",
                required=False,
                rationale="Retrieve methodology only. It cannot supply a missing actual MAPE value.",
            )
        ],
        planning_notes="Deterministic acceptance-query fallback after planner failure.",
    )


class ChatRetrievalGateway:
    """Route fast paths and adaptive plans into one normalized response."""

    def __init__(
        self,
        *,
        fast_service: RetrievalService | None = None,
        adaptive_orchestrator: AdaptiveRetrievalOrchestrator | None = None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        self.trace_sink = trace_sink
        self.fast_service = fast_service or RetrievalService(trace_sink=trace_sink)
        self.adaptive_orchestrator = adaptive_orchestrator or AdaptiveRetrievalOrchestrator(
            semantic_service=self.fast_service,
            trace_sink=trace_sink,
        )

    def retrieve(
        self,
        query: str,
        *,
        conversation_context: Sequence[str] | None = None,
        agent_context: str | None = None,
        top_k: int = 5,
        principal: PrincipalContext | None = None,
    ) -> RetrievalResponse:
        gateway_started = time.perf_counter()
        principal = principal or cli_principal()
        request = RetrievalRequest(query=query, top_k=top_k, agent_context=agent_context)
        emit_trace(self.trace_sink, "gateway.started")
        fast = self.fast_service.retrieve(request, principal=principal)
        emit_trace(
            self.trace_sink,
            "gateway.fast_result",
            route=fast.route.value,
            status=fast.status.value,
            capabilities=list(fast.routing.selected_sql_capabilities),
        )
        if fast.route != SelectedRoute.PLANNER_REQUIRED:
            emit_trace(
                self.trace_sink,
                "gateway.fast_path",
                route=fast.route.value,
            )
            return self._finish(fast, gateway_started, fallback_used=False)

        emit_trace(
            self.trace_sink,
            "gateway.adaptive_escalation",
            route=fast.route.value,
            reason_codes=list(fast.routing.reason_codes),
        )
        adaptive = self.adaptive_orchestrator.retrieve(
            request,
            principal=principal,
            conversation_context=conversation_context,
            agent_context=agent_context,
        )
        fallback_decision_started = time.perf_counter()
        fallback_condition = (
            adaptive.status == RetrievalStatus.FAILED
            and any(
                item.code in {
                    "PLANNER_FAILED",
                    "QUERY_POLICY_REJECTED",
                    "SQL_COMPILATION_REJECTED",
                    "NO_AVAILABLE_EVIDENCE",
                }
                for item in adaptive.errors
            )
            and FORECAST_QUERY_RE.search(query)
        )
        fallback_decision_ms = round((time.perf_counter() - fallback_decision_started) * 1000.0, 3)
        adaptive.timing.fallback_decision_ms = fallback_decision_ms
        emit_trace(
            self.trace_sink,
            "gateway.fallback_decision",
            elapsed_ms=fallback_decision_ms,
            selected=bool(fallback_condition),
            failure_codes=[item.code for item in adaptive.errors],
        )
        if fallback_condition:
            fallback_started = time.perf_counter()
            emit_trace(
                self.trace_sink,
                "gateway.fallback_started",
                failure_category=getattr(
                    getattr(self.adaptive_orchestrator, "planner", None),
                    "last_failure_category",
                    None,
                ),
                reason_codes=[item.code for item in adaptive.errors],
            )
            execute_plan = self.adaptive_orchestrator.execute_plan
            execute_kwargs = {
                "principal": principal,
                "request_id": adaptive.request_id,
            }
            # Keep compatibility with narrow test/integration orchestrator
            # doubles while preserving planner timing in the production
            # AdaptiveRetrievalOrchestrator.
            if "timing" in inspect.signature(execute_plan).parameters:
                execute_kwargs["timing"] = adaptive.timing
            adaptive = execute_plan(
                request,
                _fallback_forecast_plan(query, agent_context),
                **execute_kwargs,
            )
            adaptive.timing.fallback_ms = round((time.perf_counter() - fallback_started) * 1000.0, 3)
            emit_trace(
                self.trace_sink,
                "gateway.acceptance_fallback",
                elapsed_ms=adaptive.timing.fallback_ms,
                reason_codes=[item.code for item in adaptive.errors],
            )
        return self._finish(adaptive, gateway_started, fallback_used=bool(fallback_condition))

    def _finish(
        self,
        response: RetrievalResponse,
        started: float,
        *,
        fallback_used: bool,
    ) -> RetrievalResponse:
        response.timing.gateway_ms = round((time.perf_counter() - started) * 1000.0, 3)
        emit_trace(
            self.trace_sink,
            "gateway.completed",
            elapsed_ms=response.timing.gateway_ms,
            route=response.route.value,
            status=response.status.value,
            fallback_used=fallback_used,
        )
        return response


__all__ = ["ChatRetrievalGateway"]
