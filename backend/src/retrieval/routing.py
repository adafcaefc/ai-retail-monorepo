from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.retail_data_bootstrap.semantic_contract import DOC_TYPE_RETRIEVAL_DOMAIN

from .models import (
    RetrievalRequest,
    RouteMode,
    RoutingConfidence,
    RoutingDecision,
    SelectedRoute,
    VectorFilters,
)


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    reason_code: str
    filters: VectorFilters = field(default_factory=VectorFilters)


MUTATION_RE = re.compile(
    r"\b(delete|remove|update|change|set|insert|create|drop|alter|truncate|execute|exec)\b",
    re.IGNORECASE,
)
UNSAFE_RE = re.compile(
    r"\b(arbitrary\s+sql|run\s+sql|select\s+\*|union\s+select|drop\s+table|tell\s+me\s+everything)\b",
    re.IGNORECASE,
)
EXPLANATION_RE = re.compile(
    r"\b(why|diagnos(?:e|is)|recommend|what\s+should|explain|relevant\s+(?:policy|formula|rule))\b",
    re.IGNORECASE,
)
CURRENT_RE = re.compile(
    r"\b(current|today|now|latest|currently|position|on[ -]?hand|reorder\s+point|\brop\b|"
    r"workforce|forecast|proposed|highest|ranking|count|total|sum)\b",
    re.IGNORECASE,
)


def _semantic_intent(text: str) -> IntentMatch | None:
    rules: tuple[tuple[re.Pattern[str], IntentMatch], ...] = (
        (
            re.compile(r"\b(which|what)\s+(product|sku)|perishable\s+fruit|product\s+is\b", re.I),
            IntentMatch("sku_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="sku")),
        ),
        (
            re.compile(r"\b(d365|dynamics\s*365|field\s+map|data\s+source\s+map|maps?\s+to|comes?\s+from)\b", re.I),
            IntentMatch("integration_mapping", "INTEGRATION_MAPPING_INTENT", VectorFilters(retrieval_domain="integration")),
        ),
        (
            re.compile(r"\b(approv(?:e|es|al|er)|high[- ]value\s+(?:purchase|purchasing|order))\b", re.I),
            IntentMatch("approval_rule", "GOVERNANCE_INTENT", VectorFilters(retrieval_domain="governance", doc_type="approval_rule")),
        ),
        (
            re.compile(r"\b(which|what)\s+agent|agent\s+(?:handles|responsib|role)\b", re.I),
            IntentMatch("agent_responsibility", "AGENT_CONFIGURATION_INTENT", VectorFilters(retrieval_domain="agent_configuration", doc_type="agent_spec")),
        ),
        (
            re.compile(r"\b(formula|calculated|calculation|how\s+is\b|derive[ds]?)\b", re.I),
            IntentMatch("formula", "FORMULA_INTENT", VectorFilters(retrieval_domain="business_rule", doc_type="formula")),
        ),
        (
            re.compile(r"\b(what\s+does|what\s+is\s+the\s+meaning|definition|define|terminology|mean\??$)\b", re.I),
            IntentMatch("definition", "DEFINITION_INTENT", VectorFilters(retrieval_domain="business_rule", doc_type="terminology")),
        ),
        (
            re.compile(r"\b(model\s+parameter|parameter\s+meaning)\b", re.I),
            IntentMatch("model_parameter", "MODEL_PARAMETER_INTENT", VectorFilters(retrieval_domain="business_rule", doc_type="model_parameter")),
        ),
        (
            re.compile(r"\b(commercial\s+terms|vendor\s+(?:meaning|context|semantics))\b", re.I),
            IntentMatch("vendor_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="vendor")),
        ),
        (
            re.compile(r"\b(store\s+(?:meaning|semantics)|which\s+store\b)", re.I),
            IntentMatch("store_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="store")),
        ),
        (
            re.compile(r"\b(category\s+(?:meaning|semantics)|which\s+category\b)", re.I),
            IntentMatch("category_semantics", "BUSINESS_ENTITY_INTENT", VectorFilters(retrieval_domain="business_entity", doc_type="category")),
        ),
        (
            re.compile(r"\b(brand\s+event|event\s+context)\b", re.I),
            IntentMatch("brand_event", "OPERATIONAL_CONTEXT_INTENT", VectorFilters(retrieval_domain="operational_context", doc_type="brand_event")),
        ),
        (
            re.compile(r"\b(promotion\s+(?:policy|mechanism|rule))\b", re.I),
            IntentMatch("promotion_policy", "OPERATIONAL_POLICY_INTENT", VectorFilters(retrieval_domain="operational_policy", doc_type="promotion")),
        ),
        (
            re.compile(r"\b(workbook\s+(?:overview|documentation)|documentation)\b", re.I),
            IntentMatch("documentation", "DOCUMENTATION_INTENT", VectorFilters(retrieval_domain="documentation", doc_type="workbook_overview")),
        ),
        (
            re.compile(r"\b(business\s+rule|policy|risk|days[ -]of[ -]supply)\b", re.I),
            IntentMatch("business_rule", "BUSINESS_RULE_INTENT", VectorFilters(retrieval_domain="business_rule")),
        ),
    )
    for pattern, match in rules:
        if pattern.search(text):
            return match
    return None


def _sql_capabilities(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()
    if re.search(r"highest|top|ranking|ranked", lowered) and "replenish" in lowered:
        return "replenishment_ranking", ["replenishment.top_candidates"]
    if re.search(r"highest|top|ranking|ranked|at[- ]risk", lowered) and "inventory" in lowered:
        return "inventory_risk_ranking", ["inventory.at_risk"]
    if "workforce" in lowered or re.search(r"\bfte\b|staff(?:ing)?", lowered):
        return "workforce_current", ["workforce.current"]
    if "replenish" in lowered or "proposed" in lowered or "order quantity" in lowered:
        return "replenishment_current", ["sku.replenishment_current"]
    if "store" in lowered and "sku" in lowered and any(value in lowered for value in ("snapshot", "current", "inventory", "forecast")):
        return "store_sku_current", ["store_sku.snapshot"]
    if any(value in lowered for value in ("inventory", "reorder point", "on hand", "on-hand", "days of supply", "stock position")) or re.search(r"\bdays[- ]of[- ]supply\b|\brop\b", lowered):
        return "inventory_current", ["sku.inventory_current"]
    if "monthly sales" in lowered or "sales history" in lowered:
        return "monthly_sales", ["sales.monthly"]
    if "promotion" in lowered and any(value in lowered for value in ("current", "configuration", "value", "discount")):
        return "promotion_lookup", ["promotion.lookup"]
    if "trade agreement" in lowered or "current vendor terms" in lowered:
        return "trade_agreement", ["trade_agreement.by_vendor"]
    if "vendor" in lowered and any(value in lowered for value in ("current", "performance", "otif", "lead time", "moq")):
        return "vendor_lookup", ["vendor.lookup"]
    if "category" in lowered and any(value in lowered for value in ("lookup", "details", "current", "exact")):
        return "category_lookup", ["category.lookup"]
    if "brand" in lowered and any(value in lowered for value in ("lookup", "details", "current", "exact")):
        return "brand_lookup", ["brand.lookup"]
    if "legal entity" in lowered and any(value in lowered for value in ("lookup", "details", "current", "exact")):
        return "legal_entity_lookup", ["legal_entity.lookup"]
    if "store" in lowered and any(value in lowered for value in ("lookup", "details", "which", "current")):
        return "store_lookup", ["store.lookup"]
    if re.search(r"\b(price|cost|margin)\b", lowered) and re.search(r"\b(current|exact|latest)\b", lowered):
        return "sku_lookup", ["sku.lookup"]
    if re.search(r"\bsku\b|\bitem\b|\bproduct\b", lowered) and any(value in lowered for value in ("lookup", "master", "current details", "exact")):
        return "sku_lookup", ["sku.lookup"]
    return "unsupported_structured", []


def _merge_filters(request: RetrievalRequest, inferred: VectorFilters) -> VectorFilters:
    domain = inferred.retrieval_domain
    doc_type = inferred.doc_type
    if request.retrieval_domain and domain and request.retrieval_domain != domain:
        raise ValueError(
            f"Requested retrieval_domain {request.retrieval_domain!r} conflicts with "
            f"inferred {domain!r}"
        )
    if request.doc_type and doc_type and request.doc_type != doc_type:
        raise ValueError(
            f"Requested doc_type {request.doc_type!r} conflicts with inferred {doc_type!r}"
        )
    domain = request.retrieval_domain or domain
    doc_type = request.doc_type or doc_type
    if doc_type:
        expected = DOC_TYPE_RETRIEVAL_DOMAIN[doc_type]
        if domain and domain != expected:
            raise ValueError(
                f"Document type {doc_type!r} is incompatible with domain {domain!r}"
            )
        domain = domain or expected
    return VectorFilters(retrieval_domain=domain, doc_type=doc_type)


class DeterministicRouter:
    """Bounded lexical router; confidence is categorical, never probabilistic."""

    def decide(self, request: RetrievalRequest) -> RoutingDecision:
        text = " ".join(request.query.split())
        if not text:
            return RoutingDecision(
                selected_route=SelectedRoute.UNSUPPORTED,
                confidence=RoutingConfidence.HIGH,
                reason_codes=["EMPTY_QUERY"],
                recognized_intent="empty_query",
            )
        if MUTATION_RE.search(text) or UNSAFE_RE.search(text):
            return RoutingDecision(
                selected_route=SelectedRoute.UNSUPPORTED,
                confidence=RoutingConfidence.HIGH,
                reason_codes=["UNSUPPORTED_MUTATION" if MUTATION_RE.search(text) else "UNSUPPORTED_STRUCTURED_INTENT"],
                recognized_intent="unsupported_write_or_arbitrary_query",
            )

        semantic = _semantic_intent(text)
        sql_intent, capabilities = _sql_capabilities(text)
        has_current = bool(CURRENT_RE.search(text))
        has_explanation = bool(EXPLANATION_RE.search(text))
        inferred_filters = semantic.filters if semantic else VectorFilters()
        filters = _merge_filters(request, inferred_filters)
        ranking_capability = bool(
            capabilities
            and capabilities[0] in {"inventory.at_risk", "replenishment.top_candidates"}
        )

        auto_route = SelectedRoute.UNSUPPORTED
        reasons: list[str] = []
        intent = semantic.intent if semantic else sql_intent
        if ranking_capability:
            auto_route = SelectedRoute.SQL
            reasons = ["CURRENT_STATE_INTENT"]
            intent = sql_intent
        elif capabilities and (has_explanation or (semantic and has_current)):
            auto_route = SelectedRoute.HYBRID
            reasons = ["CURRENT_PLUS_EXPLANATION", "CURRENT_STATE_INTENT"]
            if semantic:
                reasons.append(semantic.reason_code)
            if not filters.retrieval_domain:
                filters = VectorFilters(retrieval_domain="business_rule")
        elif semantic and not has_current:
            auto_route = SelectedRoute.VECTOR
            reasons = [semantic.reason_code]
        elif capabilities:
            auto_route = SelectedRoute.SQL
            reasons = ["CURRENT_STATE_INTENT"]
            if re.search(r"[A-Za-z]{3}-\d{3}|S\d{3}|V\d{4}", text, re.I):
                reasons.append("EXACT_ENTITY_LOOKUP")
        elif semantic:
            auto_route = SelectedRoute.VECTOR
            reasons = [semantic.reason_code]
        elif request.retrieval_domain or request.doc_type:
            auto_route = SelectedRoute.VECTOR
            intent = "explicit_semantic_filter"
            reasons = ["EXPLICIT_VECTOR_FILTER"]
        else:
            reasons = ["UNSUPPORTED_STRUCTURED_INTENT"]

        route = auto_route
        if request.route_mode != RouteMode.AUTO:
            requested = SelectedRoute(request.route_mode.value.upper())
            if requested == SelectedRoute.SQL and (
                not capabilities or (semantic is not None and not has_current)
            ):
                route = SelectedRoute.UNSUPPORTED
                reasons = ["UNSUPPORTED_STRUCTURED_CAPABILITY"]
            elif requested == SelectedRoute.VECTOR and not (semantic or request.retrieval_domain or request.doc_type):
                route = SelectedRoute.UNSUPPORTED
                reasons = ["INVALID_ROUTE_OVERRIDE"]
            elif requested == SelectedRoute.HYBRID and not capabilities:
                route = SelectedRoute.UNSUPPORTED
                reasons = ["UNSUPPORTED_STRUCTURED_CAPABILITY", "INVALID_ROUTE_OVERRIDE"]
            else:
                route = requested
                reasons = [*reasons, "EXPLICIT_ROUTE_OVERRIDE"]

        confidence = (
            RoutingConfidence.HIGH
            if route != SelectedRoute.UNSUPPORTED and (semantic or capabilities)
            else RoutingConfidence.LOW
        )
        return RoutingDecision(
            selected_route=route,
            confidence=confidence,
            reason_codes=list(dict.fromkeys(reasons)),
            recognized_intent=intent,
            selected_sql_capabilities=capabilities if route in {SelectedRoute.SQL, SelectedRoute.HYBRID} else [],
            selected_vector_filters=filters if route in {SelectedRoute.VECTOR, SelectedRoute.HYBRID} else VectorFilters(),
            fallback_allowed=False,
        )
