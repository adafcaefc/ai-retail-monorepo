Read completely:

- plans/adaptive-retrieval-master-spec.md
- plans/adaptive-retrieval-implementation-plan.md
- plans/adaptive-retrieval-overnight-status.md

Inspect all existing implementation and the current Git diff.

You are implementation pass 3.

First repair any unfinished or failing work from earlier milestones.

Primary responsibility:

- Milestone 6: Existing Chatbot Integration
- Milestone 7: End-to-End Validation

Inspect the existing chatbot/agent architecture before modifying it.

Do NOT create a second chatbot or agent framework.

Integrate the common retrieval gateway into the existing generation path.

Implement bounded grounding and citation validation.

Run:

- existing backend tests
- adaptive retrieval tests
- affected frontend tests
- frontend build where appropriate
- SQL smoke tests when configured
- vector smoke tests
- exact forecast query
- end-to-end chatbot smoke test when existing credentials permit
- git diff --check

Repair failures rather than documenting and ignoring them.

The exact forecast query is:

"Forecast demand for the next 7 days, including forecast basket and forecast
accuracy using backtested MAPE."

The system must return the best available grounded result. If the underlying
source lacks an actual requested value, that requirement must remain visibly
PARTIAL rather than fabricated.

Continuously update the implementation plan and overnight status.

If the entire master specification genuinely satisfies its Definition of
Done after real validation, you MAY mark:

OVERALL_STATUS: COMPLETE

Otherwise leave IN_PROGRESS with exact remaining work, or BLOCKED only for a
genuine external blocker.

Do not merge/push to main.
Do not perform destructive database operations.
