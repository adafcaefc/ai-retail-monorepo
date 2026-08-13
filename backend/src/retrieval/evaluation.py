from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.common.constants import AppPaths

from .models import RetrievalRequest
from .routing import DeterministicRouter

DEFAULT_ROUTING_FIXTURE = (
    AppPaths.BACKEND_ROOT / "tests" / "fixtures" / "retrieval_routing_cases.json"
)


def evaluate_routing(
    path: Path = DEFAULT_ROUTING_FIXTURE,
    *,
    router: DeterministicRouter | None = None,
) -> dict[str, Any]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    resolved_router = router or DeterministicRouter()
    failures = []
    for case in cases:
        request_fields = {
            name: case[name]
            for name in (
                "query", "route_mode", "retrieval_domain", "doc_type", "entity_hints"
            )
            if name in case
        }
        try:
            decision = resolved_router.decide(RetrievalRequest(**request_fields))
        except ValueError:
            actual = {
                "route": "UNSUPPORTED",
                "reason_codes": ["INVALID_FILTER"],
                "capabilities": [],
                "domain": None,
                "doc_type": None,
            }
        else:
            actual = {
                "route": decision.selected_route.value,
                "reason_codes": decision.reason_codes,
                "capabilities": decision.selected_sql_capabilities,
                "domain": decision.selected_vector_filters.retrieval_domain,
                "doc_type": decision.selected_vector_filters.doc_type,
            }
        problems = []
        if actual["route"] != case["expected_route"]:
            problems.append(f"route={actual['route']}")
        if case["expected_reason"] not in actual["reason_codes"]:
            problems.append(f"reasons={actual['reason_codes']}")
        if case.get("expected_capability") and case["expected_capability"] not in actual["capabilities"]:
            problems.append(f"capabilities={actual['capabilities']}")
        if "expected_domain" in case and actual["domain"] != case["expected_domain"]:
            problems.append(f"domain={actual['domain']}")
        if "expected_doc_type" in case and actual["doc_type"] != case["expected_doc_type"]:
            problems.append(f"doc_type={actual['doc_type']}")
        if problems:
            failures.append({"id": case["id"], "problems": problems})
    return {
        "valid": not failures,
        "case_count": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "failures": failures,
    }

