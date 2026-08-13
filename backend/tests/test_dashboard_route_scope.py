"""`GET /dashboard/{agent}` over HTTP: what it accepts, and what it admits to.

Exercised through the real ASGI app rather than by calling the handler, because
the behaviour under test is FastAPI's: it discards query parameters the route
was not declared with, before any handler code runs. That is precisely the
silent failure this route used to have, and it is invisible from a unit test of
the function.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

AGENT = "retail.replenishment"
URL = f"/api/html/dashboard/{AGENT}"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_an_unscoped_request_returns_the_payload(client: TestClient) -> None:
    response = client.get(URL)

    if response.status_code == 503:
        pytest.skip("no seeded retail database")

    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == AGENT
    assert len(body["lines"]) == 800
    # Nothing was asked for, so nothing can have been ignored.
    assert "ignored_filters" not in body


def test_retail_filters_reach_the_route_instead_of_being_dropped(
    client: TestClient,
) -> None:
    """The five the boards send that the old three-parameter route discarded."""
    response = client.get(
        URL,
        params={
            "store_id": "ST-001",
            "state": "Stockout",
            "route": "direct",
            "sku": "GRC-001",
            "reorder_only": "true",
        },
    )

    assert response.status_code == 200
    # The stub narrows by nothing, so all five come back named. When a real
    # builder lands, this list shrinks — and that shrinking is the proof the
    # builder is actually filtering.
    assert response.json()["ignored_filters"] == [
        "store_id",
        "state",
        "route",
        "sku",
        "reorder_only",
    ]


def test_a_cleared_dropdown_is_not_reported_as_ignored(client: TestClient) -> None:
    response = client.get(URL, params={"legal_entity_id": "ALL", "store_id": "ALL"})

    assert response.status_code == 200
    assert "ignored_filters" not in response.json()


def test_reorder_only_false_is_not_a_filter(client: TestClient) -> None:
    # A non-empty string is truthy; left to Python's truthiness this would both
    # narrow the board and report itself as ignored.
    response = client.get(URL, params={"reorder_only": "false"})

    assert response.status_code == 200
    assert "ignored_filters" not in response.json()


def test_a_misspelt_filter_is_refused_rather_than_ignored(client: TestClient) -> None:
    response = client.get(URL, params={"store": "ST-001"})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "store" in detail
    assert "store_id" in detail


def test_an_unknown_agent_is_still_a_404(client: TestClient) -> None:
    response = client.get("/api/html/dashboard/retail.nope")

    assert response.status_code == 404
