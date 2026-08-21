"""Raw-SQL repository for immutable Retail agent handoffs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


HANDOFF_COLUMNS = """
    handoff_id,
    source_agent,
    target_agent,
    handoff_type,
    status,
    scope_json,
    source_snapshot_date,
    source_import_batch_id,
    basket_hash,
    payload_json,
    created_at,
    updated_at
"""


def _json(value: str, field: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"Persisted handoff {field} is not valid JSON") from error


def _value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value.__class__.__name__ == "UUID":
        return str(value)
    return value


def _record(
    row: Mapping[str, Any],
    *,
    include_payload: bool = False,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = {key: _value(value) for key, value in dict(row).items()}
    result["handoff_id"] = str(result["handoff_id"]).lower()
    result["scope"] = _json(result.pop("scope_json"), "scope_json")
    payload_json = result.pop("payload_json", None)
    if include_payload:
        result["payload"] = _json(payload_json, "payload_json")
    if events is not None:
        result["events"] = events
    return result


def _event(row: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: _value(value) for key, value in dict(row).items()}
    result["handoff_id"] = str(result["handoff_id"]).lower()
    return result


def _events(session: Session, handoff_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT event_id, handoff_id, from_status, to_status, created_at
            FROM retail.agent_handoff_events
            WHERE handoff_id = :handoff_id
            ORDER BY event_id ASC
            """
        ),
        {"handoff_id": handoff_id},
    ).mappings().all()
    return [_event(row) for row in rows]


def get_handoff(
    session: Session,
    handoff_id: str,
    *,
    include_payload: bool = False,
) -> dict[str, Any] | None:
    row = session.execute(
        text(f"SELECT {HANDOFF_COLUMNS} FROM retail.agent_handoffs WHERE handoff_id = :handoff_id"),
        {"handoff_id": handoff_id},
    ).mappings().first()
    if row is None:
        return None
    return _record(
        row,
        include_payload=include_payload,
        events=_events(session, handoff_id),
    )


def find_sent_by_hash(
    session: Session,
    *,
    source_agent: str,
    target_agent: str,
    handoff_type: str,
    basket_hash: str,
) -> dict[str, Any] | None:
    row = session.execute(
        text(
            f"""
            SELECT TOP 1 {HANDOFF_COLUMNS}
            FROM retail.agent_handoffs
            WHERE source_agent = :source_agent
              AND target_agent = :target_agent
              AND handoff_type = :handoff_type
              AND basket_hash = :basket_hash
              AND status = N'sent'
            ORDER BY created_at DESC, handoff_id DESC
            """
        ),
        {
            "source_agent": source_agent,
            "target_agent": target_agent,
            "handoff_type": handoff_type,
            "basket_hash": basket_hash,
        },
    ).mappings().first()
    if row is None:
        return None
    return _record(row, events=_events(session, str(row["handoff_id"])))


def create_handoff(
    session: Session,
    *,
    source_agent: str,
    target_agent: str,
    handoff_type: str,
    status: str,
    scope_json: str,
    source_snapshot_date: date,
    source_import_batch_id: int | None,
    basket_hash: str,
    payload_json: str,
) -> dict[str, Any]:
    handoff_id = str(uuid4())
    session.execute(
        text(
            """
            INSERT INTO retail.agent_handoffs (
                handoff_id,
                source_agent,
                target_agent,
                handoff_type,
                status,
                scope_json,
                source_snapshot_date,
                source_import_batch_id,
                basket_hash,
                payload_json
            )
            VALUES (
                :handoff_id,
                :source_agent,
                :target_agent,
                :handoff_type,
                :status,
                :scope_json,
                :source_snapshot_date,
                :source_import_batch_id,
                :basket_hash,
                :payload_json
            )
            """
        ),
        {
            "handoff_id": handoff_id,
            "source_agent": source_agent,
            "target_agent": target_agent,
            "handoff_type": handoff_type,
            "status": status,
            "scope_json": scope_json,
            "source_snapshot_date": source_snapshot_date,
            "source_import_batch_id": source_import_batch_id,
            "basket_hash": basket_hash,
            "payload_json": payload_json,
        },
    )
    session.execute(
        text(
            """
            INSERT INTO retail.agent_handoff_events (
                handoff_id, from_status, to_status
            )
            VALUES (:handoff_id, NULL, :to_status)
            """
        ),
        {"handoff_id": handoff_id, "to_status": status},
    )
    session.commit()
    result = get_handoff(session, handoff_id, include_payload=False)
    if result is None:  # pragma: no cover - the insert committed successfully
        raise RuntimeError("Persisted handoff could not be read after creation")
    return result


def transition_handoff(
    session: Session,
    *,
    handoff_id: str,
    from_status: str,
    to_status: str,
) -> dict[str, Any] | None:
    """Atomically transition one row and append its event."""

    result = session.execute(
        text(
            """
            UPDATE retail.agent_handoffs
            SET status = :to_status,
                updated_at = SYSUTCDATETIME()
            WHERE handoff_id = :handoff_id
              AND status = :from_status
            """
        ),
        {
            "handoff_id": handoff_id,
            "from_status": from_status,
            "to_status": to_status,
        },
    )
    if result.rowcount != 1:
        session.rollback()
        return None

    session.execute(
        text(
            """
            INSERT INTO retail.agent_handoff_events (
                handoff_id, from_status, to_status
            )
            VALUES (:handoff_id, :from_status, :to_status)
            """
        ),
        {
            "handoff_id": handoff_id,
            "from_status": from_status,
            "to_status": to_status,
        },
    )
    session.commit()
    return get_handoff(session, handoff_id, include_payload=False)


def list_inbox(
    session: Session,
    *,
    target_agent: str,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            f"""
            SELECT {HANDOFF_COLUMNS}
            FROM retail.agent_handoffs
            WHERE target_agent = :target_agent
              AND status = N'sent'
            ORDER BY created_at DESC, handoff_id DESC
            """
        ),
        {"target_agent": target_agent},
    ).mappings().all()

    items: list[dict[str, Any]] = []
    for row in rows:
        record = _record(row, include_payload=False, events=None)
        payload = _json(row["payload_json"], "payload_json")
        record.update(
            {
                "as_of": payload.get("as_of"),
                "source": payload.get("source"),
                "grain": payload.get("grain"),
                "row_count": payload.get("row_count"),
                "action_row_count": payload.get("action_row_count"),
                "basket_forecast_7d": payload.get("basket_forecast_7d"),
                "dashboard_forecast_7d": payload.get("dashboard_forecast_7d"),
                "suggestion_units": payload.get("suggestion_units"),
            }
        )
        items.append(record)
    return items


__all__ = [
    "create_handoff",
    "find_sent_by_hash",
    "get_handoff",
    "list_inbox",
    "transition_handoff",
]
