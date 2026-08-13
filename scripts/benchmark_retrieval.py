#!/usr/bin/env python3
"""Small Phase 6 POC benchmark; outputs route/timing metadata, never query text."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.retrieval.authorization import cli_principal  # noqa: E402
from src.retrieval.models import RetrievalRequest  # noqa: E402
from src.retrieval.service import RetrievalService  # noqa: E402


CASES = {
    "SQL": "What is the current inventory position for GRC-001?",
    "VECTOR": "What does Days of Supply mean?",
    "HYBRID": "Why is GRC-001 at replenishment risk?",
}


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, int(0.95 * len(ordered)) - 1))
    return {
        "samples": len(values),
        "min_ms": round(ordered[0], 3),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(ordered[-1], 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not 2 <= args.iterations <= 50:
        raise ValueError("--iterations must be between 2 and 50")
    service = RetrievalService()
    principal = cli_principal()
    measurements: dict[str, dict[str, list[float]]] = {}
    # Warm the provider/database path once. This cold start remains separately
    # visible rather than contaminating the steady-state distribution.
    cold = service.retrieve(
        RetrievalRequest(query=CASES["VECTOR"], top_k=args.top_k),
        principal=principal,
    )
    for route, query in CASES.items():
        route_values = {
            "total_ms": [], "routing_ms": [], "entity_resolution_ms": [],
            "sql_ms": [], "query_embedding_ms": [], "vector_search_ms": [],
            "serialization_ms": [],
        }
        for _ in range(args.iterations):
            result = service.retrieve(
                RetrievalRequest(query=query, top_k=args.top_k),
                principal=principal,
            )
            if result.status.value != "COMPLETE":
                raise RuntimeError(
                    f"{route} benchmark retrieval failed with "
                    f"{[error.code for error in result.errors]}"
                )
            for key in route_values:
                route_values[key].append(float(getattr(result.timing, key)))
        measurements[route] = route_values
    output = {
        "kind": "phase6_poc_baseline",
        "iterations_per_route": args.iterations,
        "cold_vector_total_ms": cold.timing.total_ms,
        "cold_query_embedding_ms": cold.timing.query_embedding_ms,
        "routes": {
            route: {name: _summary(values) for name, values in metrics.items()}
            for route, metrics in measurements.items()
        },
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
