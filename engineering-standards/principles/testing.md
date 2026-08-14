# Testing Principles

## Two suites, both fixture-based by default

```bash
cd backend
../.venv/Scripts/python.exe -m pytest tests/ -q     # no database needed

cd frontend
npm test                                            # vitest + jsdom, API mocked
```

Neither suite touches a live database or a live Azure OpenAI deployment by default.
That's deliberate — CI and local dev should never need real credentials to tell you
whether the code is broken. Keep it that way: a new test that needs a live dependency
belongs behind an opt-in marker (below), not in the default run.

## Opt-in integration tests are markers, not separate test runners

`backend/pytest.ini` declares two markers for tests that hit real external systems:

```ini
markers =
    azure_sql: live Azure SQL integration test (opt-in with RUN_AZURE_SQL_INTEGRATION=1)
    local_embedding: real local BGE model integration test (opt-in with RUN_LOCAL_EMBEDDING_INTEGRATION=1)
```

Each test checks its own env-var gate and skips itself when unset, rather than the test
runner needing separate invocation flags. If you add a test that needs a live database,
a real model download, or any other slow/credentialed dependency, follow this pattern:
add a marker, gate it on an explicit `RUN_*` env var, and make the default `pytest
tests/` run skip it cleanly rather than fail or hang.

## Distinguish "is the data right" from "is the app right"

Two verifier scripts answer genuinely different questions, and conflating them would
hide bugs:

```bash
cd backend
../.venv/Scripts/python.exe ../scripts/verify_new_dataset.py   # is the DATA right?
../.venv/Scripts/python.exe ../scripts/verify_agent_bugs.py    # is the APP right?
```

`verify_new_dataset.py` re-expresses the dataset's own reconciliation checks and KPI
derivations as SQL against `newdata` — a failure means the **import** is wrong.
`verify_agent_bugs.py` compares what a dashboard actually renders against the same
figures recomputed independently from `newdata` — a failure means the **application**
is wrong even though the data is fine. When you add a new dashboard card or a new
derived figure, ask which of these two questions a regression in it would be answering,
and add the check to the matching script rather than a third place. If it's genuinely a
new kind of question, that's a signal for a third verifier, not for stretching one of
these two.

`verify_qc_fixes.py` uses a related but distinct convention worth reusing: each row
prints `PASS`, `OPEN`, or `MANUAL`, and the script's exit code is 1 only when a
previously-`PASS`ing check regresses — an `OPEN` row (known, not-yet-done work) is not a
CI failure. If you build another "audit the codebase against a checklist" script, use
this three-state model rather than collapsing "not done yet" and "broken" into the same
failure.

## Contract tests assert against the real source of truth, not just internal consistency

`test_worked_example_cells.py` re-parses `resources/formula.md` and asserts the
generated `workedExamples.json` is byte-identical, **then** opens the real workbook and
checks every cited cell holds the documented value. It would be cheaper to only check
internal consistency (does the JSON match what the parser currently produces?) — that
test would pass even if the source-of-truth document and the JSON drifted together and
were both wrong. When a piece of data is "generated from X, verified against Y," write
the test against both, the way this one does.

## Test placement and naming

- Backend: `backend/tests/test_<subject>.py`, one file per feature area (e.g.
  `test_dashboard_filters_and_period.py`, `test_action_impact.py`). No live DB in the
  default run — use the existing fixture patterns in `backend/tests/` rather than
  standing up a new fixture style per file.
- Frontend: `*.test.jsx` colocated next to the component it tests (e.g.
  `InventoryRiskDashboard.test.jsx` beside `InventoryRiskDashboard.jsx`), using
  `@testing-library/react` + `vitest` + `jsdom`, with API calls mocked — not hitting the
  dev server.

## What a new agent or tool needs covered

When you add or change an agent (see [`ai/definition-of-done.md`](../ai/definition-of-done.md)
for the full checklist), test coverage should include:

- The tool's SQL runs against the latest completed import batch and returns the shape
  its `output_model` expects.
- If the tool is reachable via freeform query, its table(s) are on the correct
  domain allow-list — a test that asserts an *out-of-domain* table is rejected is as
  important as one that asserts the in-domain query succeeds.
- Dashboard payload contract: shape matches what the frontend expects
  (`test_dashboard_payload_contract.py` is the pattern to extend, not duplicate).
- If the change touches `formula.md` or the formula store, re-run the verification pack
  (`python -m src.formulas.verification_pack`) and let `test_formulas.py` /
  `test_worked_example_cells.py` catch drift — don't hand-edit
  `workedExamples.json`.
