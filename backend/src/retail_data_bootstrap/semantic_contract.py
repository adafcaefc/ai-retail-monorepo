from __future__ import annotations

RETRIEVAL_DOMAINS = frozenset(
    {
        "business_entity",
        "business_rule",
        "operational_policy",
        "operational_context",
        "integration",
        "governance",
        "agent_configuration",
        "documentation",
    }
)

DOC_TYPE_RETRIEVAL_DOMAIN: dict[str, str] = {
    "sku": "business_entity",
    "store": "business_entity",
    "category": "business_entity",
    "vendor": "business_entity",
    "brand": "business_entity",
    "vertical": "business_entity",
    "formula": "business_rule",
    "terminology": "business_rule",
    "model_parameter": "business_rule",
    "promotion": "operational_policy",
    "brand_event": "operational_context",
    "data_source": "integration",
    "d365_table": "integration",
    "d365_field_mapping": "integration",
    "d365_worked_example": "integration",
    "approval_rule": "governance",
    "agent_spec": "agent_configuration",
    "workbook_overview": "documentation",
}

VOLATILE_MODEL_PARAMETERS = frozenset(
    {
        "Month index (0=Jan)",
        "Demand uplift %",
        "Promo depth %",
        "Markdown depth %",
        "Extra inbound %",
        "Vendor lead Δ (d)",
        "Safety stock Δ (d)",
    }
)


def retrieval_domain_for(doc_type: str) -> str:
    try:
        return DOC_TYPE_RETRIEVAL_DOMAIN[doc_type]
    except KeyError as error:
        raise ValueError(f"No retrieval domain is defined for doc_type {doc_type!r}") from error


def validate_contract_mapping() -> None:
    invalid = {
        doc_type: domain
        for doc_type, domain in DOC_TYPE_RETRIEVAL_DOMAIN.items()
        if domain not in RETRIEVAL_DOMAINS
    }
    if invalid:
        raise ValueError(f"Invalid retrieval-domain mappings: {invalid}")
