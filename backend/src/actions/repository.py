"""Repository for chat.alerts and chat.actions (raw SQL, chat schema)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

ACTION_STATUS_PLANNED = "planned"
ACTION_STATUS_APPROVED = "approved"
ALLOWED_ACTION_STATUSES = (
    ACTION_STATUS_PLANNED,
    ACTION_STATUS_APPROVED,
)


_UUID_COLUMNS = frozenset({"id", "alert_id"})


def _row(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        elif hasattr(value, "hex") and value.__class__.__name__ == "UUID":
            data[key] = str(value)
        elif key in _UUID_COLUMNS and isinstance(value, str):
            # pyodbc returns UNIQUEIDENTIFIER as an uppercase str, not a
            # uuid.UUID object, unlike psycopg. Lowercase it to match the
            # ids this module generates with uuid4() so callers can compare
            # a generated id against a stored one.
            data[key] = value.lower()
    if "routes" in data:
        routes = data["routes"]
        if routes is None:
            data["routes"] = []
        elif isinstance(routes, str):
            try:
                data["routes"] = json.loads(routes)
            except json.JSONDecodeError:
                data["routes"] = []
    return data


def _normalize_status(status: str | None) -> str:
    value = (status or ACTION_STATUS_PLANNED).strip().lower()
    if value == "pending":
        return ACTION_STATUS_PLANNED
    if value not in ALLOWED_ACTION_STATUSES:
        raise ValueError(
            f"Unsupported action status {status!r}. "
            f"Allowed: {', '.join(ALLOWED_ACTION_STATUSES)}."
        )
    return value


def _dump_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _agent_filter(
    agent: str | Sequence[str] | None,
    filters: list[str],
    params: dict[str, Any],
) -> None:
    """Filter on one agent key or on a set of keys that mean the same agent.

    QC-020: the same agent is stored under both its canonical id and its older
    short key ('finance.treasury' and 'cashflow'). Callers pass every key an
    agent answers to, so one query returns its whole history.
    """
    if not agent:
        return
    keys = [agent] if isinstance(agent, str) else list(agent)
    if len(keys) == 1:
        filters.append("agent = :agent")
        params["agent"] = keys[0]
    else:
        filters.append("agent IN :agents")
        params["agents"] = keys


def _execute(session: Session, sql: str, params: dict[str, Any]):
    """Run `sql` against `session`, expanding an `agents` list param into IN (...)."""
    statement = text(sql)
    if isinstance(params.get("agents"), list):
        statement = statement.bindparams(bindparam("agents", expanding=True))
    return session.execute(statement, params)


def get_alerts(
    session: Session,
    *,
    agent: str | Sequence[str] | None = None,
    subagent: str | None = None,
    name: str | None = None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: dict[str, Any] = {}

    _agent_filter(agent, filters, params)
    if subagent:
        filters.append("subagent = :subagent")
        params["subagent"] = subagent
    if name:
        filters.append("name = :name")
        params["name"] = name

    sql = """
        SELECT
            id,
            name,
            subagent,
            agent,
            issue,
            date_created,
            run_id
        FROM chat.alerts
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY CASE WHEN date_created IS NULL THEN 1 ELSE 0 END, date_created DESC, id DESC"

    return [
        _row(row)
        for row in _execute(session, sql, params).mappings().all()
    ]


def get_alert(
    session: Session,
    alert_id: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                name,
                subagent,
                agent,
                issue,
                date_created,
                run_id
            FROM chat.alerts
            WHERE id = :alert_id
            """
        ),
        {"alert_id": alert_id},
    ).mappings().first()
    return _row(row) if row else None


def save_alert(
    session: Session,
    *,
    name: str,
    subagent: str,
    agent: str,
    issue: str,
    run_id: int | None = None,
    commit: bool = True,
) -> str:
    """
    Insert one alert and return its id.

    Callers that write many rows in a row should pass commit=False and commit
    once at the end. Each commit is a network round trip; against a remote
    Postgres that dominates the cost of persisting a monitoring run.
    """
    alert_id = str(uuid4())
    session.execute(
        text(
            """
            INSERT INTO chat.alerts (
                id,
                name,
                subagent,
                agent,
                issue,
                date_created,
                run_id
            )
            VALUES (
                :id,
                :name,
                :subagent,
                :agent,
                :issue,
                SYSUTCDATETIME(),
                :run_id
            )
            """
        ),
        {
            "id": alert_id,
            "name": name,
            "subagent": subagent,
            "agent": agent,
            "issue": issue,
            "run_id": run_id,
        },
    )
    if commit:
        session.commit()
    return alert_id


def save_alerts(
    session: Session,
    alerts: list[dict[str, Any]],
    *,
    run_id: int | None = None,
    commit: bool = True,
) -> list[str]:
    """
    Insert many alerts in one executemany round trip and return their ids.

    Ids are generated here, so callers can attach actions to them before the
    rows are flushed. Pass commit=False to fold this into a larger transaction.
    """
    if not alerts:
        return []

    rows = [
        {
            "id": str(uuid4()),
            "name": alert["name"],
            "subagent": alert["subagent"],
            "agent": alert["agent"],
            "issue": alert["issue"],
            "run_id": run_id,
        }
        for alert in alerts
    ]
    session.execute(
        text(
            """
            INSERT INTO chat.alerts (
                id,
                name,
                subagent,
                agent,
                issue,
                date_created,
                run_id
            )
            VALUES (
                :id,
                :name,
                :subagent,
                :agent,
                :issue,
                SYSUTCDATETIME(),
                :run_id
            )
            """
        ),
        rows,
    )
    if commit:
        session.commit()
    return [row["id"] for row in rows]


def delete_alert(
    session: Session,
    alert_id: str,
) -> bool:
    result = session.execute(
        text("DELETE FROM chat.alerts WHERE id = :alert_id"),
        {"alert_id": alert_id},
    )
    session.commit()
    return bool(result.rowcount)


def get_actions(
    session: Session,
    *,
    agent: str | Sequence[str] | None = None,
    status: str | None = None,
    alert_id: str | None = None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: dict[str, Any] = {}

    _agent_filter(agent, filters, params)
    if status:
        filters.append("status = :status")
        params["status"] = _normalize_status(status)
    if alert_id:
        filters.append("alert_id = :alert_id")
        params["alert_id"] = alert_id

    sql = """
        SELECT
            id,
            action,
            agent,
            routes,
            alert_id,
            status,
            spec,
            impact,
            reason,
            simulation_summary,
            created_at,
            run_id
        FROM chat.actions
    """
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY CASE WHEN created_at IS NULL THEN 1 ELSE 0 END, created_at DESC, id DESC"

    rows = []
    for row in _execute(session, sql, params).mappings().all():
        item = _row(row)
        summary = item.get("simulation_summary")
        if isinstance(summary, str):
            try:
                item["simulation_summary"] = json.loads(summary)
            except json.JSONDecodeError:
                pass
        rows.append(item)
    return rows


def get_action(
    session: Session,
    action_id: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT
                id,
                action,
                agent,
                routes,
                alert_id,
                status,
                spec,
                impact,
                simulation_summary,
                created_at,
                run_id
            FROM chat.actions
            WHERE id = :action_id
            """
        ),
        {"action_id": action_id},
    ).mappings().first()
    if not row:
        return None
    item = _row(row)
    summary = item.get("simulation_summary")
    if isinstance(summary, str):
        try:
            item["simulation_summary"] = json.loads(summary)
        except json.JSONDecodeError:
            pass
    return item


def save_action(
    session: Session,
    *,
    action: str,
    agent: str,
    routes: list[str],
    alert_id: str | None,
    spec: str | None = None,
    impact: str | None = None,
    status: str = ACTION_STATUS_PLANNED,
    run_id: int | None = None,
    commit: bool = True,
) -> str:
    """
    Insert one action and return its id.

    Pass commit=False when writing a batch; see save_alert for why.
    """
    action_id = str(uuid4())
    session.execute(
        text(
            """
            INSERT INTO chat.actions (
                id,
                action,
                agent,
                routes,
                alert_id,
                status,
                spec,
                impact,
                created_at,
                run_id
            )
            VALUES (
                :id,
                :action,
                :agent,
                :routes,
                :alert_id,
                :status,
                :spec,
                :impact,
                SYSUTCDATETIME(),
                :run_id
            )
            """
        ),
        {
            "id": action_id,
            "action": action,
            "agent": agent,
            "routes": json.dumps(routes),
            "alert_id": alert_id,
            "status": _normalize_status(status),
            "spec": spec,
            "impact": impact,
            "run_id": run_id,
        },
    )
    if commit:
        session.commit()
    return action_id


def save_actions(
    session: Session,
    actions: list[dict[str, Any]],
    *,
    run_id: int | None = None,
    commit: bool = True,
) -> list[str]:
    """
    Insert many actions in one executemany round trip and return their ids.

    Any alert_id referenced must already be inserted in this transaction.
    """
    if not actions:
        return []

    rows = [
        {
            "id": str(uuid4()),
            "action": item["action"],
            "agent": item["agent"],
            "routes": json.dumps(item.get("routes") or []),
            "alert_id": item.get("alert_id"),
            "status": _normalize_status(
                item.get("status", ACTION_STATUS_PLANNED)
            ),
            "spec": item.get("spec"),
            "impact": item.get("impact"),
            # The model's own justification for ranking this action first.
            # Prose only: `impact.clean_reason` strips any figure before it
            # reaches a screen, so this column never competes with the
            # computed numbers printed beside it (QC-055/QC-061).
            "reason": item.get("reason"),
            "run_id": run_id,
        }
        for item in actions
    ]
    session.execute(
        text(
            """
            INSERT INTO chat.actions (
                id,
                action,
                agent,
                routes,
                alert_id,
                status,
                spec,
                impact,
                reason,
                created_at,
                run_id
            )
            VALUES (
                :id,
                :action,
                :agent,
                :routes,
                :alert_id,
                :status,
                :spec,
                :impact,
                :reason,
                SYSUTCDATETIME(),
                :run_id
            )
            """
        ),
        rows,
    )
    if commit:
        session.commit()
    return [row["id"] for row in rows]


def update_action_status(
    session: Session,
    action_id: str,
    status: str,
) -> dict[str, Any] | None:
    normalized = _normalize_status(status)
    result = session.execute(
        text(
            """
            UPDATE chat.actions
            SET status = :status
            WHERE id = :action_id
            """
        ),
        {
            "action_id": action_id,
            "status": normalized,
        },
    )
    session.commit()
    if not result.rowcount:
        return None
    return get_action(session, action_id)


def update_action_simulation_summary(
    session: Session,
    action_id: str,
    simulation_summary: Any,
) -> dict[str, Any] | None:
    result = session.execute(
        text(
            """
            UPDATE chat.actions
            SET simulation_summary = :simulation_summary
            WHERE id = :action_id
            """
        ),
        {
            "action_id": action_id,
            "simulation_summary": _dump_json(simulation_summary),
        },
    )
    session.commit()
    if not result.rowcount:
        return None
    return get_action(session, action_id)


def delete_action(
    session: Session,
    action_id: str,
) -> bool:
    result = session.execute(
        text("DELETE FROM chat.actions WHERE id = :action_id"),
        {"action_id": action_id},
    )
    session.commit()
    return bool(result.rowcount)


def clear_alerts(
    session: Session,
    *,
    agent: str | Sequence[str] | None = None,
) -> dict[str, int]:
    """
    Delete alerts and their related actions.

    When agent is set, only that domain is cleared. Actions are removed first
    so orphaned rows cannot remain if CASCADE is absent.

    The agent may be given as every key it answers to (QC-020). Clearing has to
    cover the same rows the list shows, or a reset leaves the older short-key
    rows on screen and appears to do nothing.
    """
    params: dict[str, Any] = {}
    action_sql = "DELETE FROM chat.actions"
    alert_sql = "DELETE FROM chat.alerts"

    if agent:
        params["agents"] = [agent] if isinstance(agent, str) else list(agent)
        action_sql += """
            WHERE agent IN :agents
               OR alert_id IN (
                    SELECT id FROM chat.alerts WHERE agent IN :agents
               )
        """
        alert_sql += " WHERE agent IN :agents"

    actions_deleted = _execute(session, action_sql, params).rowcount
    alerts_deleted = _execute(session, alert_sql, params).rowcount
    session.commit()
    return {
        "alerts_deleted": int(alerts_deleted or 0),
        "actions_deleted": int(actions_deleted or 0),
    }


def try_advisory_lock(connection: Any, key: str) -> bool:
    """
    Attempt a session-scoped Azure SQL application lock keyed by `key`, non-blocking.

    Session-scoped, not transaction-scoped: it must outlive the several
    commits `populate_alerts` makes while it runs, and it is released
    explicitly by `advisory_unlock`, not by a transaction boundary. The lock
    is tied to the underlying connection (`sp_getapplock` with
    `@LockOwner='Session'`), so `connection` must be the same physical
    connection for the whole lock/unlock pair — see `service.populate_alerts`
    for why that rules out an ORM `Session`.
    """
    result = connection.execute(
        text(
            """
            DECLARE @result INT;
            EXEC @result = sp_getapplock
                @Resource = :key,
                @LockMode = 'Exclusive',
                @LockOwner = 'Session',
                @LockTimeout = 0;
            SELECT @result;
            """
        ),
        {"key": key},
    ).scalar()
    # sp_getapplock returns >= 0 on success, negative on failure/timeout.
    return result is not None and result >= 0


def advisory_unlock(connection: Any, key: str) -> None:
    """Release the lock taken by `try_advisory_lock` on the same connection."""
    connection.execute(
        text("EXEC sp_releaseapplock @Resource = :key, @LockOwner = 'Session';"),
        {"key": key},
    )


def create_monitoring_run(connection: Any, *, agent: str) -> int:
    """
    Insert a STARTED `chat.monitoring_runs` row and return its id.

    Takes a raw Connection, not a Session, so it can share the physical
    connection the advisory lock is held on for the whole populate_alerts run.
    """
    run_id = connection.execute(
        text(
            """
            INSERT INTO chat.monitoring_runs (agent, run_status, started_at)
            OUTPUT INSERTED.id
            VALUES (:agent, 'STARTED', SYSUTCDATETIME())
            """
        ),
        {"agent": agent},
    ).scalar_one()
    connection.commit()
    return int(run_id)


def complete_monitoring_run(
    connection: Any,
    run_id: int,
    *,
    monitoring_passes: int,
    alerts_created: int,
    actions_created: int,
) -> None:
    connection.execute(
        text(
            """
            UPDATE chat.monitoring_runs
            SET run_status = 'COMPLETED',
                completed_at = SYSUTCDATETIME(),
                monitoring_passes = :monitoring_passes,
                alerts_created = :alerts_created,
                actions_created = :actions_created
            WHERE id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "monitoring_passes": monitoring_passes,
            "alerts_created": alerts_created,
            "actions_created": actions_created,
        },
    )
    connection.commit()


def fail_monitoring_run(connection: Any, run_id: int, *, error_message: str) -> None:
    connection.execute(
        text(
            """
            UPDATE chat.monitoring_runs
            SET run_status = 'FAILED',
                completed_at = SYSUTCDATETIME(),
                error_message = :error_message
            WHERE id = :run_id
            """
        ),
        # Truncated: an unbounded traceback string has no business filling a
        # TEXT column meant for "what failed", and this keeps one runaway
        # error from bloating the row.
        {"run_id": run_id, "error_message": (error_message or "")[:4000]},
    )
    connection.commit()


__all__ = [
    "ACTION_STATUS_APPROVED",
    "ACTION_STATUS_PLANNED",
    "ALLOWED_ACTION_STATUSES",
    "advisory_unlock",
    "clear_alerts",
    "complete_monitoring_run",
    "create_monitoring_run",
    "delete_action",
    "delete_alert",
    "fail_monitoring_run",
    "get_action",
    "get_actions",
    "get_alert",
    "get_alerts",
    "save_action",
    "save_actions",
    "save_alert",
    "save_alerts",
    "try_advisory_lock",
    "update_action_simulation_summary",
    "update_action_status",
]
