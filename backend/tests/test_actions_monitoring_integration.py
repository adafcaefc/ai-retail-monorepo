"""populate_alerts against a real Postgres: locking, run tracking, and the
switch from destroy-and-replace to purely additive.

Opt-in: skipped unless DATABASE_URL is set, since this hits a real database
and requires `scripts/migrate_monitoring_runs.py` to have been applied.
`chivon.run_async` is stubbed so no real LLM call happens -- these tests are
about persistence and locking, not model behavior. Cleans up precisely by id
(repository.delete_alert/delete_action), never via clear_alerts: the shared
dev DB already has real rows for this domain and clear_alerts would remove
those too.

No pytest-asyncio in this project (nothing else here uses async tests), so
each test is a plain `def` that drives its async body with `asyncio.run`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text

# Import (not os.getenv) so .env is loaded first: src.common.env calls
# load_dotenv() at import time, and checking the raw environment before that
# import runs makes the skip condition depend on which other test modules
# pytest happened to collect first.
from src.common.env import config  # noqa: E402

pytestmark = pytest.mark.skipif(
    not config.DATABASE_URL,
    reason="requires a real DATABASE_URL",
)

from src.actions import repository, service  # noqa: E402
from src.db.db import get_engine, session_scope  # noqa: E402

# A real, currently-enabled agent (see agents/modules.py). Its monitoring
# passes run against the live retail tables via the real snapshot/schema
# tools -- only chivon.run_async (the model call itself) is stubbed.
AGENT = "retail.inventory_risk"


class _FakeResult:
    def __init__(self, alerts: list[dict[str, Any]]) -> None:
        self.output = {"alerts": alerts}


def _none_alert(subagent: str) -> dict[str, Any]:
    return {"name": "none", "issue": "no alert detected", "subagent": subagent, "actions": []}


def _one_alert(tag: str) -> dict[str, Any]:
    return {
        "name": f"{tag} alert",
        "issue": f"{tag} issue written by test_actions_monitoring_integration",
        "subagent": "test",
        "actions": [
            {
                "name": f"{tag} action",
                "routes": ["Test Owner"],
                "agent": "retail_inventory",
                "impact": "test impact",
                "spec": "test spec",
                "reason": "test reason",
            }
        ],
    }


def _single_alert_run_async(first_pass_name: str, tag: str):
    """Exactly one alert (and its one action) per populate call: the first
    monitoring pass raises it, the rest report the standard 'none' sentinel
    that populate_alerts already filters out. Deterministic row counts.
    """

    async def run_async(agent_name: str, payload: dict[str, Any]) -> _FakeResult:
        if agent_name == first_pass_name:
            return _FakeResult([_one_alert(tag)])
        return _FakeResult([_none_alert(agent_name)])

    return run_async


@pytest.fixture
def chivon_stub(monkeypatch):
    """Swap get_chivon() for a stub whose run_async the test controls."""

    class _Stub:
        run_async = None

    stub = _Stub()
    monkeypatch.setattr(service, "get_chivon", lambda: stub)
    return stub


@pytest.fixture
def first_pass_name() -> str:
    return service.get_agent(AGENT).monitoring_passes[0].agent_name


def _created_ids(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    alert_ids = [item["id"] for item in payload["items"]]
    action_ids = [
        action["id"] for item in payload["items"] for action in item.get("actions", [])
    ]
    return alert_ids, action_ids


def _cleanup(alert_ids: list[str], action_ids: list[str]) -> None:
    with session_scope() as session:
        for action_id in action_ids:
            repository.delete_action(session, action_id)
        for alert_id in alert_ids:
            repository.delete_alert(session, alert_id)


def test_populate_twice_doubles_the_row_count_not_constant(chivon_stub, first_pass_name):
    """Nothing is deleted between runs: two populates append, they do not
    replace -- the whole point of the append-only rewrite.
    """
    # Mutated in place by body(), not returned, so a mid-test assertion
    # failure still leaves this list holding whatever rows were created
    # before the failure -- the finally below must clean those up too.
    all_alert_ids: list[str] = []
    all_action_ids: list[str] = []

    async def body() -> None:
        for tag in ("first-run", "second-run"):
            chivon_stub.run_async = _single_alert_run_async(first_pass_name, tag)
            with session_scope() as session:
                payload = await service.populate_alerts(session, AGENT)
            alert_ids, action_ids = _created_ids(payload)
            assert len(alert_ids) == 1
            all_alert_ids.extend(alert_ids)
            all_action_ids.extend(action_ids)

        # Both runs' alerts are still present -- the first run's row was
        # never touched by the second.
        with session_scope() as session:
            stored = repository.get_alerts(session, agent=AGENT)
        stored_ids = {item["id"] for item in stored}
        assert set(all_alert_ids) <= stored_ids
        assert len(set(all_alert_ids)) == 2

    try:
        asyncio.run(body())
    finally:
        _cleanup(all_alert_ids, all_action_ids)


def test_concurrent_populate_is_rejected_then_succeeds_after(chivon_stub, first_pass_name):
    """Two overlapping calls for the same domain: the second is rejected
    while the first is in flight. A third succeeds once the first completes,
    proving the advisory lock was released rather than leaked.
    """

    # Mutated in place by body(), not returned, so a mid-test assertion
    # failure still leaves this list holding whatever rows were created
    # before the failure -- the finally below must clean those up too.
    all_alert_ids: list[str] = []
    all_action_ids: list[str] = []

    async def body() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocking_run_async(
            agent_name: str, payload: dict[str, Any]
        ) -> _FakeResult:
            started.set()
            await release.wait()
            if agent_name == first_pass_name:
                return _FakeResult([_one_alert("overlap")])
            return _FakeResult([_none_alert(agent_name)])

        chivon_stub.run_async = blocking_run_async

        with session_scope() as first_session:
            first_task = asyncio.create_task(
                service.populate_alerts(first_session, AGENT)
            )
            await asyncio.wait_for(started.wait(), timeout=5)

            # The first call is holding the lock: a second call for the same
            # domain must be rejected immediately, not queued.
            with session_scope() as second_session:
                with pytest.raises(service.PopulateAlreadyRunningError):
                    await service.populate_alerts(second_session, AGENT)

            release.set()
            first_payload = await first_task

        alert_ids, action_ids = _created_ids(first_payload)
        all_alert_ids.extend(alert_ids)
        all_action_ids.extend(action_ids)

        # The first call released the lock in `finally`: a third call must
        # succeed right away rather than also being rejected.
        chivon_stub.run_async = _single_alert_run_async(first_pass_name, "after-release")
        with session_scope() as third_session:
            third_payload = await service.populate_alerts(third_session, AGENT)
        alert_ids, action_ids = _created_ids(third_payload)
        assert len(alert_ids) == 1
        all_alert_ids.extend(alert_ids)
        all_action_ids.extend(action_ids)

    try:
        asyncio.run(body())
    finally:
        _cleanup(all_alert_ids, all_action_ids)


def test_forced_failure_marks_run_failed_and_releases_lock(
    chivon_stub, first_pass_name, monkeypatch
):
    chivon_stub.run_async = _single_alert_run_async(first_pass_name, "unused")

    def boom(session, **kwargs):
        raise RuntimeError("forced failure for test_actions_monitoring_integration")

    # get_actions runs after the lock and the STARTED run row are already
    # created but before any pass executes -- an error here is outside every
    # per-pass try/except, so it reaches populate_alerts's own except clause.
    monkeypatch.setattr(repository, "get_actions", boom)

    async def first_call() -> None:
        with session_scope() as session:
            with pytest.raises(RuntimeError, match="forced failure"):
                await service.populate_alerts(session, AGENT)

    asyncio.run(first_call())

    with get_engine().connect() as connection:
        row = (
            connection.execute(
                text(
                    """
                    SELECT run_status, error_message
                    FROM chat.monitoring_runs
                    WHERE agent = :agent
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"agent": AGENT},
            )
            .mappings()
            .first()
        )

    assert row is not None
    assert row["run_status"] == "FAILED"
    assert "forced failure" in (row["error_message"] or "")

    # The lock was released in `finally`: a second call gets past
    # try_advisory_lock and hits the SAME forced error (not
    # PopulateAlreadyRunningError), proving the first call did not leak it.
    async def second_call() -> None:
        with session_scope() as session:
            with pytest.raises(RuntimeError, match="forced failure"):
                await service.populate_alerts(session, AGENT)

    asyncio.run(second_call())
