"""Interactive developer console for the production adaptive Retail gateway.

Run from ``backend/`` with:

    python scripts/adaptive_retrieval_demo.py

The script intentionally contains no retrieval logic.  It constructs one
``RetrievalService`` and one ``ChatRetrievalGateway``, warms that service's
existing local BGE provider, and presents structured runtime events/results.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

# ``python scripts/...`` puts ``backend/scripts`` on sys.path.  Add the
# backend directory so the normal ``src`` package imports work without asking
# the demo user to set PYTHONPATH.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retail_data_bootstrap.paths import load_azure_sql_connection_string
from src.retrieval.gateway import ChatRetrievalGateway
from src.retrieval.models import RetrievalResponse
from src.retrieval.observability import RetrievalTraceEvent, TraceSink
from src.retrieval.orchestrator import AdaptiveRetrievalOrchestrator
from src.retrieval.planner import AdaptiveQueryPlanner
from src.retrieval.service import RetrievalService


BANNER = """============================================================
AI Retail 360 — Adaptive Retrieval Demo
============================================================"""


def _safe_text(value: Any, *, limit: int = 220) -> str:
    """Keep document/error text readable and strip terminal control escapes."""
    text = " ".join(str(value).split()).replace("\x1b", "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _display_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.6g}"
    if isinstance(value, int):
        return f"{value:,}"
    return _safe_text(value, limit=180)


@dataclass
class ConsoleTrace:
    """Human-readable subscriber for real retrieval trace events."""

    stream: TextIO = field(default_factory=lambda: sys.stdout)
    timings: bool = False
    verbose: bool = False
    unavailable: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.unavailable.clear()

    def _write(self, line: str = "") -> None:
        print(line, file=self.stream, flush=True)

    def __call__(self, event: RetrievalTraceEvent) -> None:
        name = event.name
        data = event.data

        if name == "router.analysis_started":
            self._write("\n[ROUTER] Analyzing query...")
        elif name == "router.decision":
            route = str(data.get("route", "UNKNOWN"))
            if route == "PLANNER_REQUIRED":
                self._write("[ROUTER] Complex / unsupported-by-fixed-capability query")
            else:
                self._write("[ROUTER] Simple query -> FAST PATH")
            self._write(f"[ROUTER] Route selected: {route}")
            capabilities = data.get("capabilities") or []
            if capabilities:
                self._write(f"[ROUTER] Capability: {', '.join(map(str, capabilities))}")
            domain = data.get("vector_domain")
            doc_type = data.get("vector_doc_type")
            if domain or doc_type:
                self._write(
                    "[ROUTER] Semantic filters: "
                    f"domain={domain or 'any'}, doc_type={doc_type or 'any'}"
                )
        elif name == "gateway.adaptive_escalation":
            self._write("[ROUTER] Escalating -> ADAPTIVE PLANNER")
        elif name == "gateway.fallback_started":
            self._write("[GATEWAY] Switching to bounded deterministic fallback")
        elif name == "gateway.acceptance_fallback":
            if self.verbose or self.timings:
                self._write(f"[GATEWAY] Fallback retrieval completed in {_ms(event.elapsed_ms)}")
        elif name == "sql.started":
            self._write("\n[SQL] Executing structured retrieval")
            for source in data.get("sources") or []:
                capability = source.get("capability", "unknown")
                intent = source.get("intent", "approved capability")
                tables = ", ".join(source.get("source_tables") or [])
                self._write(f"[SQL] Capability: {capability} — {intent}")
                if tables:
                    self._write(f"[SQL] Source: {tables}")
        elif name == "sql.completed":
            self._write(f"[SQL] Completed in {_ms(data.get('elapsed_ms'))}")
            self._write(f"[SQL] Rows returned: {data.get('row_count', 0)}")
            self._show_error_codes(data)
        elif name == "vector.started":
            cached = bool(data.get("cached"))
            action = "Using cached embedding model" if cached else "Creating query embedding"
            self._write(f"\n[VECTOR] {action}")
            self._write("[VECTOR] Searching semantic business-rule evidence")
            self._write(f"[VECTOR] Top-K: {data.get('top_k', '?')}")
            if self.verbose:
                self._write(
                    "[VECTOR] Profile: "
                    f"{data.get('provider_key', 'unknown')} / {data.get('model_name', 'unknown')}"
                )
                self._write(
                    "[VECTOR] Filters: "
                    f"domain={data.get('retrieval_domain') or 'any'}, "
                    f"doc_type={data.get('doc_type') or 'any'}"
                )
        elif name == "vector.completed":
            self._write(f"[VECTOR] Completed in {_ms(data.get('elapsed_ms'))}")
            if self.timings:
                self._write(
                    "[VECTOR] Timing: "
                    f"embedding={_ms(data.get('query_embedding_ms'))}, "
                    f"VECTOR_DISTANCE/search={_ms(data.get('vector_distance_ms'))}/"
                    f"{_ms(data.get('vector_search_ms'))}"
                )
            self._write(f"[VECTOR] Results returned: {data.get('result_count', 0)}")
            self._show_error_codes(data)
        elif name == "catalog.retrieved":
            self._write("\n[CATALOG] Retrieving relevant schema / metric context")
            if self.verbose:
                self._write(
                    f"[CATALOG] Metrics: {', '.join(data.get('metrics') or []) or 'none'}"
                )
                self._write(
                    f"[CATALOG] Tables: {', '.join(data.get('tables') or []) or 'none'}"
                )
                unavailable = data.get("unavailable") or []
                if unavailable:
                    self._write(f"[CATALOG] Known unavailable: {', '.join(unavailable)}")
        elif name == "planner.started":
            self._write("[PLANNER] Planning required evidence...")
        elif name == "planner.request_started":
            self._write("[PLANNER] Sending bounded Azure OpenAI planning request...")
            self._write(f"[PLANNER] Deployment: {_safe_text(data.get('deployment') or 'configured deployment')}")
            if self.verbose:
                self._write(
                    "[PLANNER] Mode: "
                    f"{data.get('output_mode', 'strict_tool')}; "
                    f"timeout={data.get('timeout_seconds', '?')} sec; "
                    f"max_retries={data.get('max_retries', '?')}"
                )
        elif name == "planner.model_completed":
            self._write(f"[PLANNER] Completed in {_ms(event.elapsed_ms)}")
        elif name == "planner.validation_completed":
            self._write(
                f"[PLANNER] Structured requirements: {data.get('structured_count', 0)}"
            )
            self._write(
                f"[PLANNER] Semantic requirements: {data.get('semantic_count', 0)}"
            )
        elif name == "planner.failed":
            self._write(f"[PLANNER] Azure planner failed after {_ms(event.elapsed_ms)}")
            self._write(
                f"[PLANNER] Failure category: {data.get('failure_category', 'unknown')}"
            )
        elif name == "planner.requirements":
            structured = data.get("structured") or []
            semantic = data.get("semantic") or []
            self._write(
                "[PLANNER] Structured requirements: "
                + (
                    ", ".join(
                        f"{item.get('metric_id')}"
                        f" ({item.get('availability', 'AVAILABLE')})"
                        for item in structured
                    )
                    or "none"
                )
            )
            self._write(
                "[PLANNER] Semantic requirements: "
                + (
                    ", ".join(
                        f"domain={item.get('retrieval_domain') or 'any'}, "
                        f"doc_type={item.get('doc_type') or 'any'}, "
                        f"top_k={data.get('top_k')}"
                        for item in semantic
                    )
                    or "none"
                )
            )
            for item in structured:
                if item.get("availability") == "UNAVAILABLE" and item.get("required", True):
                    metric_id = str(item.get("metric_id"))
                    if metric_id not in self.unavailable:
                        self.unavailable.append(metric_id)
        elif name == "policy.started":
            self._write("\n[POLICY] Validating query plan...")
        elif name == "policy.approved":
            self._write("[POLICY] Approved")
            if self.verbose:
                self._write(
                    "[POLICY] Metrics: "
                    f"{', '.join(data.get('metric_ids') or []) or 'none'}"
                )
                self._write(
                    "[POLICY] Sources: "
                    f"{', '.join(data.get('sources') or []) or 'none'}"
                )
        elif name == "policy.rejected":
            self._write(f"[POLICY] Rejected: {_safe_text(data.get('reason'))}")
        elif name == "compiler.started":
            self._write("\n[COMPILER] Building deterministic read-only SQL")
        elif name == "compiler.query":
            self._write(f"[COMPILER] Metric: {data.get('metric_id')}")
            self._write(f"[COMPILER] Source: {data.get('source')}")
            if self.verbose:
                self._write(
                    "[COMPILER] Parameterized SQL shape: "
                    f"{_safe_sql_shape(data.get('sql_shape'))}; "
                    f"{data.get('parameter_count', 0)} value(s) redacted"
                )
                self._write(f"[COMPILER] Fields: {', '.join(data.get('result_fields') or [])}")
        elif name == "compiler.approved":
            self._write("[COMPILER] Approved")
        elif name == "compiler.rejected":
            self._write(f"[COMPILER] Rejected: {_safe_text(data.get('reason'))}")
        elif name == "adaptive.sql.started":
            self._write(
                f"\n[SQL] Getting approved evidence for {data.get('metric_id')}"
            )
            self._write(f"[SQL] Source: {data.get('source')}")
        elif name == "adaptive.sql.completed":
            self._write(f"[SQL] Completed in {_ms(event.elapsed_ms)}")
            self._write(f"[SQL] Rows returned: {data.get('row_count', 0)}")
        elif name == "adaptive.vector.started":
            self._write(
                "\n[VECTOR] Searching planned semantic context "
                f"(domain={data.get('retrieval_domain') or 'any'}, "
                f"doc_type={data.get('doc_type') or 'any'}, top_k={data.get('top_k')})"
            )
        elif name == "evidence.aggregated":
            if data.get("structured_count") and data.get("semantic_count"):
                self._write("[ORCHESTRATOR] SQL and semantic evidence combined")
            if self.verbose or self.timings:
                self._write(
                    "[ORCHESTRATOR] Evidence combined: "
                    f"structured={data.get('structured_count', 0)}, "
                    f"semantic={data.get('semantic_count', 0)}, "
                    f"citations={data.get('citation_count', 0)}"
                )

    def _show_error_codes(self, data: dict[str, Any]) -> None:
        if self.verbose and data.get("error_codes"):
            self._write(f"[TRACE] Errors: {', '.join(data['error_codes'])}")


def _ms(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):,.1f} ms"


def _safe_sql_shape(value: Any) -> str:
    """Render only the compiler's parameterized shape, never bound values."""
    return _safe_text(value or "<shape unavailable>", limit=500)


def build_demo_stack(trace_sink: TraceSink) -> tuple[ChatRetrievalGateway, RetrievalService]:
    """Construct exactly one shared service/provider stack for the demo."""
    service = RetrievalService(trace_sink=trace_sink)
    planner = AdaptiveQueryPlanner(trace_sink=trace_sink)
    orchestrator = AdaptiveRetrievalOrchestrator(
        planner=planner,
        semantic_service=service,
        trace_sink=trace_sink,
    )
    gateway = ChatRetrievalGateway(
        fast_service=service,
        adaptive_orchestrator=orchestrator,
        trace_sink=trace_sink,
    )
    return gateway, service


def print_result(
    response: RetrievalResponse,
    trace: ConsoleTrace,
    *,
    stream: TextIO,
    show_json: bool = False,
    show_timings: bool = False,
) -> None:
    """Print bounded evidence, diagnostics, and actual response metadata."""
    print("\n[RESULT] Status: " + response.status.value, file=stream)
    print("Route: " + response.route.value, file=stream)

    if response.structured_results:
        print("\nStructured evidence:", file=stream)
        for result in response.structured_results[:12]:
            values = ", ".join(
                f"{key} = {_display_value(value)}"
                for key, value in result.data.items()
            )
            print(f"  {values or result.capability_key}", file=stream)

    if response.semantic_results:
        print("\nSemantic evidence:", file=stream)
        for result in response.semantic_results[:5]:
            print(
                f"  {result.rank}. {_safe_text(result.source_key)} — "
                f'"{_safe_text(result.excerpt, limit=180)}"',
                file=stream,
            )
            print(f"     similarity: {result.cosine_similarity:.4f}", file=stream)

    missing = list(dict.fromkeys(trace.unavailable))
    missing_messages = [
        item.message
        for item in response.errors
        if item.code == "REQUIRED_EVIDENCE_UNAVAILABLE"
    ]
    if missing or missing_messages:
        print("\nMissing required evidence:", file=stream)
        for item in missing or missing_messages:
            print(f"  - {_safe_text(item)}", file=stream)

    if response.warnings and show_timings:
        print("\nWarnings:", file=stream)
        for item in response.warnings[:8]:
            print(f"  - {item.code}: {_safe_text(item.message)}", file=stream)
    if response.errors and not missing_messages:
        print("\nDiagnostics:", file=stream)
        for item in response.errors[:8]:
            print(f"  - {item.code}: {_safe_text(item.message)}", file=stream)

    gateway_ms = response.timing.gateway_ms or response.timing.total_ms
    print(f"\nTotal gateway wall-clock time: {_ms(gateway_ms)}", file=stream)
    if show_timings:
        print("Timing breakdown:", file=stream)
        for label, value in (
            ("gateway wall-clock", response.timing.gateway_ms),
            ("routing", response.timing.routing_ms),
            ("catalog", response.timing.catalog_ms),
            ("planning", response.timing.planning_ms),
            ("planner model", response.timing.planner_model_ms),
            ("planner validation", response.timing.planner_validation_ms),
            ("fallback decision", response.timing.fallback_decision_ms),
            ("fallback + retrieval", response.timing.fallback_ms),
            ("policy", response.timing.policy_ms),
            ("compilation", response.timing.compilation_ms),
            ("SQL", response.timing.sql_ms),
            ("query embedding", response.timing.query_embedding_ms),
            ("VECTOR_DISTANCE", response.timing.vector_distance_ms),
            ("vector search", response.timing.vector_search_ms),
            ("semantic/vector total", response.timing.vector_total_ms),
            ("evidence aggregation", response.timing.evidence_aggregation_ms),
        ):
            if value:
                print(f"  {label}: {_ms(value)}", file=stream)

    if show_json:
        print("\nRaw RetrievalResponse JSON:", file=stream)
        print(
            json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2),
            file=stream,
        )


def print_help(stream: TextIO = sys.stdout) -> None:
    print(
        """Commands:
  /help       Show commands and suggested demo questions
  /quit       Exit the demo (also /exit)
  /timings    Toggle detailed timing output
  /verbose    Toggle catalog/compiler/trace detail
  /json       Toggle full RetrievalResponse JSON after each result
  /clear      Clear the console

Suggested demo questions:
  1. What is the current inventory position for GRC-001?
  2. What does Days of Supply mean?
  3. Why is GRC-001 at replenishment risk?
  4. Forecast demand for the next 7 days, including forecast basket and
     forecast accuracy using backtested MAPE.
  5. Analyze current inventory risk by SKU and compare at-risk value with
     days of supply.
  6. Analyze workforce coverage gaps by store and explain the staffing
     coverage methodology.""",
        file=stream,
    )


def run_demo(*, input_fn=input, stream: TextIO = sys.stdout) -> int:
    trace = ConsoleTrace(stream=stream)
    gateway, service = build_demo_stack(trace)

    print(BANNER, file=stream)
    print("\nInitializing retrieval gateway...", file=stream, flush=True)
    config = service.embedding_config()
    print(f"Loading local embedding model {config.model_name}...", file=stream, flush=True)
    started = time.perf_counter()
    try:
        service.warm_embedding_provider()
    except Exception as error:
        print(f"[STARTUP] BGE warm-up failed: {_safe_text(error)}", file=stream)
        return 1
    print(f"[STARTUP] BGE model ready in {_ms((time.perf_counter() - started) * 1000)}", file=stream)

    try:
        load_azure_sql_connection_string()
    except Exception as error:
        print(f"[STARTUP] Azure SQL configuration unavailable: {_safe_text(error)}", file=stream)
        return 1
    print("Azure SQL configuration ready.", file=stream)
    print("Adaptive planner ready.", file=stream)
    print("\nType a Retail question.", file=stream)
    print("Commands: /help, /quit", file=stream)

    show_json = False
    while True:
        try:
            value = input_fn("retail> ")
        except KeyboardInterrupt:
            print("\nInterrupted; returning to the prompt.", file=stream)
            continue
        except EOFError:
            print("\nGoodbye.", file=stream)
            return 0

        query = str(value).strip()
        if not query:
            continue
        command = query.casefold()
        if command in {"/quit", "/exit"}:
            print("Goodbye.", file=stream)
            return 0
        if command == "/help":
            print_help(stream)
            continue
        if command == "/timings":
            trace.timings = not trace.timings
            print(f"Detailed timings {'on' if trace.timings else 'off'}.", file=stream)
            continue
        if command == "/verbose":
            trace.verbose = not trace.verbose
            print(f"Verbose trace {'on' if trace.verbose else 'off'}.", file=stream)
            continue
        if command == "/json":
            show_json = not show_json
            print(f"Raw JSON {'on' if show_json else 'off'}.", file=stream)
            continue
        if command == "/clear":
            print("\033[2J\033[H", end="", file=stream, flush=True)
            continue
        if query.startswith("/"):
            print("Unknown command. Use /help.", file=stream)
            continue

        trace.reset()
        try:
            response = gateway.retrieve(query, agent_context="retail.demo")
        except KeyboardInterrupt:
            print("\nInterrupted; returning to the prompt.", file=stream)
            continue
        except Exception as error:
            print(f"\n[RESULT] Retrieval failed: {_safe_text(error)}", file=stream)
            continue
        print_result(
            response,
            trace,
            stream=stream,
            show_json=show_json,
            show_timings=trace.timings,
        )


def main() -> int:
    return run_demo()


if __name__ == "__main__":
    raise SystemExit(main())
