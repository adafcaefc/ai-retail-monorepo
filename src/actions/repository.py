from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid

#models

from pydantic import Base

class Action(Base):
    __tablename__ = "actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    action: Mapped[str] = mapped_column(String(50))
    agent: Mapped[str] = mapped_column(String(20))
    routes: Mapped[list[str]] = mapped_column(ARRAY(String))
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(String(25))
    subagent: Mapped[str] = mapped_column(String(50))
    agent: Mapped[str] = mapped_column(String(25))
    issue: Mapped[str] = mapped_column(String(200))

    date_created: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


#helpers
def _create_action(
    action: str,
    agent: str,
    routes: list[str],
    alert_id: str | uuid.UUID,
    status: str,
) -> Action:
    return Action(
        action=action,
        agent=agent,
        routes=routes,
        alert_id=alert_id,
        status=status,
    )


def _create_alert(
    name: str,
    subagent: str,
    agent: str,
    issue: str,
) -> Alert:
    return Alert(
        name=name,
        subagent=subagent,
        agent=agent,
        issue=issue,
    )



#returns all actions, filtered by agent, status, and alert_id. returns all actions by default.
def get_actions(
    session: Session,
    agent: str | None = None,
    status: str | None = None,
    alert_id: str| None = None,
):
    filters = []
    params = {}

    if agent:
        filters.append("agent = :agent")
        params["agent"] = agent

    if status:
        filters.append("status = :status")
        params["status"] = status

    if alert_id:
        filters.append("alert_id = :alert_id")
        params["alert_id"] = alert_id

    sql = """
        SELECT *
        FROM actions
    """

    if filters:
        sql += " WHERE " + " AND ".join(filters)

    result = session.execute(text(sql), params)

    return result.mappings().all()

#saves an action into a database
def save_action(
    session: Session,
    action: str,
    agent: str,
    routes: list[str],
    alert_id: str | uuid.UUID,
    status: str = "pending",
) -> str:

    record = _create_action(
        action=action,
        agent=agent,
        routes=routes,
        alert_id=alert_id,
        status=status,
    )

    session.add(record)
    session.commit()
    session.refresh(record)

    return str(record.id)

#bulk save actions
def save_actions(
    session: Session,
    actions: list[dict],
) -> list[str]:

    records = [
        _create_action(
            action=a["action"],
            agent=a["agent"],
            routes=a["routes"],
            alert_id=a["alert_id"],
            status=a.get("status", "pending"),
        )
        for a in actions
    ]

    session.add_all(records)
    session.commit()

    return [str(r.id) for r in records]

#updates the status of an action
def update_action_status(
    session: Session,
    action_id: str,
    status: str,
):
    record = session.get(Action, action_id)

    if record:
        record.status = status
        session.commit()

    return record

#bulk status updates for multiple actions
def update_action_statuses(
    session: Session,
    action_ids: list[str],
    status: str,
):
    (
        session.query(Action)
        .filter(Action.id.in_(action_ids))
        .update(
            {"status": status},
            synchronize_session=False,
        )
    )

    session.commit()

#delete one action by id (testing only)
def delete_action(
    session: Session,
    action_id: str | uuid.UUID,
):
    record = session.get(Action, action_id)

    if record:
        session.delete(record)
        session.commit()


#alert functions

#get alerts based on certain filters, or returns all alerts if no parameters given

def get_alerts(
    session: Session,
    agent: str | None = None,
    subagent: str | None = None,
    name: str | None = None,
):
    filters = []
    params = {}

    if agent:
        filters.append("agent = :agent")
        params["agent"] = agent

    if subagent:
        filters.append("subagent = :subagent")
        params["subagent"] = subagent

    if name:
        filters.append("name = :name")
        params["name"] = name

    sql = """
        SELECT *
        FROM alerts
    """

    if filters:
        sql += " WHERE " + " AND ".join(filters)

    result = session.execute(text(sql), params)

    return result.mappings().all()

#saves a single alert to the database
def save_alert(
    session: Session,
    name: str,
    subagent: str,
    agent: str,
    issue: str,
) -> str:

    record = _create_alert(
        name=name,
        subagent=subagent,
        agent=agent,
        issue=issue,
    )

    session.add(record)
    session.commit()
    session.refresh(record)

    return str(record.id)

#saving mulitple alerts to the database
def save_alerts(
    session: Session,
    alerts: list[dict],
) -> list[str]:

    records = [
        _create_alert(
            name=a["name"],
            subagent=a["subagent"],
            agent=a["agent"],
            issue=a["issue"],
        )
        for a in alerts
    ]

    session.add_all(records)
    session.commit()

    return [str(r.id) for r in records]

#get an alert by ID
def get_alert(
    session: Session,
    alert_id: str | uuid.UUID,
):
    return session.get(Alert, alert_id)

#delete an alert. only for testing
def delete_alert(
    session: Session,
    alert_id: str | uuid.UUID,
):
    record = session.get(Alert, alert_id)

    if record:
        session.delete(record)
        session.commit()

    return record
