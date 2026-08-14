Read completely:

- plans/adaptive-retrieval-master-spec.md
- plans/adaptive-retrieval-implementation-plan.md
- plans/adaptive-retrieval-overnight-status.md

Inspect the actual current Git diff and tests.

You are implementation pass 2.

First verify the work from pass 1. If an earlier milestone is incomplete,
broken, or inconsistent with the master specification, repair it before
continuing.

Primary responsibility:

- Milestone 4: Query Policy Engine + Deterministic SQL Compiler
- Milestone 5: Adaptive Retrieval Orchestrator

Implement real working code and tests.

The LLM must never directly execute generated SQL.

Query plans must be deterministically validated before a deterministic
compiler produces parameterized read-only SQL.

Add strong adversarial tests.

Adaptive SQL/vector branches should execute concurrently where safe and return
evidence through the existing RetrievalResponse philosophy.

Continuously update the implementation plan and overnight status.

Run relevant existing and new tests, repair failures, and record exact results.

Do not mark COMPLETE while chatbot integration / final UAT remains.

Do not merge/push to main.
Do not perform destructive database operations.
