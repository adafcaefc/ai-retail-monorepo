"""Append-only monitoring: history vs. the live view, and the prompt context.

Unit tests only -- `src.actions.repository` is monkeypatched, no database.
Companion to test_actions_monitoring_integration.py, which proves locking and
persistence against a real Postgres that cannot be faked here.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.actions import repository, service

# A real, currently-enabled agent (see agents/modules.py) with a short
# `db_domain` alias distinct from its canonical id, so the QC-020/QC-021
# aliasing this module already handles has something to actually exercise.
AGENT = "retail.inventory_risk"
AGENT_SHORT_KEY = "retail_inventory"


class DummySession:
    """Stands in for a Session; every repository call below is monkeypatched."""


@pytest.fixture
def session() -> DummySession:
    return DummySession()


def _alert(id_: str, *, name: str, agent: str = AGENT, issue: str = "issue") -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "subagent": "retail.inventory_risk.monitoring.stockout",
        "agent": agent,
        "issue": issue,
        "date_created": "2026-08-01T00:00:00+00:00",
        "run_id": None,
    }


def _action(
    id_: str,
    *,
    action: str,
    agent: str = AGENT,
    alert_id: str | None = None,
    status: str = "planned",
    spec: str = "",
    impact: str = "",
) -> dict[str, Any]:
    return {
        "id": id_,
        "action": action,
        "agent": agent,
        "routes": [],
        "alert_id": alert_id,
        "status": status,
        "spec": spec,
        "impact": impact,
        "reason": None,
        "simulation_summary": None,
        "created_at": "2026-08-01T00:00:00+00:00",
        "run_id": None,
    }


# ---------------------------------------------------------------------------
# History stays undeduped; the live view still dedupes and ranks
# ---------------------------------------------------------------------------


def test_alert_history_keeps_duplicate_titles(monkeypatch, session):
    """Nothing is deleted, so a later run's alert can share an older title.

    QC-021's `_dedupe` exists for the live view's aliased-agent-key
    duplication, not for this -- History has to show both rows.
    """
    alerts = [
        _alert("new", name="Stockout spike", agent=AGENT),
        _alert("old", name="Stockout spike", agent=AGENT_SHORT_KEY),
    ]
    monkeypatch.setattr(repository, "get_alerts", lambda session, **kwargs: alerts)

    history = service.list_alert_history(session, agent=AGENT)

    assert [item["id"] for item in history] == ["new", "old"]
    assert all(item["agent"] == AGENT for item in history)  # canonicalized


def test_live_alerts_still_dedupe_the_same_pair(monkeypatch, session):
    alerts = [
        _alert("new", name="Stockout spike", agent=AGENT),
        _alert("old", name="Stockout spike", agent=AGENT_SHORT_KEY),
    ]
    monkeypatch.setattr(repository, "get_alerts", lambda session, **kwargs: alerts)

    live = service.list_alerts(session, agent=AGENT)

    assert [item["id"] for item in live] == ["new"]


def test_action_history_keeps_duplicates_and_skips_ranking(monkeypatch, session):
    actions = [
        _action("new", action="Reorder SKU-1", agent=AGENT, impact="stored impact A"),
        _action("old", action="Reorder SKU-1", agent=AGENT_SHORT_KEY, impact="stored impact B"),
    ]
    monkeypatch.setattr(repository, "get_actions", lambda session, **kwargs: actions)

    history = service.list_action_history(session, agent=AGENT)

    assert [item["id"] for item in history] == ["new", "old"]
    # Unranked: stored wording is untouched, nothing from impact.enrich_actions.
    assert history[0]["impact"] == "stored impact A"
    assert "rank" not in history[0]
    assert "confidence" not in history[0]


def test_live_actions_dedupe_and_rank(monkeypatch, session):
    actions = [
        _action("new", action="Reorder SKU-1", agent=AGENT),
        _action("old", action="Reorder SKU-1", agent=AGENT_SHORT_KEY),
    ]
    monkeypatch.setattr(repository, "get_actions", lambda session, **kwargs: actions)

    live = service.list_actions(session, agent=AGENT)

    assert [item["id"] for item in live] == ["new"]
    assert "rank" in live[0]


def test_list_actions_for_alert_threads_status_filter(monkeypatch, session):
    captured: dict[str, Any] = {}

    def fake_get_actions(session, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        repository, "get_alert", lambda session, alert_id: _alert(alert_id, name="x")
    )
    monkeypatch.setattr(repository, "get_actions", fake_get_actions)

    service.list_actions_for_alert(session, "alert-1", status="planned")

    assert captured["alert_id"] == "alert-1"
    assert captured["status"] == "planned"


# ---------------------------------------------------------------------------
# current_actions: the join to its alert, miss-handling, and the context cap
# ---------------------------------------------------------------------------


def test_current_actions_resolves_the_alert_it_addresses():
    alerts_by_id = {
        "alert-1": _alert("alert-1", name="Stockout spike", issue="SKU-1 below ROP")
    }
    action = _action(
        "action-1",
        action="Reorder SKU-1",
        alert_id="alert-1",
        status="approved",
        spec="spec text",
        impact="impact text",
    )

    context = service._monitoring_context([action], alerts_by_id)

    assert context == [
        {
            "action": "Reorder SKU-1",
            "status": "approved",
            "spec": "spec text",
            "impact": "impact text",
            "alert_name": "Stockout spike",
            "alert_issue": "SKU-1 below ROP",
        }
    ]


@pytest.mark.parametrize("alert_id", ["missing", None])
def test_current_actions_miss_handling_when_alert_not_found(alert_id):
    """An action whose alert cannot be resolved still surfaces, blank rather
    than raising -- alerts_by_id is a plain dict lookup with no guarantee
    every action's alert_id is still present in it.
    """
    action = _action("action-1", action="Reorder SKU-1", alert_id=alert_id)

    context = service._monitoring_context([action], alerts_by_id={})

    assert context[0]["alert_name"] == ""
    assert context[0]["alert_issue"] == ""


def test_current_actions_cap_keeps_only_the_newest():
    """stored_actions arrives newest-first; the cap must keep the front, not
    a random slice, or a monitoring pass would see stale context instead of
    the actions most likely to already cover its issue.
    """
    total = service.MAX_MONITORING_CONTEXT + 5
    actions = [_action(f"a{i}", action=f"Action {i}") for i in range(total)]

    context = service._monitoring_context(actions, alerts_by_id={})

    assert len(context) == service.MAX_MONITORING_CONTEXT
    assert context[0]["action"] == "Action 0"
    assert context[-1]["action"] == f"Action {service.MAX_MONITORING_CONTEXT - 1}"
