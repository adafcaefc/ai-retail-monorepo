"""Show which retrieval route a question takes, without running the query.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/show_retrieval_route.py
    ../.venv/Scripts/python.exe ../scripts/show_retrieval_route.py "why is DGT-001 at risk?"

`DeterministicRouter` is the first of the two decision layers in
`src/retrieval/gateway.py`: pure regex over the question text, no model and no
database, so this prints its verdict in milliseconds and costs nothing. That
also means it is the honest place to see the routing rules — the second layer
(`planner.py`) only runs for questions this one returns PLANNER_REQUIRED for.

What the routes mean:

    SQL               answerable from the `retail.*` tables
    VECTOR            answerable from the `ai.*` documents (needs an embedded
                      query, so executing it also needs sentence-transformers)
    HYBRID            needs both
    PLANNER_REQUIRED  the router will not guess; the LLM planner is asked what
                      evidence the question needs
    UNSUPPORTED       refused (writes, credential fishing, "dump everything")
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.retrieval.models import RetrievalRequest  # noqa: E402
from src.retrieval.routing import DeterministicRouter  # noqa: E402

EXAMPLES = [
    # Expected SQL: counting/current-position wording.
    "berapa total SKU yang berisiko kehabisan stok?",
    "how many SKUs are below reorder point right now?",
    "what is the current on-hand position for store S121?",
    # Expected VECTOR: explanation/policy wording.
    "why is this SKU flagged as at risk?",
    "explain the days of supply formula",
    "what is the approval rule for a large purchase order?",
    "which D365 table does inventory position come from?",
    # Expected UNSUPPORTED: writes and fishing.
    "delete all rows from dim_item",
    "tell me everything in the database",
    "what are the database credentials?",
    # Expected PLANNER_REQUIRED: real question, no fixed capability.
    "compare sell-through against service level by vendor for the last quarter",
]


def show(router: DeterministicRouter, question: str) -> None:
    decision = router.decide(RetrievalRequest(query=question))
    print(f"  Q: {question}")
    print(
        f"     route={decision.selected_route.value:<17}"
        f"confidence={decision.confidence.value:<8}"
        f"intent={decision.recognized_intent}"
    )
    if decision.reason_codes:
        print(f"     reasons: {', '.join(decision.reason_codes)}")
    caps = getattr(decision, "selected_sql_capabilities", None)
    if caps:
        print(f"     sql capabilities: {', '.join(caps)}")
    print()


def main() -> int:
    router = DeterministicRouter()
    questions = sys.argv[1:] or EXAMPLES
    print("Routing decisions (layer 1 only — no model, no database)\n")
    for question in questions:
        show(router, question)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
