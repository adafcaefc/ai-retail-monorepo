from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from src.retail_data_bootstrap.database import SOURCE_LOAD_COLUMNS, TABLE_COLUMNS
from src.retrieval.authorization import cli_principal
from src.retrieval.catalog import CATALOG, CATALOG_PATH, search_catalog
from src.retrieval.compiler import DeterministicSqlCompiler
from src.retrieval.models import (
    Diagnostic,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalStatus,
    RoutingConfidence,
    RoutingDecision,
    SelectedRoute,
    SemanticResult,
    SourceReference,
    StructuredResult,
)
from src.retrieval.orchestrator import AdaptiveRetrievalOrchestrator
from src.retrieval.policy import QueryPolicy, QueryPolicyError
from src.retrieval.planner import (
    AdaptiveQueryPlanner,
    PlannerValidationError,
    QueryPlan,
    SemanticRequirement,
    StructuredRequirement,
    QueryFilter,
    TimeWindow,
)
from src.retrieval.authorization import PrincipalContext
from src.retrieval.routing import DeterministicRouter
from src.retrieval.service import RetrievalService


FORECAST_QUERY = (
    "Forecast demand for the next 7 days, including forecast basket and "
    "forecast accuracy using backtested MAPE."
)


def test_safe_unseen_retail_question_escalates_to_planner():
    decision = DeterministicRouter().decide(RetrievalRequest(query=FORECAST_QUERY))
    assert decision.selected_route == SelectedRoute.PLANNER_REQUIRED
    assert decision.reason_codes == ["PLANNER_REQUIRED"]
    assert decision.selected_sql_capabilities == []


@pytest.mark.parametrize(
    "query",
    [
        "Analyze the inventory trend for GRC-001.",
        "Compare inventory and forecast demand by SKU.",
        "Compare monthly sales and forecast demand.",
        "Analyze vendor performance with replenishment requirements.",
        "Show promotion uplift and forecast demand by category.",
    ],
)
def test_safe_analytical_requests_escalate_when_a_fast_path_is_insufficient(query):
    decision = DeterministicRouter().decide(RetrievalRequest(query=query))
    assert decision.selected_route == SelectedRoute.PLANNER_REQUIRED
    assert "PLANNER_REQUIRED" in decision.reason_codes


@pytest.mark.parametrize(
    "query",
    [
        "How much inventory is there by store?",
        "Show current inventory.",
        "Show current inventory and forecast demand for GRC-001.",
        "Which categories have the highest inventory?",
        "What are sales by legal entity?",
        "Which vendors have the best service levels?",
        "Show GMROI by category.",
        "Which SKUs are highest at risk?",
    ],
)
def test_uncovered_retail_analytical_shapes_do_not_use_a_wrong_fast_path(query):
    decision = DeterministicRouter().decide(RetrievalRequest(query=query))
    assert decision.selected_route == SelectedRoute.PLANNER_REQUIRED
    assert not decision.selected_sql_capabilities


def test_entity_bound_phase6_lookup_without_entity_escalates_for_aggregate_planning():
    decision = DeterministicRouter().decide(
        RetrievalRequest(query="What is current inventory position?")
    )
    assert decision.selected_route == SelectedRoute.PLANNER_REQUIRED
    assert "FAST_PATH_REQUIRES_ENTITY" in decision.reason_codes


def test_fast_paths_and_unsafe_refusals_are_unchanged():
    router = DeterministicRouter()
    assert router.decide(
        RetrievalRequest(query="What is the current inventory position for GRC-001?")
    ).selected_route == SelectedRoute.SQL
    assert router.decide(
        RetrievalRequest(query="What does Days of Supply mean?")
    ).selected_route == SelectedRoute.VECTOR
    assert router.decide(
        RetrievalRequest(query="Why is GRC-001 at replenishment risk?")
    ).selected_route == SelectedRoute.HYBRID
    assert router.decide(
        RetrievalRequest(query="DROP TABLE retail.Sku")
    ).selected_route == SelectedRoute.UNSUPPORTED
    assert router.decide(
        RetrievalRequest(query="What color is the sky?")
    ).selected_route == SelectedRoute.UNSUPPORTED


def test_planner_required_service_does_not_open_database():
    def no_database():
        raise AssertionError("planner escalation must not open the Phase 6 database")

    response = RetrievalService(connection_factory=no_database).retrieve(
        RetrievalRequest(query=FORECAST_QUERY),
        principal=cli_principal(),
    )
    assert response.route == SelectedRoute.PLANNER_REQUIRED
    assert response.errors[0].code == "PLANNER_REQUIRED"
    assert response.structured_results == []
    assert response.semantic_results == []


def test_catalog_is_versioned_machine_readable_and_approved():
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert raw["catalog_version"] == CATALOG.catalog_version
    assert len(CATALOG.tables) == 15
    assert {table.name.split(".", 1)[0] for table in CATALOG.tables} == {"retail"}
    assert all(table.keys and table.columns for table in CATALOG.tables)
    assert all(metric.table.startswith("retail.") for metric in CATALOG.metrics)
    assert all(metric.column for metric in CATALOG.metrics)
    assert CATALOG.known_unavailable
    for table in CATALOG.tables:
        columns = {column.name for column in table.columns}
        assert set(table.keys) <= columns, table.name
        assert set(table.time_fields) <= columns, table.name
        assert set(table.approved_filters) <= columns, table.name
    for metric in CATALOG.metrics:
        table = next(table for table in CATALOG.tables if table.name == metric.table)
        columns = {column.name for column in table.columns}
        assert metric.column in columns
        assert set(metric.dimensions) <= columns
    forecast = next(metric for metric in CATALOG.metrics if metric.metric_id == "demand.forecast_7d")
    assert "forecast basket" not in forecast.aliases


def test_catalog_columns_and_relationships_are_subsets_of_normalized_schema():
    catalog_tables = {table.name.split(".", 1)[1]: table for table in CATALOG.tables}
    actual_tables = set(TABLE_COLUMNS) | {"SourceLoad"}
    assert set(catalog_tables) == actual_tables
    for name, table in catalog_tables.items():
        lineage = {"source_load_id", "source_sheet", "source_row", "loaded_at"}
        actual_columns = (
            set(SOURCE_LOAD_COLUMNS)
            if name == "SourceLoad"
            else set(TABLE_COLUMNS.get(name, ())) | lineage
        )
        assert {column.name for column in table.columns} <= actual_columns
        assert set(table.keys) <= actual_columns
        assert set(table.approved_filters) <= actual_columns
    for relationship in CATALOG.relationships:
        source = relationship.from_table.split(".", 1)[1]
        target = relationship.to_table.split(".", 1)[1]
        assert set(relationship.from_columns) <= set(TABLE_COLUMNS[source])
        assert set(relationship.to_columns) <= set(TABLE_COLUMNS[target])


def test_catalog_search_is_relevant_bounded_and_reports_unavailable_metrics():
    context = search_catalog(FORECAST_QUERY, limit=4)
    assert len(context.tables) <= 4
    assert len(context.metrics) <= 4
    assert any(metric.metric_id == "demand.forecast_7d" for metric in context.metrics)
    assert {item.term for item in context.unavailable} == {"forecast accuracy", "forecast basket"}
    assert len(context.prompt_text()) < 16000
    with pytest.raises(ValueError):
        search_catalog(" ")
    with pytest.raises(ValueError):
        search_catalog("x" * 1001)


def test_query_plan_rejects_sql_control_syntax():
    with pytest.raises(ValidationError, match="SQL"):
        QueryPlan(
            request="Find inventory",
            catalog_version=CATALOG.catalog_version,
            structured_requirements=[
                StructuredRequirement(
                    metric_id="inventory.inventory_position",
                )
            ],
            dependencies=["SELECT * from retail.InventorySnapshot"],
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        QueryPlan(
            request="Find inventory",
            catalog_version=CATALOG.catalog_version,
            structured_requirements=[
                StructuredRequirement(metric_id="inventory.inventory_position")
            ],
            sql="SELECT * FROM retail.InventorySnapshot",
        )


def test_planner_uses_bounded_catalog_and_marks_unknown_requirements_unavailable():
    observed = {}

    def runner(planner_input):
        observed["input"] = planner_input
        return {
            "request": planner_input.user_request,
            "catalog_version": planner_input.catalog.catalog_version,
            "structured_requirements": [
                {
                    "metric_id": "demand.forecast_7d",
                    "dimensions": ["sku_id", "not_a_dimension"],
                    "aggregation": "sum",
                    "time_window": {"horizon_days": 7},
                    "rationale": "Use the approved seven-day forecast.",
                },
                {
                    "metric_id": "forecast.backtested_mape",
                    "rationale": "Requested by the user but not in the catalog.",
                },
            ],
            "semantic_requirements": [
                {
                    "query": "forecast accuracy methodology",
                    "retrieval_domain": "business_rule",
                    "required": False,
                }
            ],
        }

    planner = AdaptiveQueryPlanner(runner=runner)
    plan = planner.plan(
        FORECAST_QUERY,
        conversation_context=[f"context-{index}" for index in range(10)],
        agent_context="retail.retail",
        catalog_limit=3,
    )
    planner_input = observed["input"]
    assert len(planner_input.conversation_context) == 6
    assert len(planner_input.catalog.tables) <= 3
    assert plan.structured_requirements[0].availability == "AVAILABLE"
    assert plan.structured_requirements[0].dimensions == ["sku_id"]
    assert plan.structured_requirements[0].time_window is None
    assert plan.structured_requirements[1].availability == "UNAVAILABLE"
    assert "not in the approved query catalog" in plan.structured_requirements[1].unavailable_reason
    assert any("forecast.backtested_mape" in item for item in plan.unavailable_requirements)
    assert plan.catalog_version == CATALOG.catalog_version


def test_planner_runner_validation_failure_is_explicit():
    planner = AdaptiveQueryPlanner(runner=lambda _: {"request": "bad"})
    with pytest.raises(PlannerValidationError):
        planner.plan("Forecast demand")


def test_planner_timeout_is_one_bounded_attempt_and_is_categorized():
    calls = 0

    def timeout_runner(_):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("bounded planner timeout")

    planner = AdaptiveQueryPlanner(runner=timeout_runner)
    with pytest.raises(httpx.ReadTimeout):
        planner.plan("Forecast demand")
    assert calls == 1
    assert planner.last_failure_category == "timeout"


def test_query_plan_keeps_typed_validation_after_narrow_model_normalization():
    plan = QueryPlan.model_validate(
        {
            "request": "Explain inventory risk",
            "catalog_version": CATALOG.catalog_version,
            "structured_requirements": [
                {
                    "metric_id": "inventory.days_of_supply",
                    "dimensions": None,
                    "filters": None,
                }
            ],
            "semantic_requirements": [
                {
                    "query": "inventory risk rule",
                    "retrieval_domain": "documentation",
                    "doc_type": "formula",
                }
            ],
            "dependencies": None,
            "unavailable_requirements": None,
        }
    )
    assert plan.structured_requirements[0].dimensions == []
    assert plan.structured_requirements[0].filters == []
    assert plan.semantic_requirements[0].retrieval_domain == "business_rule"
    assert plan.dependencies == []
    with pytest.raises(ValidationError):
        QueryPlan.model_validate(
            {
                "request": "bad",
                "catalog_version": CATALOG.catalog_version,
                "structured_requirements": [
                    {"metric_id": "inventory.days_of_supply", "filters": "not-an-array"}
                ],
            }
        )


def _plan(*requirements, semantic_requirements=None, dependencies=None):
    return QueryPlan(
        request="Forecast demand safely",
        catalog_version=CATALOG.catalog_version,
        structured_requirements=list(requirements),
        semantic_requirements=semantic_requirements or [],
        dependencies=dependencies or [],
    )


def test_policy_rejects_unapproved_fields_filters_joins_and_broad_time_windows():
    base = StructuredRequirement(metric_id="sales.monthly_amount", aggregation="sum")
    with pytest.raises(QueryPolicyError, match="Filter field"):
        QueryPolicy().validate(
            _plan(StructuredRequirement(metric_id="sales.monthly_amount", aggregation="sum", filters=[QueryFilter(field="not_a_column", operator="eq", value="x")]))
        )
    with pytest.raises(QueryPolicyError, match="dependencies"):
        QueryPolicy().validate(_plan(base, dependencies=["a", "b", "c"]))
    with pytest.raises(QueryPolicyError, match="bounded date"):
        QueryPolicy().validate(_plan(StructuredRequirement(
            metric_id="promotion.expected_uplift_pct", aggregation="avg",
            time_window=TimeWindow(start="2020-01-01", end="2022-01-01"),
        )))


def test_policy_rejects_injection_and_unbounded_filter_cardinality():
    with pytest.raises(ValidationError, match="SQL"):
        _plan(StructuredRequirement(
                metric_id="inventory.inventory_position",
                filters=[{"field": "sku_id", "operator": "eq", "value": "GRC-001' OR 1=1 --"}],
            ))
    with pytest.raises(QueryPolicyError, match="limited"):
        QueryPolicy().validate(
            _plan(StructuredRequirement(
                metric_id="inventory.inventory_position",
                filters=[{"field": "sku_id", "operator": "in", "value": [str(i) for i in range(51)]}],
            ))
        )


def test_policy_enforces_authorization_scope_and_compiler_parameterizes_values():
    requirement = StructuredRequirement(
        metric_id="sales.monthly_amount",
        aggregation="sum",
        dimensions=["legal_entity_id"],
        filters=[{"field": "legal_entity_id", "operator": "eq", "value": "GRC"}],
    )
    with pytest.raises(QueryPolicyError, match="escapes"):
        QueryPolicy().validate(_plan(requirement), principal=PrincipalContext("p", True, ("ELC",)))

    validated = QueryPolicy().validate(
        _plan(StructuredRequirement(metric_id="sales.monthly_amount", aggregation="sum", dimensions=["legal_entity_id"])),
        principal=PrincipalContext("p", True, ("GRC", "ELC")),
    )
    compiled = DeterministicSqlCompiler().compile(validated.queries[0])
    assert "SELECT *" not in compiled.sql.upper()
    assert "[retail].[MonthlySales]" in compiled.sql
    assert "GRC" not in compiled.sql
    assert compiled.params[0] == 50
    assert "GRC" in compiled.params and "ELC" in compiled.params
    assert "ORDER BY [legal_entity_id]" in compiled.sql


def test_compiler_emits_fixed_read_only_parameterized_sql_for_aggregate_and_row_queries():
    aggregate = QueryPolicy().validate(_plan(StructuredRequirement(
        metric_id="demand.forecast_7d", aggregation="sum", dimensions=["sku_id"],
        filters=[{"field": "sku_id", "operator": "contains", "value": "GRC%_001"}],
    ))).queries[0]
    compiled = DeterministicSqlCompiler().compile(aggregate)
    assert compiled.sql.startswith("SELECT TOP (?)")
    assert "SUM([forecast_7d]) AS [metric_value]" in compiled.sql
    assert "GROUP BY [sku_id]" in compiled.sql
    assert "GRC" not in compiled.sql
    assert compiled.params == (50, "%GRC\\%\\_001%")

    row = QueryPolicy().validate(_plan(StructuredRequirement(
        metric_id="inventory.inventory_position", filters=[{"field": "sku_id", "operator": "eq", "value": "GRC-001"}],
    ))).queries[0]
    row_sql = DeterministicSqlCompiler().compile(row)
    assert "FROM [retail].[InventorySnapshot]" in row_sql.sql
    assert "source_load_id" in row_sql.sql
    assert row_sql.params == (50, "GRC-001")
    assert "ORDER BY [sku_id]" in row_sql.sql

    with pytest.raises(ValueError, match="filter"):
        DeterministicSqlCompiler().compile(
            row.model_copy(update={
                "filters": [QueryFilter(field="loaded_at", operator="eq", value="2026-01-01")]
            })
        )
    with pytest.raises(ValueError, match="time field"):
        DeterministicSqlCompiler().compile(
            row.model_copy(update={"time_field": "user_supplied_column"})
        )


def test_policy_does_not_execute_an_unsupported_forecast_horizon():
    with pytest.raises(QueryPolicyError, match="exactly a seven-day"):
        QueryPolicy().validate(_plan(StructuredRequirement(
            metric_id="demand.forecast_7d",
            aggregation="sum",
            time_window=TimeWindow(horizon_days=14),
        )))


class _AdaptiveCursor:
    description = [("sku_id",), ("metric_value",), ("source_load_id",), ("source_sheet",), ("source_row",), ("loaded_at",)]

    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchall(self):
        return [("GRC-001", 42, 7, "Sheet", 6, "2026-08-13T00:00:00")]


class _AdaptiveConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def close(self):
        self.closed = True


def test_orchestrator_executes_sql_and_vector_concurrently_and_preserves_evidence():
    import threading

    started = []
    barrier = threading.Barrier(2)
    cursor = _AdaptiveCursor()
    connection = _AdaptiveConnection(cursor)
    plan = _plan(
        StructuredRequirement(metric_id="inventory.inventory_position"),
        semantic_requirements=[SemanticRequirement(query="inventory methodology", required=True)],
    )

    def structured(compiled):
        started.append("sql")
        barrier.wait(timeout=2)
        return AdaptiveRetrievalOrchestrator(connection_factory=lambda: connection)._execute_sql(compiled)

    def semantic(requirement, request, principal):
        started.append("vector")
        barrier.wait(timeout=2)
        citation = SourceReference(citation_id="semantic:test", source_kind="semantic", doc_key="doc", chunk_key="doc#0")
        result = SemanticResult(
            rank=1, cosine_distance=0.1, cosine_similarity=0.9, doc_key="doc", doc_type="terminology",
            retrieval_domain="business_rule", source_sheet="Glossary", source_key="inventory",
            matched_chunk_index=0, matched_chunk_key="doc#0", excerpt="Inventory context", citation_id="semantic:test",
        )
        return RetrievalResponse(
            request_id="vector", status=RetrievalStatus.COMPLETE, route=SelectedRoute.VECTOR,
            routing=RoutingDecision(selected_route=SelectedRoute.VECTOR, confidence=RoutingConfidence.HIGH, recognized_intent="vector"),
            semantic_results=[result], citations=[citation],
        )

    orchestrator = AdaptiveRetrievalOrchestrator(structured_executor=structured, semantic_executor=semantic, max_workers=2)
    response = orchestrator.execute_plan(RetrievalRequest(query="x"), plan, principal=cli_principal())
    assert set(started) == {"sql", "vector"}
    assert response.status == RetrievalStatus.COMPLETE
    assert response.result_counts.structured == 1
    assert response.result_counts.semantic == 1
    assert response.structured_results[0].data["inventory.inventory_position"] == 42
    assert {citation.source_kind for citation in response.citations} == {"sql", "semantic"}


def test_orchestrator_returns_partial_when_exact_requirement_is_unavailable():
    plan = _plan(
        StructuredRequirement(metric_id="inventory.inventory_position"),
        StructuredRequirement(
            metric_id="forecast.backtested_mape",
            availability="UNAVAILABLE",
            unavailable_reason="No approved historical forecast-error metric exists.",
            required=True,
        ),
    )
    calls = []
    orchestrator = AdaptiveRetrievalOrchestrator(
        structured_executor=lambda compiled: calls.append(compiled) or (
            [StructuredResult(capability_key="adaptive.inventory.inventory_position", row_index=1, data={"inventory.inventory_position": 42}, citation_ids=["sql:valid"])],
            [SourceReference(citation_id="sql:valid", source_kind="sql", schema_name="retail")],
        ),
    )
    response = orchestrator.execute_plan(RetrievalRequest(query="x"), plan, principal=cli_principal())
    assert len(calls) == 1
    assert response.status == RetrievalStatus.PARTIAL
    assert response.errors[0].code == "REQUIRED_EVIDENCE_UNAVAILABLE"


def test_optional_unavailable_and_failed_evidence_do_not_make_valid_result_partial():
    plan = _plan(
        StructuredRequirement(metric_id="inventory.inventory_position"),
        StructuredRequirement(
            metric_id="forecast.optional_metric",
            availability="UNAVAILABLE",
            unavailable_reason="Optional metric is not available.",
            required=False,
        ),
        semantic_requirements=[
            SemanticRequirement(query="optional methodology", required=False)
        ],
    )

    def optional_failure(*_):
        raise RuntimeError("optional vector is unavailable")

    orchestrator = AdaptiveRetrievalOrchestrator(
        structured_executor=lambda compiled: (
            [StructuredResult(
                capability_key="adaptive.inventory.inventory_position",
                row_index=1,
                data={"inventory.inventory_position": 42},
                citation_ids=["sql:valid"],
            )],
            [SourceReference(citation_id="sql:valid", source_kind="sql", schema_name="retail")],
        ),
        semantic_executor=optional_failure,
    )
    response = orchestrator.execute_plan(
        RetrievalRequest(query="x"), plan, principal=cli_principal()
    )
    assert response.status == RetrievalStatus.COMPLETE
    assert not response.errors
    assert [item.code for item in response.warnings] == ["ADAPTIVE_VECTOR_BRANCH_FAILED"]


def test_orchestrator_policy_rejection_never_calls_sql_or_vector():
    plan = _plan(StructuredRequirement(
        metric_id="inventory.inventory_position",
        filters=[{"field": "not_approved", "operator": "eq", "value": "x"}],
    ))
    called = []
    orchestrator = AdaptiveRetrievalOrchestrator(
        structured_executor=lambda _: called.append("sql"),
        semantic_executor=lambda *_: called.append("vector"),
    )
    response = orchestrator.execute_plan(RetrievalRequest(query="x"), plan, principal=cli_principal())
    assert response.status == RetrievalStatus.FAILED
    assert response.errors[0].code == "QUERY_POLICY_REJECTED"
    assert called == []


def test_orchestrator_authorization_denial_never_plans_or_executes():
    called = []

    class Planner:
        def plan(self, *_args, **_kwargs):
            called.append("planner")
            return _plan(StructuredRequirement(metric_id="inventory.inventory_position"))

    orchestrator = AdaptiveRetrievalOrchestrator(
        planner=Planner(),
        structured_executor=lambda _: called.append("sql"),
        semantic_executor=lambda *_: called.append("vector"),
    )
    response = orchestrator.retrieve(
        RetrievalRequest(query="inventory analysis"),
        principal=PrincipalContext("external", False),
    )
    assert response.status == RetrievalStatus.FAILED
    assert response.errors[0].code == "AUTHORIZATION_DENIED"
    assert called == []


def test_scoped_adaptive_principal_cannot_run_unscoped_semantic_branch():
    plan = _plan(
        StructuredRequirement(metric_id="inventory.inventory_position"),
        semantic_requirements=[
            SemanticRequirement(query="inventory methodology", required=False)
        ],
    )
    called = []
    orchestrator = AdaptiveRetrievalOrchestrator(
        structured_executor=lambda _: called.append("sql"),
        semantic_executor=lambda *_: called.append("vector"),
    )
    response = orchestrator.execute_plan(
        RetrievalRequest(query="scoped inventory analysis"),
        plan,
        principal=PrincipalContext("scoped", True, ("GRC",)),
    )
    assert response.status == RetrievalStatus.FAILED
    assert response.errors[0].code == "QUERY_POLICY_REJECTED"
    assert called == []


def test_orchestrator_retrieve_runs_one_injected_planning_pass_before_branches():
    calls = []

    class Planner:
        def plan(self, request, **kwargs):
            calls.append((request, kwargs))
            return _plan(StructuredRequirement(metric_id="inventory.inventory_position"))

    orchestrator = AdaptiveRetrievalOrchestrator(
        planner=Planner(),
        structured_executor=lambda compiled: ([], []),
    )
    response = orchestrator.retrieve(RetrievalRequest(query="unseen inventory analysis"), principal=cli_principal())
    assert response.status == RetrievalStatus.FAILED
    assert len(calls) == 1
    assert calls[0][0] == "unseen inventory analysis"
