# Definition of Done

Use this as the pre-merge checklist for any change touching an agent, a dashboard, or
the shared agent/data pipeline. Not every item applies to every PR — a copy-only prompt
tweak doesn't need a new allow-list entry — but check each one off deliberately (or note
why it's N/A) rather than skipping the list.

## Agent / tool changes

- [ ] New or changed agent is registered in `ENABLED_MODULES`
      (`backend/src/llm/agents/modules.py`) — or deliberately left out, with the reason
      stated in the PR description (e.g. "scaffolding only, enabling in a follow-up").
- [ ] Config JSON loads cleanly at startup — chivon's disjoint-union merge doesn't hard-error
      on a duplicate agent id, and template interpolations (`{{constants.X}}`) resolve.
- [ ] New tools are exposed via the folder's `tools/__init__.py` `TOOLS` dict (or
      `common/tools/` for cross-agent tools) so they reach `LOCAL_TOOLS`.
- [ ] Any new freeform-SQL-reachable table is added to the correct domain allow-list in
      `common/tools/freeform_query.py` — and *only* that domain's list.
- [ ] Any new state-changing tool routes through a named service function with an audit
      trail, not an ad hoc mutation via the freeform query tool.
- [ ] System prompt enforces the shared persona and forbids answering data questions
      without a tool call (see [`agent-instructions.md`](agent-instructions.md)).
- [ ] Output conforms to the component schema: ≤ 4 components, valid JSON `content`
      strings, no markdown/HTML/styling embedded, chart contract respected
      (numbers not strings, no color/layout hints), table/chart/narrative reconcile
      against the same source rows.

## Data / schema changes

- [ ] New work targets the `newdata` / `retail` star schemas, not the superseded
      per-agent schemas in `exisitingdb/` (see
      [`../principles/architecture.md`](../principles/architecture.md)).
- [ ] If dataset derivations changed: `scripts/verify_new_dataset.py` re-run and passing.
- [ ] If a dashboard's figures changed: `scripts/verify_agent_bugs.py` re-run and passing.
- [ ] If `resources/formula.md` changed: verification pack regenerated
      (`python -m src.formulas.verification_pack --write`) and
      `test_formulas.py` / `test_worked_example_cells.py` pass — never hand-edit
      `workedExamples.json`.

## Tests

- [ ] `cd backend && pytest tests/ -q` passes with no live database.
- [ ] `cd frontend && npm test` passes.
- [ ] New behavior has a test that would fail without the change — not just a test that
      happens to pass with it.
- [ ] Any test needing a live external system (real DB, real embedding model) is gated
      behind a marker + `RUN_*` env var and skips cleanly by default (see
      [`../principles/testing.md`](../principles/testing.md)).

## Frontend

- [ ] New user-facing strings are added to `src/i18n.js` for both English and Bahasa
      Indonesia — not hardcoded inline.
- [ ] A new static page or agent UI override follows the auto-discovery folder shape
      (`index.js` descriptor) rather than needing a manual registration edit.
- [ ] Chart-producing code emits the documented chart contract shape, not custom styling
      fields the renderer will ignore or mishandle.

## Docs and config hygiene

- [ ] `AGENTS.md` / `README.md` tables are updated if the change affects the agent
      registry, key file index, or API surface described there.
- [ ] Any new required environment variable is documented in the relevant
      `.env.example` with a comment on what it's for and the failure mode when unset.
- [ ] No secrets, API keys, or real connection strings committed — check `git status`
      output before staging, not just the diff of files you meant to change.

## Security

- [ ] No new SQL built via string interpolation — bound parameters only.
- [ ] No new `eval()`/`exec()`/dynamic-code-execution path for user- or model-supplied
      expressions.
- [ ] Any new externally-reachable endpoint has explicit input validation at the
      boundary and returns the correct status-code family (404 vs 422 vs 503 — see
      [`../principles/api-design.md`](../principles/api-design.md)).
