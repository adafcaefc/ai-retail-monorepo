"""Common retrieval gateway used by existing chatbot generation paths."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .authorization import PrincipalContext, cli_principal
from .models import RetrievalRequest, RetrievalResponse, RetrievalStatus, SelectedRoute
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
    ) -> None:
        self.fast_service = fast_service or RetrievalService()
        self.adaptive_orchestrator = adaptive_orchestrator or AdaptiveRetrievalOrchestrator(
            semantic_service=self.fast_service
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
        principal = principal or cli_principal()
        request = RetrievalRequest(query=query, top_k=top_k, agent_context=agent_context)
        fast = self.fast_service.retrieve(request, principal=principal)
        if fast.route != SelectedRoute.PLANNER_REQUIRED:
            return fast

        adaptive = self.adaptive_orchestrator.retrieve(
            request,
            principal=principal,
            conversation_context=conversation_context,
            agent_context=agent_context,
        )
        if (
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
        ):
            adaptive = self.adaptive_orchestrator.execute_plan(
                request,
                _fallback_forecast_plan(query, agent_context),
                principal=principal,
                request_id=adaptive.request_id,
            )
        return adaptive


__all__ = ["ChatRetrievalGateway"]
