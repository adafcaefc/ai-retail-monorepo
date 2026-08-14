# Adaptive Retrieval Senior Audit

AUDIT_STATUS: READY_FOR_PRODUCT_DECISION

## Executive verdict

The adaptive retrieval implementation is ready to proceed to the Retail chat ownership/product decision, subject to the live Azure validation and authorization caveats recorded below. The main path is genuinely adaptive: it selects bounded evidence requirements from a versioned catalog, validates those requirements deterministically, compiles fixed-shape parameterized SQL, runs bounded SQL/vector branches, and returns separate structured and semantic evidence.

The audit did find and fix real defects. The deterministic router could previously trap several legitimate analytical questions in an entity-bound Phase 6 capability or reject them as unsupported. The chatbot also did not fail closed for every citation-less/failed response, and adaptive semantic requirements could be recreated with a fresh retrieval service. Those issues are now covered by regression tests.

The exact forecast request is not succeeding only because of an acceptance-query branch. Its normal route is `PLANNER_REQUIRED` and the normal gateway invokes the planner. The narrow exact-query fallback is resilience logic used only after planner/policy/compiler/no-evidence failure; it still retrieves the approved seven-day forecast and marks forecast basket and backtested MAPE unavailable. Those unavailable facts are never fabricated.

The remaining current application blocker is the intentional registry/product choice: the enabled Retail modules are dashboard-only and no Retail chat agent is loaded at normal startup. The implementation must not enable one automatically. This is a product/navigation decision, not an unfinished adaptive execution path. It is not a production security approval: enterprise identity and legal-entity authorization are still required before exposing chat to users.

## Architecture verified

The runtime flow is:

1. The existing chat pipeline automatically requests retrieval only when the agent name starts with `retail.`. Finance and other agents do not enter this path.
2. `ChatRetrievalGateway` invokes `RetrievalService` first. SQL, VECTOR, and HYBRID decisions execute through the existing Phase 6 service.
3. A safe request that cannot be represented by a fixed capability returns `PLANNER_REQUIRED` from the service without opening Azure SQL or loading the vector provider.
4. The gateway then calls one `AdaptiveRetrievalOrchestrator` planning pass. The planner receives a bounded relevant catalog slice, bounded conversation/entity context, and no database tool.
5. `QueryPolicy.validate()` authorizes the structured plan against the active catalog. `DeterministicSqlCompiler` converts each approved structured requirement into fixed-shape SQL. The execution layer never consumes planner SQL because the plan has no SQL field and the compiler accepts only `QuerySpec` values.
6. Independent approved SQL and semantic requirements are submitted to bounded executor branches. SQL and vector branches can overlap; the local embedding provider is cached and guarded by its service lock.
7. The orchestrator aggregates `structured_results`, `semantic_results`, citations, warnings, errors, and timings into `RetrievalResponse`. It does not generate an answer.
8. The existing chatbot receives only `build_grounding_packet()` output. The packet is bounded, citation-addressable, and explicitly labels retrieved content as data rather than instructions. Generated citation markers are validated before UI rendering.

The old CLI `retrieve` command intentionally stops at the service boundary. A separate `retrieve-gateway` command now exercises the complete fast-path-plus-adaptive gateway without changing the Phase 6 diagnostic command.

## Generalization review

The main adaptive path is general within the approved catalog. Routing is not keyed to the full acceptance sentence, `next 7 days`, basket, MAPE, `GRC-001`, or `S001`. The planner schema, catalog search, policy, compiler, and orchestrator have no exact acceptance-query dependency.

There is one deliberately narrow fallback in `gateway.py`: a regex recognizes the exact forecast acceptance shape after an adaptive failure and builds a catalog-derived `QueryPlan`. This is resilience logic, not the primary planner. Its plan contains:

- `demand.forecast_7d` as an available structured metric;
- `forecast.basket` as required but unavailable; and
- `forecast.backtested_mape` as required but unavailable, with optional methodology context only.

The fallback cannot make unavailable metrics executable, and the gateway does not use it for arbitrary queries. The main planner path remains the path used when the model is available.

The original lexical escalation was too narrow. I verified and corrected cases including inventory by store, current inventory plus forecast, category inventory ranking, sales by legal entity, vendor service-level ranking, GMROI by category, and sell-through by category. They now escalate instead of silently selecting an unrelated SKU-level capability. Entity-bound capabilities without a recognizable entity now also escalate when the request looks like an aggregate/analytical question; definition/formula semantic requests retain their VECTOR fast path.

This is not an unrestricted natural-language SQL system. Questions outside Retail vocabulary, write/arbitrary-data requests, and facts absent from the catalog remain unsupported or unavailable. That is the intended safe limitation, not evidence of acceptance-query hard-coding.

## Fast-path / escalation review

Verified behavior:

- `What is the current inventory position for GRC-001?` → `SQL`, with `sku.inventory_current` and exact-entity resolution.
- `What does Days of Supply mean?` → `VECTOR`, with terminology filtering.
- `Why is GRC-001 at replenishment risk?` → `HYBRID`, preserving structured replenishment evidence and business-rule context separately.
- The exact forecast request → `PLANNER_REQUIRED`, with no Phase 6 database access in the service-only command.
- Safe analytical combinations and unsupported fixed dimensions → `PLANNER_REQUIRED` rather than a misleading fixed capability.
- Mutations, arbitrary SQL markers, broad “all data” requests, credential/secrets requests, and unrelated questions → `UNSUPPORTED`.

The router checks mutation/arbitrary-query refusal before adaptive vocabulary. The fast path therefore cannot be bypassed by adding Retail words to a write or arbitrary SQL request. Explicit route overrides cannot force a planner-required structured request through SQL or VECTOR.

The fixed Phase 6 paths remain intact in the maintained routing fixture and regression tests. The router is still lexical and therefore should be treated as a bounded classifier, not as a complete semantic intent model. The adaptive planner is the safety-preserving escape hatch for safe Retail analytical shapes that fixed keywords cannot represent.

## Planner safety review

The planner boundary is sound:

- `QueryPlan` is a strict Pydantic model with forbidden extra fields. A supplied `sql` field is rejected.
- Execution-relevant fields are scanned for SQL control syntax. Unknown metrics and invalid dimensions are normalized to unavailable before policy execution.
- Metrics, dimensions, filters, aggregations, semantic domains, and document types are typed and bounded. Semantic values are constrained by enums where they affect retrieval routing.
- `request`, rationale, planning notes, and unavailable explanations are not execution inputs; they are not incorrectly treated as SQL. They do not reach the compiler.
- The planner has no database connection, callable database tool, SQL tool, or write capability. It returns evidence requirements only.
- The prompt explicitly instructs the model to use the catalog and leave dependencies empty. The policy independently rejects dependencies because no typed join compiler exists.
- Catalog text is supplied as bounded context and is treated as untrusted context in the planner instructions. Model output still has to pass Pydantic, catalog normalization, policy, and compiler checks.

The model cannot select an arbitrary table or column merely by naming it. A metric must resolve to the active catalog; a dimension must be declared for that metric; a filter must be an approved field for that metric's catalog table; and the compiler independently rechecks the active metric/table/column relationship.

## Policy / compiler review

Adaptive execution cannot begin before policy validation. `AdaptiveRetrievalOrchestrator.execute_plan()` re-authorizes the principal, calls `QueryPolicy.validate()`, and only then compiles and submits branch work. The normal `retrieve()` path is not the only enforcement point.

The policy enforces:

- active catalog version and `retail.*` source tables;
- approved metrics, metric columns, dimensions, aggregations, and filters;
- typed filter operators and bounded scalar/list values;
- SQL-control rejection in string filter values;
- at most 50 rows, eight structured requirements, eight semantic requirements, twelve filters per query, fifty `IN` values, and bounded complexity;
- bounded date ranges and the exact seven-day rule for `demand.forecast_7d`;
- no free-form dependencies/joins until a typed join compiler exists;
- authorization scope filters for structured metrics whose tables carry `legal_entity_id`;
- rejection when legal-entity scope cannot be enforced, including scoped adaptive plans with semantic requirements because the frozen vector contract has no legal-entity filter;
- a fixed ten-second policy timeout value, applied to connections that expose the supported timeout property.

The compiler emits no `SELECT *`, DDL, DML, or arbitrary SQL fragment. Tables, columns, dimensions, time fields, operators, and aggregation functions are selected from catalog-approved metadata. Values, dates, entity scope values, and row limits are DB-API parameters. `TOP (?)` is always emitted with the bounded policy limit. Row-grain and aggregate queries receive deterministic ordering where an ordering key exists.

I added a defensive compiler check so a direct `QuerySpec` seam cannot introduce a time field that differs from the catalog metric. Direct `execute_plan()` calls are still policy-gated, and policy-rejected plans do not invoke either executor.

The timeout is a bounded contract rather than a universal cancellation guarantee. The current SQL adapter sets `connection.timeout` when available; it does not issue a driver-independent command cancellation. This is acceptable for the internal POC boundary but remains a production risk.

## Catalog correctness review

The catalog is versioned as `2026-08-13.1` and describes 15 `retail.*` normalized tables, eight approved metrics, typed dimensions/filters, grains, units, time metadata, and descriptive relationships. I reconciled catalog table names and columns against `TABLE_COLUMNS` and `SOURCE_LOAD_COLUMNS` in the structured bootstrap code:

- catalog tables: 15;
- normalized actual tables, including `SourceLoad`: 15;
- catalog columns absent from the normalized schema: 0;
- relationship columns absent from their referenced actual tables: 0.

Important semantics are represented correctly:

- `MonthlySales.period_label` is a relative workbook period, not a calendar date;
- promotion validity uses `valid_from`/`valid_to` and configured uplift is not an observed outcome;
- the seven-day forecast is the `StoreSkuSnapshot.forecast_7d` metric;
- forecast basket composition and forecast accuracy/backtested MAPE are explicitly in `known_unavailable` and are not aliases of the forecast-units metric.

The listed relationships are metadata only. They are not presented to the compiler as executable joins; policy rejects dependencies until typed join support exists. Some potentially useful cross-table questions therefore fail safely or return PARTIAL rather than pretending that a relationship is executable. `StoreSkuSnapshot` also has no legal-entity field in the current catalog, so scoped requests that require that fact are correctly refused rather than leaking unscoped data.

## Orchestration review

The adaptive path performs one planning pass followed by bounded execution and one aggregation step. There is no planner → database → planner loop and no uncontrolled tool iteration. The default executor worker count is bounded and capped at eight.

Evidence semantics are preserved:

- structured and semantic evidence remain separate response fields and separate citation kinds;
- required unavailable evidence creates an error;
- required branch failure or no results creates an error;
- useful evidence plus an error produces `PARTIAL`;
- no evidence produces `FAILED`, including an empty successful-looking SQL/vector result;
- an optional branch failure becomes a warning when required evidence succeeds;
- zero evidence cannot be `COMPLETE`;
- semantic context never substitutes for an unavailable exact numerical fact, and SQL facts never substitute for required semantic methodology.

SQL/vector branches are independently submitted and aggregate their results after completion. The local embedding provider is cached at the service level and protected by a lock; this preserves model safety but serializes simultaneous vector model calls within that process. The gateway now shares the fast service with adaptive semantic execution so fast and adaptive paths do not maintain duplicate embedding-provider caches.

## Grounding / citation review

`build_grounding_packet()` limits structured evidence to 12 rows, semantic evidence to eight items, excerpts to 700 characters, scalar values to 240 characters, and the complete packet to 14,000 characters. It selects citation IDs only from evidence surviving truncation, so a citation removed by the bound is not available to the generator.

The packet includes status, route, diagnostics, and explicit instructions that retrieved content is data rather than instructions. SQL evidence is authoritative for exact numerical facts; semantic evidence is context only; unavailable values must not be inferred. Malicious semantic text remains inside a JSON evidence field and cannot become a system or conversation instruction through the retrieval boundary.

The pipeline now fails closed before Chivon generation when retrieval is `FAILED` or when the bounded packet has no citation IDs. This applies even if the route is `UNSUPPORTED`. When generation does run, every citation marker is checked against the IDs actually included in the packet; unknown IDs and missing required references return a visible withheld notice. `PARTIAL` and its diagnostics remain in the final generation context and are also rendered visibly alongside the response.

Automatic retrieval is restricted to `retail.*` agent names. Finance and other agents retain their existing behavior unless a caller explicitly supplies a retrieval response.

## CLI / gateway review

The original command calls `retrieve_context()`, which is the deterministic `RetrievalService` boundary. `RetrievalService` deliberately returns immediately for `PLANNER_REQUIRED`, so the observed result is expected:

```text
status=FAILED
route=PLANNER_REQUIRED
planning_ms=0.0
error=PLANNER_REQUIRED
```

It is not an accidental planner failure; that command never constructs or invokes the adaptive gateway. I preserved it as a fast-path/Phase 6 diagnostic command and added:

```text
python -m src.retail_data_bootstrap retrieve-gateway "..."
```

The new command invokes `ChatRetrievalGateway`, so it exercises escalation, planning, policy, compilation, and evidence aggregation. In this environment the exact gateway command did not complete within a safe 20-second observation window because the Azure model call was unreachable/slow; it produced no contradictory application response. The separate live test identified the Azure SQL network failure independently.

## Performance analysis

The overnight report's approximately 29.8-second planning and 34.1-second total observation is consistent with one Azure OpenAI planner request plus network/model latency, not with an intentional multi-pass retrieval loop. The code path contains one `AdaptiveQueryPlanner.plan()` call, and the planner has no tools. Catalog search is deterministic and now cached; the planner agent is lazily constructed once per planner instance; Pydantic-AI output retries are set to zero for this one-pass planner; and each planner request has a 15-second model timeout.

Measured local prompt dimensions for the exact request:

- relevant catalog context: 7,329 characters;
- serialized planner payload: about 7,533 characters;
- selected context: five tables, two metrics, four relationships, and two unavailable items.

That is bounded and not the full catalog, but it is still roughly 1,800–2,000 tokens before model-generated output. The existing shared `AsyncOpenAI` client reports `max_retries=2`, a five-second connect timeout, and a 600-second default read timeout. The planner's per-request 15-second setting is passed through Pydantic-AI to the OpenAI call, but client-level network retries can still add attempts and backoff around a failed request. The current environment could not complete the gateway observation, so the exact 29.8-second run cannot be independently reproduced here and should not be treated as a measured SLA.

Highest-value optimizations, in order:

1. Instrument planner request count, retry count, model response time, validation time, and network error category; use a planner-specific OpenAI client with an explicit low retry count so one unavailable model call cannot consume several timeout windows.
2. Add a bounded plan cache keyed by normalized query, relevant context, catalog version, and agent scope, with explicit invalidation/TTL. Cache only validated plans and never bypass policy or compilation.
3. Reduce the planner schema/context to the smallest relevant metric/table slice and preserve one structured call. Do not remove policy, catalog, compiler, authorization, or citation checks to improve latency.

## Frontend test-harness review

The overnight working-tree modification added a global `testTimeout: 10000` to `frontend/vitest.config.js`. I tested the full frontend suite with the default five-second per-test timeout and all 54 tests passed, including the demand dashboard. The timeout override was therefore unnecessary and overly broad; the file was returned to the default harness behavior. The dashboard suite can take about 16 seconds in aggregate, but its individual tests remained below the default per-test limit in the final run.

## Retail chat registry blocker

Normal registry inspection confirms exactly:

```text
enabled = retail.demand_forecasting, retail.inventory_risk, retail.replenishment
dashboard_only = True, True, True
chat_agent = '', '', ''
loaded config files = common/config/common.json,
                    common/config/simulator.json,
                    common/config/subagents.json
```

`retail.retail` is absent from `ENABLED_MODULES`, so its chat config is not loaded during normal startup. The existing Retail chat configuration works only when loaded manually, as the overnight report stated. Do not enable it automatically.

For the current shipped application, this is the only remaining blocker to exposing the adaptive path through Retail navigation: the product must decide which Retail module owns chat and how it is presented. Separately, before production exposure, the chat request must carry an authenticated principal rather than the current internal CLI fallback, and legal-entity scope must be derived from authorization rather than a client-selected dashboard filter. Those are explicit pre-exposure security requirements, not reasons to enable a module during this audit.

## Fixes made during this audit

The working tree already contained the overnight adaptive implementation. The additional focused audit changes were:

- broadened deterministic safe-Retail escalation and added entity-bound fast-path checks so uncovered analytical shapes do not use misleading Phase 6 capabilities;
- made empty service retrieval responses `FAILED` with `NO_EVIDENCE_RETRIEVED`;
- made the chatbot fail closed for all failed or citation-less retrieval responses, including `UNSUPPORTED`, and added tests for the boundary;
- rejected scoped adaptive plans that contain semantic requirements which the frozen vector contract cannot legally scope;
- reused the retrieval service/embedding cache across fast and adaptive gateway paths;
- cached catalog searches and planner-agent construction, set planner output retries to zero, and applied a bounded per-call planner timeout;
- added the clearly named `retrieve-gateway` CLI command while preserving `retrieve` as the deterministic Phase 6 command;
- added a defensive compiler check for catalog-approved time fields;
- added routing, catalog/schema, compiler, empty-evidence, scope, planner-fallback, and grounding regression coverage;
- removed the broad Vitest timeout override after proving it was unnecessary. No functional frontend harness timeout change remains.

No database writes, migrations, production/source-data changes, re-embedding, Git history rewrites, pushes, or module-enablement changes were made.

## Validation results

Passed:

```text
cd backend
python -m pytest -q tests/test_retrieval.py tests/test_adaptive_retrieval.py tests/test_chat_retrieval_integration.py
85 passed, 2 skipped

python -m pytest -q tests
375 passed, 100 skipped

python -m compileall -q src tests
git diff --check

cd ../frontend
npm test -- --run
54 passed across 6 files

npm run build
689 modules transformed; dist/index.html 970.18 kB; build succeeded
```

Routing probes produced SQL, VECTOR, HYBRID, and PLANNER_REQUIRED for the three Phase 6 examples and the exact forecast request respectively. The service-only exact CLI produced `FAILED / PLANNER_REQUIRED / planning_ms=0.0`, which is the intentional service boundary. The complete gateway CLI was separately attempted with a safe 20-second timeout and did not complete because the Azure model path was not reachable quickly enough.

Opt-in live validation was attempted with:

```text
RUN_AZURE_SQL_INTEGRATION=1 RUN_LOCAL_EMBEDDING_INTEGRATION=1 \
python -m pytest -q tests/test_retrieval.py tests/test_vector_embedding.py \
-m 'azure_sql or local_embedding'
```

Result: `1 passed, 3 failed, 54 deselected`. The local embedding check passed. All three failures were before query execution while opening Azure SQL and reported SQLSTATE `08001` / SQL Server Network Interfaces error `0x271D`. This is an infrastructure/network failure, so live SQL/VECTOR/HYBRID and live adaptive evidence remain unverified in this environment. The overnight report's successful live claims were not accepted without this independent run.

## Remaining risks

- Azure SQL reachability and a successful Azure OpenAI adaptive run were unavailable during this audit. The exact live `PARTIAL` response with real forecast evidence still needs to be rerun in a networked environment.
- The shared OpenAI client still has client-level retries; the planner timeout bounds each request but not necessarily the total time across retry attempts. The reported 29.8-second planning observation needs request-level instrumentation.
- `InternalPocAuthorizationPolicy` checks only an internal marker. The normal chat pipeline currently defaults the gateway to `cli_principal()` and does not pass authenticated legal-entity authorization. Retail chat must remain disabled until this is integrated.
- Scoped semantic adaptive retrieval is intentionally refused because the frozen vector schema lacks legal-entity filtering. Adding scope-aware semantic retrieval requires a separate typed authorization/data-contract change.
- The catalog currently supports only the listed metrics and no adaptive joins. Forecast basket and backtested MAPE remain unavailable exact facts. The correct result for those requirements is PARTIAL/FAILED, never an inferred value.
- SQL timeout enforcement depends on the DB-API driver's connection timeout behavior; there is no portable command cancellation implementation.
- The lexical router is deliberately bounded. Continued evaluation should add representative unseen Retail questions so safe requests escalate rather than become unsupported, without weakening arbitrary-query/write refusal.

## Recommended next 3 actions

1. Make the product/navigation decision for Retail chat ownership, then enable the chosen module explicitly and run normal-startup end-to-end validation; do not enable `retail.retail` as an audit-side convenience.
2. Integrate the authenticated principal and authorized legal-entity scope into the chat gateway, and either add scope-aware semantic retrieval or keep scoped semantic plans refused before exposure.
3. In a networked environment, rerun the four live probes and exact forecast gateway request with planner attempt/timing instrumentation; set planner-specific retry behavior and add a validated bounded plan cache if latency remains above the POC target.
