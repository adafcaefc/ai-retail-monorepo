"""Resolving a named action onto a stored one, and failing usefully.

Written against a live failure: the user asked the Replenishment agent to
"Simulate switching DGT-046, DGT-019 and DGT-063", the agent called
simulate_action_impact with the title it composed from that sentence --
"Switch DGT-046, DGT-019, DGT-063 to best_price_vendor" -- and the call failed
with "No stored action matches". The action was in the database the whole
time, titled "CFO approval: switch sourcing on top DGT SKUs", with those SKU
ids in its spec.

Two defects sat behind it. The substring test ran one way only, so a request
longer than the stored title could never match; and the failure carried no ids,
so the agent had nothing to retry with and repeated the identical call.

The fixture rows are the real ones, so the titles and specs here are what the
matcher actually has to cope with.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.llm.agents.common.tools import alert_actions
from src.llm.agents.common.tools.alert_actions import (
    UnresolvedAction,
    _resolve_action,
)

SOURCING_ID = "d4b050ab-8a7a-450a-a44b-e3ff64dc877e"
DELEGATION_ID = "fd2284ed-d663-4929-81de-45cdc40e1008"

STORED: list[dict[str, Any]] = [
    {
        "id": SOURCING_ID,
        "action": "CFO approval: switch sourcing on top DGT SKUs",
        "agent": "retail.replenishment",
        "routes": ["CFO"],
        "status": "planned",
        "impact": "Sourcing saving: capture",
        "spec": (
            "Target SKUs DGT-046, DGT-019, DGT-063, DGT-041, DGT-060; source "
            "these PO quantities from best_price_vendor instead of "
            "designated_vendor for this PO only; success metric: realised "
            "unit-price equals trade-agreement best_price and captured saving "
            ">=90%."
        ),
    },
    {
        "id": DELEGATION_ID,
        "action": "Approve delegated sourcing approvals",
        "agent": "retail.replenishment",
        "routes": ["CFO"],
        "status": "planned",
        "impact": "CFO decision load: reduce",
        "spec": (
            "Create delegation: allow Procurement Director to approve vendor "
            "switches for POs <= IDR 500,000,000 when best_price_vendor OTIF "
            "and lead_adherence >= designated vendor."
        ),
    },
    {
        "id": "7c31a90e-0000-4000-8000-000000000001",
        "action": "Clarify accuracy KPI",
        "agent": "retail.demand_forecasting",
        "routes": ["Demand Planning Lead"],
        "status": "planned",
        "impact": "KPI definition: agree",
        "spec": "Agree one accuracy definition across the forecast board.",
    },
]

# What the agent composed from the user's sentence. It reads like the action
# and shares not one word with the stored title.
COMPOSED_TITLE = "Switch DGT-046, DGT-019, DGT-063 to best_price_vendor"


class FakeRepository:
    """Stand-in for src.actions.repository, over the fixture rows."""

    @staticmethod
    def get_actions(session: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return list(STORED)

    @staticmethod
    def get_action(session: Any, action_id: str) -> dict[str, Any] | None:
        for item in STORED:
            if item["id"] == action_id:
                return item
        return None


@pytest.fixture(autouse=True)
def fake_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the fixture rows wherever the module imports the repository."""
    import src.actions

    monkeypatch.setattr(src.actions, "repository", FakeRepository, raising=False)


def resolve(**kwargs: Any) -> dict[str, Any]:
    return _resolve_action(session=None, **kwargs)


def test_action_id_resolves_directly() -> None:
    assert resolve(action_id=SOURCING_ID)["id"] == SOURCING_ID


def test_exact_title_resolves() -> None:
    resolved = resolve(action="CFO approval: switch sourcing on top DGT SKUs")
    assert resolved["id"] == SOURCING_ID


def test_title_match_ignores_case_and_padding() -> None:
    resolved = resolve(action="  cfo approval: SWITCH sourcing on top dgt skus ")
    assert resolved["id"] == SOURCING_ID


def test_fragment_of_a_stored_title_resolves() -> None:
    """The old one-directional test: a shorter quote still has to work."""
    assert resolve(action="switch sourcing on top DGT")["id"] == SOURCING_ID


def test_stored_title_wrapped_in_a_sentence_resolves() -> None:
    """The direction that used to miss: request longer than the title."""
    resolved = resolve(
        action=(
            "Please simulate CFO approval: switch sourcing on top DGT SKUs "
            "before I take it to the board"
        )
    )
    assert resolved["id"] == SOURCING_ID


def test_short_title_inside_a_long_question_is_not_a_match() -> None:
    """Containment is only evidence when the title is specific enough.

    A three-word title landing inside a long sentence is a coincidence. It must
    not silently resolve, or the wrong remediation gets simulated.
    """
    with pytest.raises(UnresolvedAction):
        resolve(
            action=(
                "We should clarify accuracy KPI ownership and a dozen other "
                "reporting questions raised in the steering meeting today"
            )
        )


def test_composed_title_does_not_resolve_but_hands_back_the_ids() -> None:
    """The reported failure: no match, and now a way out of it."""
    with pytest.raises(UnresolvedAction) as raised:
        resolve(action=COMPOSED_TITLE)

    payload = raised.value.payload
    assert payload["resolved"] is False
    assert payload["requested_action"] == COMPOSED_TITLE
    assert payload["stored_action_count"] == len(STORED)

    listed = {item["action_id"] for item in payload["stored_actions"]}
    assert SOURCING_ID in listed

    # The spec excerpt is the whole point: it is the only place the SKU the
    # user named is visible, so it is what lets the agent pick the right id.
    sourcing = next(
        item
        for item in payload["stored_actions"]
        if item["action_id"] == SOURCING_ID
    )
    assert "DGT-046" in sourcing["spec"]


def test_unknown_action_id_also_hands_back_the_ids() -> None:
    with pytest.raises(UnresolvedAction) as raised:
        resolve(action_id="00000000-0000-4000-8000-000000000000")

    payload = raised.value.payload
    assert payload["resolved"] is False
    assert payload["stored_actions"]


def test_ambiguous_title_lists_only_the_rivals() -> None:
    """'sourcing' hits both replenishment actions, so neither may be assumed."""
    with pytest.raises(UnresolvedAction) as raised:
        resolve(action="sourcing")

    payload = raised.value.payload
    listed = {item["action_id"] for item in payload["stored_actions"]}
    assert listed == {SOURCING_ID, DELEGATION_ID}


def test_naming_nothing_is_a_caller_error() -> None:
    """A missing name is the agent's bug, not a resolution failure."""
    with pytest.raises(ValueError):
        resolve()


def test_spec_excerpt_is_capped() -> None:
    long_spec = dict(STORED[0])
    long_spec["spec"] = "DGT-046 " * 200
    digest = alert_actions._digest(long_spec)
    assert len(digest["spec"]) <= alert_actions._SPEC_EXCERPT + 3
    assert digest["spec"].endswith("...")


@pytest.fixture
def offline_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hand the tools a session they never use, without touching a database."""
    from contextlib import contextmanager

    import src.db.db as db

    @contextmanager
    def fake_scope():
        yield None

    monkeypatch.setattr(db, "session_scope", fake_scope)


def test_simulate_returns_the_payload_instead_of_raising(
    offline_session: None,
) -> None:
    """A raising tool aborts the whole run, so the agent never reads the fix.

    pydantic-ai propagates a plain exception out of the run and pipeline.py
    turns it into a failed response, which is what produced the dead end on
    screen. Returning the payload keeps the agent alive with the ids in hand.
    """
    result = asyncio.run(
        alert_actions.simulate_action_impact(action=COMPOSED_TITLE)
    )

    assert result["resolved"] is False
    assert result["stored_actions"]
    assert "action_id" in result["note_to_agent"]


def test_unresolved_approval_approves_nothing(
    offline_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dangerous half: a name that does not resolve must not approve."""
    import src.actions.service as actions_service

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("approve_action ran on an unresolved name")

    monkeypatch.setattr(actions_service, "approve_action", refuse)

    result = alert_actions.request_action_approval(action=COMPOSED_TITLE)

    assert result["resolved"] is False
    assert result.get("status") != "APPROVED"
