from __future__ import annotations

import io
import asyncio
import time
from types import SimpleNamespace

from scripts.adaptive_retrieval_demo import (
    ConsoleTrace,
    build_demo_stack,
    print_result,
    run_demo,
)
from src.retrieval.models import (
    Diagnostic,
    RetrievalResponse,
    RetrievalStatus,
    RoutingConfidence,
    RoutingDecision,
    SelectedRoute,
    SemanticResult,
    SourceReference,
    StructuredResult,
)
from src.retrieval.observability import RetrievalTraceEvent


def _response(status: RetrievalStatus = RetrievalStatus.COMPLETE) -> RetrievalResponse:
    citation = SourceReference(
        citation_id="sql:demo",
        source_kind="sql",
        schema_name="retail",
        tables=["InventorySnapshot"],
    )
    return RetrievalResponse(
        request_id="demo-request",
        status=status,
        route=SelectedRoute.SQL,
        routing=RoutingDecision(
            selected_route=SelectedRoute.SQL,
            confidence=RoutingConfidence.HIGH,
            recognized_intent="inventory_current",
            selected_sql_capabilities=["sku.inventory_current"],
        ),
        structured_results=[
            StructuredResult(
                capability_key="sku.inventory_current",
                row_index=1,
                data={"inventory_position": 42},
                citation_ids=[citation.citation_id],
            )
        ],
        citations=[citation],
        errors=(
            [
                Diagnostic(
                    code="REQUIRED_EVIDENCE_UNAVAILABLE",
                    message="forecast.backtested_mape is not approved",
                )
            ]
            if status == RetrievalStatus.PARTIAL
            else []
        ),
    )


def test_demo_stack_shares_one_service_between_gateway_and_adaptive_vector_path() -> None:
    gateway, service = build_demo_stack(lambda _event: None)

    assert gateway.fast_service is service
    assert gateway.adaptive_orchestrator.semantic_service is service
    assert gateway.adaptive_orchestrator.planner is not None


def test_console_trace_classifies_real_route_event_shapes() -> None:
    stream = io.StringIO()
    trace = ConsoleTrace(stream=stream)
    for route in ("SQL", "VECTOR", "HYBRID"):
        trace(
            RetrievalTraceEvent(
                name="router.decision",
                data={"route": route, "capabilities": []},
            )
        )
    trace(
        RetrievalTraceEvent(
            name="router.decision",
            data={"route": "PLANNER_REQUIRED", "capabilities": []},
        )
    )
    trace(RetrievalTraceEvent(name="gateway.adaptive_escalation", data={}))
    output = stream.getvalue()
    assert "Route selected: SQL" in output
    assert "Route selected: VECTOR" in output
    assert "Route selected: HYBRID" in output
    assert "Route selected: PLANNER_REQUIRED" in output
    assert "Escalating -> ADAPTIVE PLANNER" in output


def test_partial_result_displays_actual_missing_evidence() -> None:
    stream = io.StringIO()
    trace = ConsoleTrace(stream=stream)
    trace(
        RetrievalTraceEvent(
            name="planner.requirements",
            data={
                "structured": [
                    {"metric_id": "forecast.backtested_mape", "availability": "UNAVAILABLE"}
                ],
                "semantic": [],
                "top_k": 5,
            },
        )
    )
    print_result(_response(RetrievalStatus.PARTIAL), trace, stream=stream)
    output = stream.getvalue()
    assert "Status: PARTIAL" in output
    assert "forecast.backtested_mape" in output
    assert "inventory_position = 42" in output


def test_verbose_sql_trace_does_not_print_parameter_values_or_credentials() -> None:
    stream = io.StringIO()
    trace = ConsoleTrace(stream=stream, verbose=True)
    trace(
        RetrievalTraceEvent(
            name="compiler.query",
            data={
                "metric_id": "inventory.inventory_position",
                "source": "retail.InventorySnapshot",
                "parameter_count": 1,
                "result_fields": ["metric_value"],
                "params": ("password=do-not-print",),
                "sql_shape": "SELECT [metric] FROM [retail].[InventorySnapshot] WHERE [sku_id] = ?",
            },
        )
    )
    output = stream.getvalue()
    assert "password=do-not-print" not in output
    assert "Parameterized SQL shape" in output
    assert "1 value(s) redacted" in output


def test_planner_failure_trace_is_safe_and_has_category() -> None:
    stream = io.StringIO()
    trace = ConsoleTrace(stream=stream)
    trace(
        RetrievalTraceEvent(
            name="planner.request_started",
            data={
                "deployment": "gpt-5-mini",
                "timeout_seconds": 15,
                "max_retries": 0,
                "output_mode": "strict_tool",
            },
        )
    )
    trace(
        RetrievalTraceEvent(
            name="planner.failed",
            data={"failure_category": "timeout", "exception_type": "ReadTimeout"},
            elapsed_ms=7001.0,
        )
    )
    output = stream.getvalue()
    assert "Sending bounded Azure OpenAI planning request" in output
    assert "Failure category: timeout" in output
    assert "api-key" not in output.casefold()
    assert "password" not in output.casefold()


def test_gateway_wall_clock_includes_adaptive_planner_wait() -> None:
    response = _response()

    class Fast:
        def retrieve(self, request, *, principal):
            return response.model_copy(update={"route": SelectedRoute.PLANNER_REQUIRED})

    class Adaptive:
        def retrieve(self, *args, **kwargs):
            time.sleep(0.02)
            return response.model_copy(update={"route": SelectedRoute.PLANNER_REQUIRED})

    from src.retrieval.gateway import ChatRetrievalGateway

    result = ChatRetrievalGateway(fast_service=Fast(), adaptive_orchestrator=Adaptive()).retrieve(
        "Compare current inventory and forecast demand by SKU."
    )
    assert result.timing.gateway_ms >= 20


def test_azure_planner_factory_is_native_and_bounded() -> None:
    from src.llm import model_provider

    assert type(model_provider.client).__name__ == "AsyncAzureOpenAI"
    planner_model = model_provider.create_planner_model(timeout_seconds=7)
    planner_client = planner_model.provider.client
    try:
        assert type(planner_client).__name__ == "AsyncAzureOpenAI"
        assert planner_client.max_retries == 0
        assert planner_client.timeout.read == 7
    finally:
        asyncio.run(planner_client.close())


def test_cli_toggles_do_not_change_retrieval_behavior(monkeypatch) -> None:
    calls: list[str] = []
    response = _response()

    class FakeGateway:
        def retrieve(self, query, **kwargs):
            calls.append(query)
            return response

    class FakeService:
        def embedding_config(self):
            return SimpleNamespace(model_name="BAAI/bge-small-en-v1.5")

        def warm_embedding_provider(self):
            return None

    monkeypatch.setattr(
        "scripts.adaptive_retrieval_demo.build_demo_stack",
        lambda trace: (FakeGateway(), FakeService()),
    )
    monkeypatch.setattr(
        "scripts.adaptive_retrieval_demo.load_azure_sql_connection_string",
        lambda: "configured-but-never-printed",
    )
    values = iter(("/timings", "/verbose", "/json", "What is inventory?", "/quit"))
    stream = io.StringIO()
    assert run_demo(input_fn=lambda _prompt: next(values), stream=stream) == 0
    assert calls == ["What is inventory?"]
    assert "Raw RetrievalResponse JSON" in stream.getvalue()


def test_cli_handles_interrupt_and_eof_without_retrieval(monkeypatch) -> None:
    class FakeGateway:
        def retrieve(self, query, **kwargs):
            raise AssertionError("no retrieval expected")

    class FakeService:
        def embedding_config(self):
            return SimpleNamespace(model_name="BAAI/bge-small-en-v1.5")

        def warm_embedding_provider(self):
            return None

    monkeypatch.setattr(
        "scripts.adaptive_retrieval_demo.build_demo_stack",
        lambda trace: (FakeGateway(), FakeService()),
    )
    monkeypatch.setattr(
        "scripts.adaptive_retrieval_demo.load_azure_sql_connection_string",
        lambda: "configured",
    )
    attempts = iter((KeyboardInterrupt(), EOFError()))

    def interrupted_input(_prompt):
        error = next(attempts)
        raise error

    stream = io.StringIO()
    assert run_demo(input_fn=interrupted_input, stream=stream) == 0
    assert "returning to the prompt" in stream.getvalue()
    assert "Goodbye." in stream.getvalue()
