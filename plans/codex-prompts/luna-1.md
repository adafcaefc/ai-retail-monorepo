Read these files completely before changing code:

- plans/adaptive-retrieval-master-spec.md
- plans/adaptive-retrieval-overnight-status.md
- plans/phase-6-retrieval-routing-changelog.md
- plans/phase-5-vector-embedding-changelog.md
- plans/retail-data-vector-bootstrap.md

Inspect the repository implementation rather than assuming anything.

You are implementation pass 1 of an unattended multi-agent engineering run.

Primary responsibility:

- Milestone 1: Retrieval Gateway
- Milestone 2: Queryable Data / Metric Catalog
- Milestone 3: Adaptive Query Planner

If earlier work already exists, inspect and validate it rather than
duplicating it.

Implement real working code and tests.

Continuously update:

- plans/adaptive-retrieval-implementation-plan.md
- plans/adaptive-retrieval-overnight-status.md

Run relevant tests after each substantial implementation boundary. Diagnose
and repair failures before proceeding.

Do not mark OVERALL_STATUS: COMPLETE because later milestones still remain.

When milestones 1–3 are complete and verified, leave:

OVERALL_STATUS: IN_PROGRESS

and clearly record that milestones 4–7 remain.

Only use BLOCKED for a genuine external blocker that cannot safely be solved.

Do not merge or push to main.
Do not perform destructive database operations.
Do not re-embed the frozen corpus without a genuine documented defect.
