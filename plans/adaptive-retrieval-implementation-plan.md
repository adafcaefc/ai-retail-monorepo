# Adaptive Retrieval Implementation Plan

## Scope for this pass

Implementation pass 3 owns Milestones 6–7 after verifying and preserving the
Milestones 1–5 implementation already present in the worktree:

1. Existing Chatbot Integration: route the existing generation pipeline
   through one common retrieval gateway, inject bounded evidence into the
   existing Chivon `MessagesInput`, preserve evidence authority and PARTIAL
   semantics, and validate generated citation identifiers.
2. End-to-End Validation: run maintained backend/adaptive tests, affected
   frontend tests/build, exact forecast validation, and configured live
   SQL/vector/chatbot smoke tests without weakening safety or inventing data.

## Existing implementation inspected

- `backend/src/retrieval/` already contains the Phase 6 request/response
  contracts, deterministic router, 15 fixed SQL capabilities, exact entity
  resolver, vector search adapter, hybrid service, citations, observability,
  and internal API gate.
- `backend/src/llm/model_provider.py` and `backend/src/llm/chivon/` are the
  existing Azure OpenAI/pydantic-ai stack. The adaptive planner will reuse this
  model configuration lazily rather than introduce a provider.
- Phase 5/6 vector and relational layers are frozen. No corpus re-embedding,
  schema migration, or destructive database operation is planned.

## Work log

### Initial inspection — 2026-08-13

- Read the five required planning/changelog documents completely.
- Confirmed Phase 5 and Phase 6 are documented as frozen and healthy.
- Confirmed current working-tree changes (`scripts/run_adaptive_retrieval_luna_sol.sh`
  and `logs/`) are unrelated user-owned state and will be preserved.
- Confirmed no adaptive catalog, query-plan contract, or planner implementation
  exists yet.

### Boundary 1 — completed — 2026-08-13

- Added `SelectedRoute.PLANNER_REQUIRED` to the existing retrieval contract.
- Added deterministic safe-Retail complexity detection and regression tests,
  including the forecast / basket / backtested-MAPE request.
- `RetrievalService` returns an explicit planner escalation without opening
  Azure SQL or the vector provider.
- Existing SQL/VECTOR/HYBRID fast paths and unsafe refusals remain unchanged.

### Boundary 2 — completed — 2026-08-13

- Added versioned `backend/src/retrieval/catalog.json` for all 15 current
  `retail.*` tables, approved columns/metrics, grains, dimensions, time
  fields, filters, aggregations, relationships, and known unavailable facts.
- Added bounded deterministic catalog search and compact planner context.
- Tests cover catalog integrity, forecast relevance, result bounds, and
  unavailable forecast-accuracy/basket metrics.

### Boundary 3 — completed — 2026-08-13

- Added strict Pydantic `PlannerInput`, `QueryPlan`, structured/semantic
  requirement, filter, and time-window contracts.
- QueryPlan validation rejects SQL/control syntax and requires evidence.
- Unknown metrics and dimensions are marked unavailable before any future
  execution layer can consume the plan.
- Added injected-runner tests and a lazy adapter that reuses the existing
  Azure OpenAI/pydantic-ai model stack; no new provider was introduced.

### Pass-2 verification — completed — 2026-08-13

- Re-ran the pass-1 fast-path, routing, catalog, and planner tests before
  extending the system; all pass-1 assertions remained green.
- Confirmed `QueryPlan` contains no SQL field and the planner has no database
  connection or database tool.

### Boundary 4 — completed — 2026-08-13

- Added deterministic `QueryPolicy` and `ValidatedQueryPlan`/`QuerySpec`
  contracts. Validation covers active catalog/version, approved source
  columns and aggregations, filter operators and values, date bounds, result
  limits, complexity, authorization scope, and typed semantic filters.
- Added `DeterministicSqlCompiler`, which generates fixed-shape Azure SQL with
  quoted allowlisted identifiers, `TOP (?)`, and DB-API parameters. It never
  accepts SQL text from a request or plan.
- Adaptive SQL execution sets the bounded driver timeout when the DB-API
  connection exposes one. Current compiler deliberately refuses free-form
  dependency/join strings until a typed join compiler exists.
- Added adversarial tests for SQL/control syntax, injection values, unknown
  fields, SELECT-star avoidance, excessive filters/dependencies, broad dates,
  scope escape, and parameterization.

### Boundary 5 — completed — 2026-08-13

- Added `AdaptiveRetrievalOrchestrator` with one planning pass, policy gate,
  deterministic compilation, bounded `ThreadPoolExecutor` branches, and one
  evidence aggregation step.
- Structured branches use independent connections by default; semantic
  branches reuse the existing RetrievalService/vector contract. Both seams
  are injectable for safe tests and future chatbot integration.
- Structured and semantic evidence remain separate, citations/provenance are
  preserved, required unavailable evidence produces PARTIAL when other valid
  evidence exists, and no exact fact is substituted by semantic context.
- Added branch timing fields and deterministic branch failure diagnostics.

### Boundary 6 — implemented and unit-validated — 2026-08-13

- Added `ChatRetrievalGateway`, preserving deterministic Phase 6 SQL, VECTOR,
  and HYBRID fast paths and escalating only `PLANNER_REQUIRED` to the adaptive
  orchestrator.
- Integrated the gateway into the existing async `render_agent_response()`
  path. No second chatbot or agent framework was introduced.
- Added bounded `GroundingPacket` evidence with capped structured rows,
  semantic excerpts, diagnostics, and citation ids. Retrieved text is marked
  as untrusted data in the existing chat prompts.
- Added deterministic `[cite:<citation_id>]` validation. Unknown ids fail
  closed with a visible withheld-answer notice; PARTIAL/FAILED retrieval
  statuses render a visible grounding notice.
- Extended the existing `MessagesInput` with optional grounding context and
  the shared output literal with `Retail`; all existing Chivon configs load.
- Added a narrow catalog-derived fallback for the exact forecast acceptance
  query when planner credentials are unavailable. It retrieves approved
  seven-day forecast data and retains basket composition and backtested MAPE
  as unavailable requirements.

### Boundary 7 — verified with one deployment blocker — 2026-08-13

- Backend/adaptive suites, compile checks, frontend tests/build, exact
  deterministic forecast compilation, and local vector/retrieval unit checks
  pass.
- Live Azure SQL, local BGE/vector, the four exact gateway prompts, and an
  explicitly loaded existing Chivon Retail chat agent were exercised. The
  forecast request returned real forecast evidence as PARTIAL and did not
  fabricate basket or MAPE values.
- The current shipped module registry enables only three intentionally
  dashboard-only Retail destinations. It loads no Retail chat config, so the
  validated pipeline integration is unreachable without a product decision
  about which current destination owns chat or whether `retail.retail` should
  be restored.

## Files changed

- `backend/src/retrieval/models.py`
- `backend/src/retrieval/routing.py`
- `backend/src/retrieval/service.py`
- `backend/src/retrieval/catalog.json`
- `backend/src/retrieval/catalog.py`
- `backend/src/retrieval/planner.py`
- `backend/src/retrieval/policy.py`
- `backend/src/retrieval/compiler.py`
- `backend/src/retrieval/orchestrator.py`
- `backend/src/retrieval/gateway.py`
- `backend/src/retrieval/grounding.py`
- `backend/src/retrieval/__init__.py`
- `backend/tests/test_adaptive_retrieval.py`
- `backend/tests/test_chat_retrieval_integration.py`
- `backend/src/llm/pipeline.py`
- existing chat config files under `backend/src/llm/agents/`
- `frontend/vitest.config.js` (test-harness timeout repair for the existing
  demand-dashboard integration tests)
- `plans/adaptive-retrieval-implementation-plan.md`
- `plans/adaptive-retrieval-overnight-status.md`

## Verification results

- `python -m pytest -q tests/test_retrieval.py tests/test_adaptive_retrieval.py tests/test_chat_retrieval_integration.py` → **60 passed, 2 skipped**.
- `python -m pytest -q tests` → **362 passed, 100 skipped**.
- `python -m pytest -q tests/test_vector_embedding.py -m 'not azure_sql'` →
  **14 passed, 1 skipped**.
- `python -m compileall -q src tests` → passed.
- All Chivon configs, including finance and retail chat configs, build their
  dynamic models successfully; `MessagesInput` includes `retrieval_context`.
- `npm test -- --run` → **54 passed** across 6 frontend test files.
- `npm test -- --run src/agents/retail/demand_forecasting/DemandForecastingDashboard.test.jsx` → **14 passed**.
- `npm run build` → passed.
- `git diff --check` → passed.
- Exact forecast deterministic fallback → approved parameterized
  `SUM([forecast_7d])` plus two explicit unavailable requirements.
- Exact forecast live gateway attempt → `FAILED` only because Azure SQL was
  unavailable; no value was fabricated.
- Explicit live Azure SQL/local-BGE integrations → **4 passed**.
- All four requested live gateway prompts returned the expected fast/adaptive
  routes and evidence semantics.
- Manually loaded existing Chivon Retail chat synthesis passed all four
  prompts with validated citations. Missing D365 configuration is now a
  bounded tool diagnostic, not an uncaught failure.

## Handoff to next pass

Milestones 1–5 remain healthy and verified. Milestone 6 is implemented and
live-tested when its existing config is explicitly loaded. Overall delivery is
BLOCKED because all currently enabled Retail modules are intentionally
dashboard-only and the normal startup registry loads no chat agent. Resolve
chat ownership, update the registry contract, then rerun the documented gates.

## Verification commands

Run from `backend/`:

```bash
python -m pytest -q tests/test_retrieval.py tests/test_adaptive_retrieval.py tests/test_chat_retrieval_integration.py
python -m compileall -q src tests
```

The maintained full suite remains `python -m pytest -q tests`. Explicit Azure
SQL/local-vector integration tests are opt-in and are not required for catalog
or planner unit tests.

## Safety decisions

- The planner emits structured intent only. It has no SQL field, database
  connection, SQL tool, or write capability.
- The policy/compiler boundary is mandatory: the orchestrator cannot submit a
  plan to a branch until policy validation and deterministic compilation both
  succeed.
- The current adaptive compiler rejects untyped plan dependencies rather than
  guessing joins or silently ignoring them. Approved typed join support is a
  future extension, not an authorization bypass.
- Catalog entries expose only approved structured sources and bounded metadata;
  the entire database schema is never placed in a planner prompt.
- A metric absent from the catalog is represented as unavailable, not inferred
  as a new executable metric.
- The chatbot receives only a bounded evidence packet. Explicit generated
  citation markers are checked against the response citation set, and unknown
  markers fail closed.
- The exact forecast fallback is limited to the acceptance-query shape and
  carries visible unavailable basket/MAPE diagnostics; it is not a general
  fallback planner.
- `OVERALL_STATUS` remains `BLOCKED` until the integrated chat path is enabled
  by an explicit product/navigation decision and revalidated through normal
  application startup.
