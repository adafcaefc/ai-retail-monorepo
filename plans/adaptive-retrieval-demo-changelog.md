# Adaptive Retrieval Interactive Demo Changelog

## Purpose

The interactive demo provides a senior-engineer-friendly console for asking
arbitrary Retail questions repeatedly in one Python process. It makes the
existing Phase 6 fast paths, `PLANNER_REQUIRED` escalation, bounded adaptive
planning, deterministic policy/compiler boundary, SQL/vector execution, and
evidence status visible without creating a second retrieval implementation.

## Files Added

- `backend/scripts/__init__.py`
- `backend/scripts/adaptive_retrieval_demo.py`
- `backend/tests/test_adaptive_retrieval_demo.py`
- `backend/tests/test_azure_openai_planner_integration.py`
- `plans/adaptive-retrieval-demo-changelog.md`

## Files Modified

- `backend/src/retail_data_bootstrap/embedding_provider.py`
- `backend/src/retail_data_bootstrap/vector_store.py`
- `backend/src/llm/model_provider.py`
- `backend/src/retrieval/gateway.py`
- `backend/src/retrieval/models.py`
- `backend/src/retrieval/observability.py`
- `backend/src/retrieval/orchestrator.py`
- `backend/src/retrieval/planner.py`
- `backend/src/retrieval/routing.py`
- `backend/src/retrieval/service.py`
- `backend/pytest.ini`
- `backend/tests/test_adaptive_retrieval.py`
- `backend/tests/test_retrieval.py`
- `backend/tests/test_vector_embedding.py`

## Architecture

`adaptive_retrieval_demo.py` constructs one `RetrievalService`, one
`AdaptiveRetrievalOrchestrator`, and one `ChatRetrievalGateway`. The
orchestrator receives the same service as its semantic service, so fast-path
vector retrieval and adaptive semantic branches share the same provider cache
and vector lock. Every question calls the existing gateway; the CLI does not
route, plan, compile, query, or synthesize independently.

The optional `RetrievalTraceEvent` sink is silent unless a caller subscribes.
The demo subscribes and renders structured events from the real router,
catalog, planner, policy, compiler, gateway, service, and orchestrator. Normal
production logging is not replaced with demo-only print statements.

## Warm Model Lifecycle

`RetrievalService._configured_provider()` remains the single lazy construction
point for the configured embedding provider. `EmbeddingProvider.warm_up()` is
the small provider lifecycle hook; `LocalBgeEmbeddingProvider.warm_up()` calls
its existing `_load_model()` path, which loads and validates the local
`BAAI/bge-small-en-v1.5` SentenceTransformer with `local_files_only=True`.

At startup the demo obtains the service's configured profile, calls
`service.warm_embedding_provider()`, and does not perform a semantic search to
fake initialization. The exact provider object stays attached to the service
for the lifetime of the process. Subsequent vector trace events report
`cached=True` from that provider's loaded state. The regression tests cover
both one model factory call across repeated warm-ups and one provider factory
call across repeated retrievals.

Azure SQL connections are still opened and closed per retrieval branch. The
demo validates that the Azure SQL connection configuration exists at startup;
it does not hold a transaction or connection open indefinitely.

## Console Trace Events

The trace is powered by runtime metadata, not keyword-specific presentation
rules:

- `router.decision` supplies FAST PATH/route, confidence, reason codes,
  capabilities, and vector filters.
- `gateway.adaptive_escalation` supplies the real `PLANNER_REQUIRED` boundary.
- `planner.request_started`, `planner.model_completed`,
  `planner.validation_completed`, and `planner.failed` supply the bounded
  Azure deployment, strict output mode, failure category, and measured model
  and validation timings.
- `catalog.retrieved` supplies the bounded tables, metrics, unavailable catalog
  items, and catalog timing.
- `planner.requirements` supplies structured metric availability/aggregation/
  dimensions and semantic domain/doc-type/top-k context.
- `policy.approved` supplies validated metric sources, dimensions, filter
  fields, and semantic domains.
- `compiler.query` supplies the approved metric/source/result shape and the
  count of parameter values; parameter values are never emitted.
- `sql.*`, `vector.*`, and adaptive branch events supply actual source,
  capability, row count, model-cache state, embedding/search timings, and
  branch timings.
- `evidence.aggregated` and the final `RetrievalResponse` supply evidence
  counts, citations, COMPLETE/PARTIAL/FAILED status, diagnostics, and total
  timing. `gateway.completed` supplies the true wall-clock duration including
  planner wait and any fallback decision.

Adaptive semantic timing now propagates the existing service timings into the
orchestrator response. `vector_distance_ms` is measured around the
parameterized Azure SQL `VECTOR_DISTANCE` retrieval/ranking operation, while
`query_embedding_ms` measures the local provider call. `vector_search_ms`
continues to represent the post-embedding vector branch work, and
`vector_total_ms` represents the full semantic branch timing.

## CLI Commands

- `/help` — show commands and six suggested demo prompts.
- `/quit` and `/exit` — exit cleanly.
- `/timings` — toggle the detailed response timing breakdown.
- `/verbose` — toggle bounded catalog/compiler/trace details. It does not print
  SQL parameters or credentials.
- `/json` — toggle the full raw `RetrievalResponse` JSON after each result.
- `/clear` — clear the terminal using an ANSI screen-clear sequence.

Ctrl+C returns to the question prompt where possible. Ctrl+D exits with a
short goodbye message.

## Example Session

The following is illustrative output shape only; timings and values are not
fixed or fabricated by the demo.

```text
retail> What is the current inventory position for GRC-001?
[ROUTER] Simple query -> FAST PATH
[ROUTER] Route selected: SQL
[ROUTER] Capability: sku.inventory_current
[SQL] Executing structured retrieval
[SQL] Source: retail.Sku, retail.InventorySnapshot
[SQL] Completed in <measured time>
[SQL] Rows returned: <measured count>
[RESULT] Status: COMPLETE
Route: SQL
Structured evidence:
  inventory_position = <source value>

retail> What does Days of Supply mean?
[ROUTER] Simple query -> FAST PATH
[ROUTER] Route selected: VECTOR
[VECTOR] Using cached embedding model
[VECTOR] Searching semantic business-rule evidence
[VECTOR] Top-K: 5
[RESULT] Status: COMPLETE
Route: VECTOR
Semantic evidence:
  1. <source key> — "<bounded source excerpt>"
     similarity: <source score>

retail> Why is GRC-001 at replenishment risk?
[ROUTER] Simple query -> FAST PATH
[ROUTER] Route selected: HYBRID
[SQL] Executing structured retrieval
[VECTOR] Using cached embedding model
[ORCHESTRATOR] Evidence combined: <actual counts>
[RESULT] Status: COMPLETE
Route: HYBRID

retail> Forecast demand for the next 7 days, including forecast basket and forecast accuracy using backtested MAPE.
[ROUTER] Complex / unsupported-by-fixed-capability query
[ROUTER] Route selected: PLANNER_REQUIRED
[ROUTER] Escalating -> ADAPTIVE PLANNER
[CATALOG] Retrieving relevant schema / metric context
[PLANNER] Planning required evidence...
[POLICY] Validating query plan...
[POLICY] Approved
[COMPILER] Building deterministic read-only SQL
[SQL] Getting approved evidence for demand.forecast_7d
[VECTOR] Searching planned semantic context
[RESULT] Status: PARTIAL
Missing required evidence:
  - forecast.basket
  - forecast.backtested_mape
```

The final adaptive status, available forecast evidence, missing requirements,
and timings come from the live `RetrievalResponse`. The forecast basket and
backtested MAPE are not inferred when absent from the approved catalog.

## Safety

The demo uses `cli_principal()` only at the existing internal POC boundary;
this does not add product authorization. The planner returns a structured
`QueryPlan`, never executable SQL. `QueryPolicy` validates it and
`DeterministicSqlCompiler` creates the parameterized read-only SQL shape from
the approved catalog. The console reports capability/table/metric metadata and
parameter counts, never SQL parameter values, connection strings, passwords,
API keys, or raw credentials. `/json` exposes only the existing bounded
`RetrievalResponse` contract.

No database writes, migrations, source-data changes, corpus re-embedding, or
embedding-profile changes are performed.

## Tests

Run from `backend/`:

```bash
python -m pytest -q tests/test_adaptive_retrieval_demo.py tests/test_retrieval.py tests/test_vector_embedding.py
python -m pytest -q tests/test_adaptive_retrieval.py tests/test_chat_retrieval_integration.py
python -m compileall -q src scripts tests
```

The focused adaptive/demo/chat/retrieval run completed with **96 passed, 2
skipped**. The opt-in live Azure planner run completed separately with **2
passed**. The compile command completed successfully. The maintained backend
suite completed with **387 passed, 102 skipped**.

## Known Limitations

- Live SQL/vector answers depend on Azure SQL reachability and the active
  embedding profile.
- Adaptive planner latency depends on Azure OpenAI availability and model
  latency; a valid plan is normally one bounded structured request, with one
  strict Pydantic-AI corrective turn permitted only after malformed output.
- Forecast basket composition and backtested MAPE are unavailable unless an
  approved catalog/source metric is added through a separate architecture
  change; the demo preserves PARTIAL semantics.
- Scoped adaptive semantic retrieval remains refused where the frozen vector
  contract cannot enforce legal-entity scope.
- The current Retail chatbot registry remains disabled. This demo exercises
  the retrieval gateway directly and does not change product/navigation
  ownership.

## How To Run

From the repository root:

```bash
cd backend
source ../.venv/bin/activate
python scripts/adaptive_retrieval_demo.py
```

The local model files and Azure SQL/Azure OpenAI configuration must already be
available in the environment used for the demo.

## Azure OpenAI Planner Fix

The planner now uses an Azure-native `AsyncAzureOpenAI` client with a dedicated
15-second timeout and transport `max_retries=0`; it no longer inherits the
long retry window used by unrelated chat workloads. Pydantic-AI still emits
and validates the strict `QueryPlan` tool schema. The demo exposes real planner
request/completion/failure events and reports gateway wall-clock time, so an
Azure wait cannot be hidden behind SQL/vector timings.

Live validation on 2026-08-14 returned strict plans for both the exact forecast
prompt and a new category/inventory prompt. The exact forecast demo run used
the real planner, reached policy/compiler/SQL, and returned `PARTIAL` for the
catalog-unavailable basket and backtested-MAPE evidence; it did not use the
bounded acceptance fallback. The existing fallback remains available for a
genuine planner outage.
