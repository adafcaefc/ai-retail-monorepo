You are the final senior engineering and correctness pass.

Read completely:

- plans/adaptive-retrieval-master-spec.md
- plans/adaptive-retrieval-implementation-plan.md
- plans/adaptive-retrieval-overnight-status.md
- plans/phase-6-retrieval-routing-changelog.md
- plans/phase-5-vector-embedding-changelog.md

Then inspect:

- the complete Git diff
- implementation architecture
- tests
- current database/vector integration
- existing chatbot integration

Luna implementation passes have already attempted the project.

DO NOT redo working implementation merely for stylistic preference.

Your job is to determine whether the complete system actually satisfies the
master specification.

Specifically audit:

1. Phase 6 fast paths remain intact.
2. Safe unknown informational requests can escalate.
3. Query catalog accurately represents queryable data.
4. Adaptive planner uses retrieved catalog context.
5. Planner produces structured plans, never executable SQL.
6. Policy engine validates every dynamic structured query.
7. SQL compiler is deterministic, read-only and parameterized.
8. Unsafe/adversarial plans cannot reach Azure SQL.
9. SQL/vector work can be composed efficiently.
10. Parallel retrieval is used where safe.
11. COMPLETE/PARTIAL/FAILED semantics are correct.
12. Existing chatbot consumes RetrievalResponse evidence.
13. Exact/current numerical claims are grounded in SQL evidence.
14. Semantic context is properly bounded.
15. Retrieved content cannot override system instructions.
16. Citation IDs are validated.
17. Missing evidence cannot become fabricated values.
18. Existing maintained tests remain healthy.

Run the full relevant test/build suite.

Run live Azure SQL/vector smoke tests when configuration/network permits.

Test:

"What is the current inventory position for GRC-001?"

"What does Days of Supply mean?"

"Why is GRC-001 at replenishment risk?"

and especially:

"Forecast demand for the next 7 days, including forecast basket and forecast
accuracy using backtested MAPE."

If the underlying data cannot supply one portion of the complex request, the
system must return a correct PARTIAL result rather than fabricate it.

Fix defects you find.

Do not merely review and report fixable problems.

After fixing, rerun the relevant tests.

Update plans/adaptive-retrieval-overnight-status.md accurately.

Mark:

OVERALL_STATUS: COMPLETE

ONLY when the master Definition of Done is genuinely satisfied.

Otherwise mark:

OVERALL_STATUS: BLOCKED

and document the exact genuine blocker, reproduction commands, completed work,
and safest next action.

Never merge or push to main.
Never make destructive database changes.
Never expose credentials.
