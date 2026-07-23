from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid

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
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

#helper
def _create_action(
    action: str,
    agent: str,
    routes: list[str],
    conversation_id: str | uuid.UUID,
    status: str,
) -> Action:
    return Action(
        action=action,
        agent=agent,
        routes=routes,
        conversation_id=conversation_id,
        status=status,
    )


#returns all actions, filtered by agent and status. returns all actions by default.
def get_actions(
    session: Session,
    agent: str | None = None,
    status: str | None = None,
):
    filters = []
    params = {}

    if agent:
        filters.append("agent = :agent")
        params["agent"] = agent

    if status:
        filters.append("status = :status")
        params["status"] = status

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
    conversation_id: str | uuid.UUID,
    status: str = "pending",
) -> str:

    record = _create_action(
        action=action,
        agent=agent,
        routes=routes,
        conversation_id=conversation_id,
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
            conversation_id=a["conversation_id"],
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