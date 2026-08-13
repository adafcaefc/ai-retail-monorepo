from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.retail_data_bootstrap.embedding_config import EmbeddingConfig
from src.retail_data_bootstrap.database import open_connection
from src.retrieval.api import _internal_poc_principal, router as retrieval_api_router
from src.retrieval.authorization import (
    InternalPocAuthorizationPolicy,
    PrincipalContext,
)
from src.retrieval.capabilities import CAPABILITIES, StructuredSqlExecutor, capability_catalog
from src.retrieval.entities import EntityResolution, EntityResolver
from src.retrieval.evaluation import DEFAULT_ROUTING_FIXTURE, evaluate_routing
from src.retrieval.models import (
    EntityHint,
    EntityType,
    RecognizedEntity,
    RetrievalRequest,
    RetrievalResponse,
    SelectedRoute,
    SourceReference,
    StructuredResult,
)
from src.retrieval.observability import log_retrieval_event, query_fingerprint
from src.retrieval.routing import DeterministicRouter
from src.retrieval.service import RetrievalService


def test_routing_evaluation_fixture_has_at_least_30_cases_and_passes():
    cases = json.loads(DEFAULT_ROUTING_FIXTURE.read_text(encoding="utf-8"))
    assert len(cases) >= 30
    assert {case["expected_route"] for case in cases} == {
        "SQL", "VECTOR", "HYBRID", "UNSUPPORTED"
    }
    result = evaluate_routing()
    assert result == {
        "valid": True,
        "case_count": len(cases),
        "passed": len(cases),
        "failed": 0,
        "failures": [],
    }


@pytest.mark.parametrize(
    ("query", "route", "capability", "domain", "doc_type"),
    [
        ("What is the current inventory position for GRC-001?", "SQL", "sku.inventory_current", None, None),
        ("What does Days of Supply mean?", "VECTOR", None, "business_rule", "terminology"),
        ("How is average daily sales per store calculated?", "VECTOR", None, "business_rule", "formula"),
        ("Which D365 field maps to demand forecasting?", "VECTOR", None, "integration", None),
        ("Who approves a high-value purchase order?", "VECTOR", None, "governance", "approval_rule"),
        ("Which agent is responsible for replenishment?", "VECTOR", None, "agent_configuration", "agent_spec"),
        ("Why is GRC-001 at replenishment risk?", "HYBRID", "sku.replenishment_current", "business_rule", None),
        ("Which product is a perishable fruit?", "VECTOR", None, "business_entity", "sku"),
    ],
)
def test_mandatory_route_and_filter_regressions(query, route, capability, domain, doc_type):
    decision = DeterministicRouter().decide(RetrievalRequest(query=query))
    assert decision.selected_route.value == route
    if capability:
        assert capability in decision.selected_sql_capabilities
    assert decision.selected_vector_filters.retrieval_domain == domain
    assert decision.selected_vector_filters.doc_type == doc_type


def test_route_override_is_safe_and_filters_intersect_strictly():
    router = DeterministicRouter()
    forced_sql = router.decide(
        RetrievalRequest(query="What does Days of Supply mean?", route_mode="sql")
    )
    assert forced_sql.selected_route == SelectedRoute.UNSUPPORTED
    assert "UNSUPPORTED_STRUCTURED_CAPABILITY" in forced_sql.reason_codes
    forced_vector = router.decide(
        RetrievalRequest(
            query="Which product is a perishable fruit?",
            route_mode="vector",
            retrieval_domain="business_entity",
            doc_type="sku",
        )
    )
    assert forced_vector.selected_route == SelectedRoute.VECTOR
    assert "EXPLICIT_ROUTE_OVERRIDE" in forced_vector.reason_codes
    with pytest.raises(ValueError, match="conflicts"):
        router.decide(
            RetrievalRequest(
                query="Which product is a perishable fruit?",
                retrieval_domain="governance",
            )
        )


def test_request_contract_forbids_untrusted_identifiers_profiles_and_extra_fields():
    with pytest.raises(ValidationError):
        RetrievalRequest(query="x", table="retail.Sku")
    with pytest.raises(ValidationError):
        RetrievalRequest(query="x", embedding_profile_id=7)
    with pytest.raises(ValidationError):
        RetrievalRequest(query="x", top_k=21)
    assert "answer" not in RetrievalResponse.model_fields


def test_capability_catalog_is_allowlisted_explicit_and_bounded():
    catalog = capability_catalog()
    assert len(catalog) == 15
    assert {item["capability_key"] for item in catalog} == set(CAPABILITIES)
    for capability in CAPABILITIES.values():
        normalized = " ".join(capability.query.upper().split())
        assert "SELECT *" not in normalized
        assert "RETAIL.[" in normalized or "RETAIL." in normalized
        assert capability.max_rows <= 50
        assert capability.selected_fields


class RecordingCursor:
    def __init__(self, rows, columns):
        self.rows = rows
        self.description = [(name,) for name in columns]
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return list(self.rows)


class RecordingConnection:
    def __init__(self, cursor):
        self.value = cursor
        self.closed = False

    def cursor(self):
        return self.value

    def close(self):
        self.closed = True


def test_sql_parameters_cannot_change_template_and_provenance_is_normalized():
    capability = CAPABILITIES["vendor.lookup"]
    columns = [*capability.selected_fields, "source_load_id", "source_sheet", "source_row", "loaded_at"]
    row = ["V0001", "V1", "Aurora", "G", "USD", "30D", "DAP", 3, 10, 98, 99, 1, 97, 1, "Vendor_Master", 2, "2026-08-11T00:00:00"]
    cursor = RecordingCursor([tuple(row)], columns)
    connection = RecordingConnection(cursor)
    malicious = RecognizedEntity(
        entity_type="vendor",
        identifier="V0001'; DROP TABLE retail.Vendor;--",
        display_name=None,
        resolution_method="test",
    )
    results, citations, _ = StructuredSqlExecutor().execute(
        "vendor.lookup", {EntityType.VENDOR: malicious}, connection
    )
    executed_sql, params = cursor.calls[0]
    assert malicious.identifier not in executed_sql
    assert params == (malicious.identifier,)
    assert executed_sql == capability.query
    assert results[0].data["vendor_account"] == "V0001"
    assert citations[0].schema_name == "retail"
    assert citations[0].tables == ["Vendor"]
    assert citations[0].source_sheet == "Vendor_Master"
    assert "DROP TABLE" not in json.dumps(citations[0].model_dump())


@pytest.mark.parametrize("capability_key", sorted(CAPABILITIES))
def test_every_sql_capability_builds_only_fixed_bounded_parameters(capability_key):
    capability = CAPABILITIES[capability_key]
    cursor = RecordingCursor([], [*capability.selected_fields, "source_load_id", "source_sheet", "source_row", "loaded_at"])
    connection = RecordingConnection(cursor)
    entities = {
        entity_type: RecognizedEntity(
            entity_type=entity_type,
            identifier=f"value-for-{entity_type.value}",
            display_name=None,
            resolution_method="test",
        )
        for entity_type in capability.required_entities
    }
    StructuredSqlExecutor().execute(
        capability_key, entities, connection, row_limit=999
    )
    sql, params = cursor.calls[0]
    assert sql == capability.query
    assert len(params) == len(capability.parameter_entities) + int(capability.has_limit_parameter)
    if capability.has_limit_parameter:
        assert params[0] == capability.max_rows
    for entity_type in capability.parameter_entities:
        assert entities[entity_type].identifier in params


class ResolverCursor:
    def __init__(self):
        self.rows = []
        self.description = []

    def execute(self, sql, params=()):
        if "retail.[Sku]" in sql:
            self.description = [("sku_id",), ("item_name",)]
            self.rows = [("GRC-001", "Fruit 1")] if params and params[0].upper() == "GRC-001" else []
        elif "retail.[Category]" in sql:
            self.description = [("category_id",), ("category_name",)]
            self.rows = [("DGT-C01", "Electronics"), ("ELC-C01", "Electronics")]
        return self

    def fetchall(self):
        return list(self.rows)


def test_entity_resolution_exact_unknown_and_ambiguous_behavior():
    connection = RecordingConnection(ResolverCursor())
    resolver = EntityResolver()
    exact = resolver.resolve("inventory GRC-001", [], (EntityType.SKU,), connection)
    assert exact.entities[0].identifier == "GRC-001"
    assert exact.entities[0].resolution_method == "canonical_identifier"
    missing = resolver.resolve("inventory GRC-999", [], (EntityType.SKU,), connection)
    assert missing.missing == [EntityType.SKU]
    ambiguous = resolver.resolve(
        "category Electronics",
        [EntityHint(entity_type="category", value="Electronics")],
        (EntityType.CATEGORY,),
        connection,
    )
    assert len(ambiguous.ambiguous[EntityType.CATEGORY]) == 2
    assert not ambiguous.entities


class FakeResolver:
    def __init__(self, *, missing=False, ambiguous=False):
        self.missing = missing
        self.ambiguous = ambiguous

    def resolve(self, query, hints, required, connection):
        result = EntityResolution()
        if self.missing:
            result.missing = list(required)
        elif self.ambiguous:
            result.ambiguous = {(required[0] if required else EntityType.SKU): [{"identifier": "A", "display_name": "A"}, {"identifier": "B", "display_name": "B"}]}
        else:
            result.entities = [
                RecognizedEntity(entity_type="sku", identifier="GRC-001", display_name="Fruit 1", resolution_method="canonical_identifier")
            ]
        return result


class FakeSqlExecutor:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def execute(self, capability, entities, connection, *, row_limit):
        self.calls.append((capability, entities, row_limit))
        if self.fail:
            raise RuntimeError("database detail that must be redacted")
        citation = SourceReference(
            citation_id="sql:test", source_kind="sql", schema_name="retail",
            tables=["ReplenishmentProposal"], business_keys={"sku_id": "GRC-001"},
            capability_key=capability, selected_fields=["order_buy_units"],
        )
        return [StructuredResult(capability_key=capability, row_index=1, data={"sku_id": "GRC-001", "order_buy_units": 192}, citation_ids=["sql:test"])], [citation], False


class FakeProvider:
    def embed_query(self, query):
        value = np.zeros(384, dtype=np.float32)
        value[0] = 1
        return value


def fake_semantic_search(query, provider, config, **kwargs):
    provider.embed_query(query)
    assert kwargs["allow_building"] is False
    return {
        "profile_key": config.profile_key,
        "results": [{
            "rank": 1, "cosine_distance": 0.1, "cosine_similarity": 0.9,
            "doc_key": "terminology:replenishment", "doc_type": "terminology",
            "retrieval_domain": "business_rule", "source_sheet": "Glossary",
            "source_key": "Replenishment", "matched_chunk_index": 0,
            "matched_chunk_key": "terminology:replenishment#000", "excerpt": "Replenishment rule evidence.",
        }],
    }


def _service(*, resolver=None, sql=None, search=fake_semantic_search):
    connection = RecordingConnection(RecordingCursor([], []))
    return RetrievalService(
        entity_resolver=resolver or FakeResolver(),
        sql_executor=sql or FakeSqlExecutor(),
        connection_factory=lambda: connection,
        config_factory=EmbeddingConfig,
        provider_factory=lambda config: FakeProvider(),
        semantic_search_fn=search,
    ), connection


def test_hybrid_service_returns_both_evidence_types_independent_citations_and_no_answer():
    service, connection = _service()
    response = service.retrieve(
        RetrievalRequest(query="Why is GRC-001 at replenishment risk?"),
        principal=PrincipalContext("test", True),
    )
    assert response.route == SelectedRoute.HYBRID
    assert response.status == "COMPLETE"
    assert response.result_counts.structured == 1
    assert response.result_counts.semantic == 1
    assert {citation.source_kind for citation in response.citations} == {"sql", "semantic"}
    assert response.semantic_results[0].source_sheet == "Glossary"
    assert "answer" not in response.model_dump()
    assert connection.closed


def test_embedding_provider_is_reused_and_active_profile_is_not_caller_selectable():
    calls = []
    connection = RecordingConnection(RecordingCursor([], []))
    service = RetrievalService(
        entity_resolver=FakeResolver(),
        sql_executor=FakeSqlExecutor(),
        connection_factory=lambda: connection,
        config_factory=EmbeddingConfig,
        provider_factory=lambda config: calls.append(config.profile_key) or FakeProvider(),
        semantic_search_fn=fake_semantic_search,
    )
    principal = PrincipalContext("test", True)
    for _ in range(2):
        response = service.retrieve(
            RetrievalRequest(query="What does Days of Supply mean?"),
            principal=principal,
        )
        assert response.routing.selected_vector_filters.doc_type == "terminology"
    assert calls == ["local-bge-small-en-v1.5-384-v1"]


def test_hybrid_branch_failure_and_missing_entity_are_explicit_without_substitution():
    sql_failure, _ = _service(sql=FakeSqlExecutor(fail=True))
    failed = sql_failure.retrieve(
        RetrievalRequest(query="Why is GRC-001 at replenishment risk?"),
        principal=PrincipalContext("test", True),
    )
    assert failed.status == "PARTIAL"
    assert not failed.structured_results
    assert failed.semantic_results
    assert any(error.code == "HYBRID_SQL_BRANCH_FAILED" for error in failed.errors)

    missing_service, _ = _service(resolver=FakeResolver(missing=True))
    missing = missing_service.retrieve(
        RetrievalRequest(query="Why is GRC-999 at replenishment risk?"),
        principal=PrincipalContext("test", True),
    )
    assert any(error.code == "ENTITY_NOT_FOUND" for error in missing.errors)
    assert any(warning.code == "HYBRID_SQL_BRANCH_FAILED" for warning in missing.warnings)
    assert not missing.structured_results
    assert missing.semantic_results


def test_vector_failure_does_not_substitute_sql_for_semantic_context():
    def failing_search(*args, **kwargs):
        raise RuntimeError("No ACTIVE embedding profile is available")

    service, _ = _service(search=failing_search)
    response = service.retrieve(
        RetrievalRequest(query="Why is GRC-001 at replenishment risk?"),
        principal=PrincipalContext("test", True),
    )
    assert response.structured_results
    assert not response.semantic_results
    assert any(error.code == "ACTIVE_EMBEDDING_PROFILE_UNAVAILABLE" for error in response.errors)
    assert any(warning.code == "HYBRID_VECTOR_BRANCH_FAILED" for warning in response.warnings)


def test_unknown_sql_entity_prevents_broad_query_execution():
    executor = FakeSqlExecutor()
    service, _ = _service(resolver=FakeResolver(missing=True), sql=executor)
    response = service.retrieve(
        RetrievalRequest(query="What is the current inventory position for GRC-999?"),
        principal=PrincipalContext("test", True),
    )
    assert response.route == SelectedRoute.SQL
    assert any(error.code == "ENTITY_NOT_FOUND" for error in response.errors)
    assert executor.calls == []


def test_ambiguous_entity_prevents_sql_and_returns_bounded_candidates():
    executor = FakeSqlExecutor()
    service, _ = _service(resolver=FakeResolver(ambiguous=True), sql=executor)
    response = service.retrieve(
        RetrievalRequest(
            query="Show current details for category Accessories.",
            entity_hints=[{"entity_type": "category", "value": "Accessories"}],
        ),
        principal=PrincipalContext("test", True),
    )
    assert response.route == SelectedRoute.SQL
    error = next(error for error in response.errors if error.code == "AMBIGUOUS_ENTITY")
    assert "identifier" in error.message
    assert executor.calls == []


def test_authorization_policy_rejects_non_internal_principal():
    with pytest.raises(PermissionError):
        InternalPocAuthorizationPolicy().authorize(
            PrincipalContext("external", False), RetrievalRequest(query="definition")
        )


def test_api_is_internal_disabled_by_default(monkeypatch):
    monkeypatch.setenv("RETAIL_RETRIEVAL_API_ENABLED", "false")
    with pytest.raises(HTTPException) as raised:
        _internal_poc_principal()
    assert raised.value.status_code == 503
    assert "internal" in raised.value.detail.lower()
    route = next(route for route in retrieval_api_router.routes if route.path.endswith("/query"))
    assert route.include_in_schema is False


def test_observability_uses_fingerprint_not_query_text(caplog):
    query = "Secret-looking but nonsecret exact question"
    with caplog.at_level(logging.INFO, logger="src.retrieval"):
        log_retrieval_event(
            request_id="id",
            query_fingerprint=query_fingerprint(query),
            route="VECTOR",
            query=query,
            vector=[1.0, 2.0],
        )
    text = caplog.text
    assert query not in text
    assert "1.0" not in text
    assert query_fingerprint(query) in text


def test_frozen_jsonl_contract_contains_no_retrieval_or_vector_fields():
    path = Path(__file__).parents[2] / "generated" / "retail_documents_sample.jsonl"
    if not path.exists():
        # `/generated/` is gitignored, so this artifact does not exist on a
        # fresh checkout -- it is written by
        # `python -m src.retail_data_bootstrap generate-documents`. Skipping
        # keeps the contract assertion meaningful wherever the file is
        # present, without failing a clone that has never run the generator.
        pytest.skip(
            "generated/retail_documents_sample.jsonl is absent; run "
            "`python -m src.retail_data_bootstrap generate-documents` first"
        )
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert set(row) == {
        "doc_key", "doc_type", "retrieval_domain", "source_sheet",
        "source_key", "content", "metadata", "content_hash",
    }


@pytest.mark.azure_sql
def test_live_retrieval_sql_vector_hybrid_when_explicitly_enabled():
    if os.getenv("RUN_AZURE_SQL_INTEGRATION") != "1" or os.getenv("RUN_LOCAL_EMBEDDING_INTEGRATION") != "1":
        pytest.skip("Set both live integration flags to run Phase 6 live retrieval")
    service = RetrievalService()
    principal = PrincipalContext("integration", True)
    sql = service.retrieve(RetrievalRequest(query="What is the current inventory position for GRC-001?"), principal=principal)
    vector = service.retrieve(RetrievalRequest(query="Which product is a perishable fruit?", top_k=5), principal=principal)
    hybrid = service.retrieve(RetrievalRequest(query="Why is GRC-001 at replenishment risk?", top_k=5), principal=principal)
    assert sql.status == "COMPLETE" and sql.structured_results
    assert vector.status == "COMPLETE" and vector.semantic_results[0].doc_type == "sku"
    assert hybrid.structured_results and hybrid.semantic_results
    assert all(item.doc_key for item in vector.semantic_results)


@pytest.mark.azure_sql
def test_every_live_sql_capability_and_direct_inventory_crosscheck_when_enabled():
    if os.getenv("RUN_AZURE_SQL_INTEGRATION") != "1":
        pytest.skip("Set RUN_AZURE_SQL_INTEGRATION=1 to run live capability checks")
    identifiers = {
        EntityType.SKU: "GRC-001",
        EntityType.STORE: "S001",
        EntityType.VENDOR: "V0001",
        EntityType.LEGAL_ENTITY: "GRC",
        EntityType.CATEGORY: "GRC-C01",
        EntityType.BRAND: "Brava",
        EntityType.PROMOTION: "PRM-0001",
    }
    entities = {
        entity_type: RecognizedEntity(
            entity_type=entity_type,
            identifier=identifier,
            display_name=None,
            resolution_method="integration_fixture",
        )
        for entity_type, identifier in identifiers.items()
    }
    connection = open_connection()
    try:
        executor = StructuredSqlExecutor()
        for capability_key, capability in CAPABILITIES.items():
            results, citations, _ = executor.execute(
                capability_key, entities, connection, row_limit=5
            )
            assert results, capability_key
            assert len(results) <= capability.max_rows
            assert len(results) == len(citations)
            assert all(citation.schema_name == "retail" for citation in citations)
            assert all(citation.capability_key == capability_key for citation in citations)
        service = RetrievalService()
        retrieved = service.retrieve(
            RetrievalRequest(query="What is the current inventory position for GRC-001?"),
            principal=PrincipalContext("integration", True),
        )
        cursor = connection.cursor()
        cursor.execute(
            "SELECT inventory_position FROM retail.InventorySnapshot WHERE sku_id = ?;",
            ("GRC-001",),
        )
        direct = float(cursor.fetchone()[0])
        assert retrieved.structured_results[0].data["inventory_position"] == direct
    finally:
        connection.close()
