OVERALL_STATUS: BLOCKED

# Adaptive Retrieval Overnight Status

## Senior correctness result — 2026-08-13

The adaptive retrieval implementation is code-complete and its retrieval,
policy, compiler, orchestration, grounding, live Azure SQL, live vector, and
manually loaded Chivon paths pass. It is not marked COMPLETE because the
current application registry intentionally enables only three dashboard-only
Retail modules. No enabled module has a chat agent, and no Retail chat config
is loaded at startup. The integrated `render_agent_response()` path is
therefore unreachable in the shipped application.

Choosing which of Demand Forecasting, Inventory Risk, or Replenishment should
own chat—or whether to restore the older fourth `retail.retail` sidebar
module—is a product/navigation decision. The maintained tests explicitly
assert that the three current modules are dashboard-only and that
`retail.retail` is absent, so this pass did not silently reverse that product
decision.

## Milestone status

- Adaptive Milestone 1 — Retrieval Gateway: **complete and verified**.
  Existing Phase 6 SQL, VECTOR, and HYBRID paths retain first refusal. Safe
  complex Retail requests escalate through `PLANNER_REQUIRED`, including
  analytical requests for trends and cross-domain comparisons when a matching
  fast path is insufficient. Mutation and arbitrary-SQL requests remain
  unsupported.
- Adaptive Milestone 2 — Queryable Data / Metric Catalog: **complete and
  verified**. The independently versioned catalog covers all 15 `retail.*`
  tables, approved columns/filters/metrics, grains, units, time metadata,
  relationships, and unavailable forecast basket/MAPE facts. Every catalog
  column was reconciled read-only against live Azure SQL. Invalid cross-table
  filter/dimension declarations and the misleading `forecast basket` alias
  were removed.
- Adaptive Milestone 3 — Adaptive Query Planner: **complete and verified**.
  It receives bounded retrieved catalog context, conversation/entity/agent
  context, and returns a strict Pydantic `QueryPlan` with no SQL field or
  database tool. Live Azure OpenAI planning completed for the exact forecast
  request. Semantic domain/doc-type values are schema enums, unknown metrics
  normalize to unavailable, and execution-relevant SQL/control text is
  rejected.
- Adaptive Milestone 4 — Policy Engine and deterministic compiler: **complete
  and verified**. Every adaptive branch passes through policy before
  compilation. The compiler accepts only catalog-backed `QuerySpec` values,
  emits explicit read-only `SELECT TOP (?)` statements, parameterizes all
  values, validates filters defensively, and adds deterministic ordering.
  Unsupported horizons, fields, joins/dependencies, scope escapes, excessive
  cardinality/complexity, and adversarial content fail closed.
- Adaptive Milestone 5 — Orchestration: **complete and verified**. One planner
  pass feeds bounded parallel SQL/vector branches. Required and optional
  failures now have distinct semantics; optional branch failure is a warning
  when required evidence succeeds. Zero evidence cannot be COMPLETE.
  Authorization is checked both before planning and at direct plan execution.
- Adaptive Milestone 6 — Existing Chatbot Integration: **implemented and
  integration-tested, but deployment-blocked**. The shared existing pipeline
  accepts a normalized `RetrievalResponse`, builds bounded untrusted-data
  context, fails closed when retrieval fails, requires at least one verified
  citation when evidence is supplied, and rejects unknown citations. The
  Retail prompt avoids duplicating normalized evidence through D365, and an
  unconfigured D365 tool now returns a bounded error instead of crashing.
  However, no enabled registry module points to this chat agent.
- Adaptive Milestone 7 — End-to-End Validation: **complete except for the
  shipped-registry reachability blocker above**.

## Defects fixed in the senior pass

- Escalated analytical Retail requests when a nominal fast-path keyword does
  not cover the requested trend/comparison/combination.
- Reconciled catalog references with actual queryable columns and removed
  false cross-table dimensions/filters.
- Corrected `MonthlySales.period_label`: it is a relative workbook label, not
  an ISO/calendar time field.
- Prevented non-seven-day horizons from silently compiling against the fixed
  seven-day forecast metric.
- Added schema enums and clearer constraints to make live planner output
  reliably valid while retaining strict validation.
- Stopped harmless planner prose from being rejected as executable SQL while
  retaining rejection on execution-relevant plan fields and forbidding any
  extra `sql` field.
- Added deterministic compiler ordering and defensive filter validation.
- Preserved required/optional evidence semantics through policy and branch
  execution.
- Added authorization enforcement to direct `execute_plan()` calls.
- Ensured no-evidence execution returns FAILED rather than COMPLETE.
- Restricted automatic Retail retrieval to Retail agents so unrelated Finance
  agent behavior is not regressed; any agent may still consume an explicitly
  supplied normalized response.
- Made Retail generation fail closed on retrieval failure instead of allowing
  an ungrounded numerical answer.
- Required evidence-backed generated output to contain a valid citation and
  continued to reject every unknown citation id.
- Limited prompt-visible citation ids to evidence actually included in the
  bounded grounding packet, including after size truncation.
- Kept malicious retrieved instructions inside the untrusted evidence field;
  they never become conversation or system instructions.
- Made missing D365 configuration a bounded tool diagnostic rather than an
  uncaught `KeyError`.

## Live Azure SQL/vector validation

Live configuration was available through the ignored local environment file;
no credential or connection string was printed.

- `What is the current inventory position for GRC-001?` → SQL, COMPLETE,
  one structured row and one SQL citation.
- `What does Days of Supply mean?` → VECTOR, COMPLETE, five semantic results
  and five semantic citations.
- `Why is GRC-001 at replenishment risk?` → HYBRID, COMPLETE, one structured
  result plus five semantic results and six citations.
- `Forecast demand for the next 7 days, including forecast basket and
  forecast accuracy using backtested MAPE.` → PLANNER_REQUIRED, PARTIAL,
  verified seven-day forecast SQL evidence plus bounded semantic context;
  forecast basket and backtested MAPE remained explicit
  `REQUIRED_EVIDENCE_UNAVAILABLE` errors. No MAPE or basket value was
  fabricated.
- The live adaptive planner used bounded catalog context and completed one
  structured planning pass. A representative live run spent about 29.8 s in
  planning and about 34.1 s total; this is a POC observation, not an SLA.
- Read-only catalog reconciliation found 15 live and 15 catalog tables with
  zero invalid declared catalog columns.
- Explicit live integration tests: **4 passed** (Azure SQL capabilities,
  SQL/VECTOR/HYBRID retrieval, active AI catalog, and real local BGE).

No database migration, write, re-embedding, or destructive database command
was run.

## Chatbot validation

The disabled `retail.retail.chat` config was loaded explicitly into the
existing Chivon singleton for a non-persistent smoke test; no second chatbot
framework was created.

- All three fast-path prompts synthesized successfully from their normalized
  response and emitted valid citation markers.
- The complex forecast prompt synthesized successfully with a visible PARTIAL
  notice, cited exact forecast values, and plainly stated that forecast basket
  and backtested MAPE were unavailable.
- Invalid citations, omitted citations on evidence-backed output, failed
  retrieval, malicious semantic instructions, and absent D365 configuration
  have deterministic regression coverage.

This proves the integration code works when loaded, but does not remove the
registry blocker in the shipped application.

## Maintained verification results

- `cd backend && python -m pytest -q tests` → **362 passed, 100 skipped**.
  Skips are the repository's opt-in/environment cases.
- `cd backend && python -m pytest -q tests/test_retrieval.py tests/test_adaptive_retrieval.py tests/test_chat_retrieval_integration.py`
  → focused retrieval/chat suite passed (the final full suite supersedes the
  earlier focused count).
- `cd backend && RUN_AZURE_SQL_INTEGRATION=1 RUN_LOCAL_EMBEDDING_INTEGRATION=1 python -m pytest -q tests/test_retrieval.py tests/test_vector_embedding.py -m 'azure_sql or local_embedding'`
  → **4 passed, 53 deselected**.
- `cd backend && python -m compileall -q src tests` → passed.
- `cd frontend && npm test -- --run` → **54 passed** across six files.
- `cd frontend && npm run build` → passed (689 modules transformed).
- `git diff --check` → passed.

## Exact blocker reproduction

Run from `backend/`:

```bash
python - <<'PY'
from src.llm.agents import ENABLED_MODULES, AGENT_CONFIG_FILES, AGENT_REGISTRY
print("enabled=", ENABLED_MODULES)
print("dashboard_only=", {k: v.dashboard_only for k, v in AGENT_REGISTRY.items()})
print("chat_agents=", {k: v.chat_agent for k, v in AGENT_REGISTRY.items()})
print("config_files=", [p.name for p in AGENT_CONFIG_FILES])
PY
```

Observed:

```text
enabled= ('retail.demand_forecasting', 'retail.inventory_risk', 'retail.replenishment')
dashboard_only= {'retail.demand_forecasting': True, 'retail.inventory_risk': True, 'retail.replenishment': True}
chat_agents= {'retail.demand_forecasting': '', 'retail.inventory_risk': '', 'retail.replenishment': ''}
config_files= ['common.json', 'simulator.json', 'subagents.json']
```

`backend/tests/test_retail_module.py` intentionally asserts the same
three-dashboard-only contract and explicitly asserts that `retail.retail` is
not enabled.

## Safest next action

Obtain the product/navigation decision for chat ownership, then take one of
these reviewed paths:

1. Restore `retail.retail` as a fourth enabled module, preserving the three
   dashboard-only destinations; or
2. Assign chat to one or more of the three current destinations, introducing
   an explicit chat-capability flag so chat can be enabled without accidentally
   enabling monitoring, action, and generic dashboard APIs.

After that decision, update the registry/frontend contract tests, run the same
full/live suites, and repeat the four shipped-application chatbot prompts.
Only then should this file change to `OVERALL_STATUS: COMPLETE`.

## Files changed

- Adaptive retrieval: `backend/src/retrieval/{catalog.json,catalog.py,compiler.py,gateway.py,grounding.py,orchestrator.py,planner.py,policy.py}` plus updates to `__init__.py`, `models.py`, `observability.py`, `routing.py`, and `service.py`.
- Existing chatbot: `backend/src/llm/pipeline.py`, shared config, Retail chat
  config, and Retail D365 forecast tool.
- Tests: `backend/tests/test_adaptive_retrieval.py` and
  `backend/tests/test_chat_retrieval_integration.py`.
- Existing frontend test harness: `frontend/vitest.config.js`.
- Durable plans/status and the existing overnight runner script.

User-owned/unrelated `logs/` content was preserved. No merge, push, history
rewrite, or destructive database operation was performed.
