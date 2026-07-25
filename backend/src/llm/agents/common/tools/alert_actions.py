"""Cross-agent alert/action plan tools (list, simulate, approve)."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.tools.db import _read_connection, _rows


def get_alert_action_plan(
    agent: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Return recent stored alerts with the routed actions planned for each."""

    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50.")
    agent_filter = agent.strip()

    with _read_connection() as connection:
        alerts = _rows(
            connection,
            """
            SELECT id, name, subagent, agent, issue, date_created
            FROM chat.alerts
            WHERE :agent = ''
               OR lower(agent) LIKE '%' || lower(:agent) || '%'
               OR lower(subagent) LIKE '%' || lower(:agent) || '%'
            ORDER BY date_created DESC
            LIMIT :limit
            """,
            {"agent": agent_filter, "limit": limit},
        )
        alert_ids = [str(alert["id"]) for alert in alerts]
        actions = (
            _rows(
                connection,
                """
                SELECT id, alert_id, action, agent, routes, status,
                       spec, impact, simulation_summary, created_at
                FROM chat.actions
                WHERE alert_id::text = ANY(:alert_ids)
                ORDER BY created_at
                LIMIT 200
                """,
                {"alert_ids": alert_ids},
            )
            if alert_ids
            else []
        )
        unlinked_actions = _rows(
            connection,
            """
            SELECT id, action, agent, routes, status, spec, impact,
                   simulation_summary, created_at
            FROM chat.actions
            WHERE alert_id IS NULL
            ORDER BY created_at DESC
            LIMIT 20
            """,
            {},
        )

    actions_by_alert: dict[str, list[dict[str, Any]]] = {}
    for action in actions:
        alert_id = str(action.pop("alert_id"))
        actions_by_alert.setdefault(alert_id, []).append(action)

    return {
        "agent_filter": agent_filter,
        "alert_count": len(alerts),
        "alerts": [
            {
                **alert,
                "actions": actions_by_alert.get(str(alert["id"]), []),
            }
            for alert in alerts
        ],
        "unlinked_actions": unlinked_actions,
        "note": (
            "Each action carries its own status and routing owners. An "
            "action is only executed once its owner records approval."
        ),
    }


def _resolve_action(
    session: Any,
    *,
    action_id: str = "",
    action: str = "",
) -> dict[str, Any]:
    """Resolve a stored action by id, falling back to title match."""

    from src.actions import repository

    action_id = (action_id or "").strip()
    action_title = (action or "").strip()

    if action_id:
        found = repository.get_action(session, action_id)
        if found is None:
            raise LookupError(f"Action {action_id!r} was not found.")
        return found

    if not action_title:
        raise ValueError(
            "Provide action_id or action title so the action can be resolved."
        )

    candidates = repository.get_actions(session)
    exact = [
        item
        for item in candidates
        if str(item.get("action") or "").strip().lower()
        == action_title.lower()
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        ids = ", ".join(str(item["id"]) for item in exact[:5])
        raise ValueError(
            f"Multiple actions titled {action_title!r}. "
            f"Pass action_id. Candidates: {ids}"
        )

    partial = [
        item
        for item in candidates
        if action_title.lower() in str(item.get("action") or "").lower()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        ids = ", ".join(str(item["id"]) for item in partial[:5])
        raise ValueError(
            f"Multiple actions match {action_title!r}. "
            f"Pass action_id. Candidates: {ids}"
        )
    raise LookupError(f"No stored action matches {action_title!r}.")


async def simulate_action_impact(
    action_id: str = "",
    action: str = "",
    question: str = "",
) -> dict[str, Any]:
    """Run the impact simulation for an action before any approval.

    Call this whenever the user wants to understand what an action would
    do: its impact, effect, consequence, result, upside, downside, risk,
    or any what-if about applying it. Also call it as the first step when
    the user approves or asks to execute an action, so the simulation is
    shown before approval is confirmed. Do not wait for the user to say
    the word simulation.

    Args:
        action_id: Identifier of the action being simulated, when known.
        action: Title of the action being simulated.
        question: What the user wants to understand about the impact.
    """

    from src.actions import service as actions_service
    from src.db.db import session_scope

    with session_scope() as session:
        resolved = _resolve_action(
            session,
            action_id=action_id,
            action=action,
        )
        result = await actions_service.simulate_action(
            session,
            str(resolved["id"]),
        )

    simulation = result.get("simulation") or {}
    updated = result.get("action") or {}
    return {
        "received": True,
        "action_id": str(updated.get("id") or resolved["id"]),
        "action": updated.get("action") or resolved.get("action"),
        "question": question,
        "status": "SIMULATED",
        "action_status": updated.get("status") or resolved.get("status"),
        "impact": updated.get("impact") or resolved.get("impact"),
        "simulation": simulation,
        "simulation_summary": updated.get("simulation_summary"),
        "note_to_agent": (
            "Present the simulation summary and metrics as the simulated "
            "impact for this action. Distinguish the owner's stored impact "
            "estimate from the freshly simulated figures. Ask the user to "
            "confirm before calling request_action_approval."
        ),
    }


def request_action_approval(
    action_id: str = "",
    action: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Mark a stored action as approved after the user confirms.

    Call this whenever the user confirms approval after a simulation was
    already presented for the same action. The action status is set to
    approved in the database. Nothing is executed; execution remains with
    the domain execution agent after approval.

    Args:
        action_id: Identifier of the approved action, when known.
        action: Title of the approved action.
        note: Any condition or instruction the user attached.
    """

    from src.actions import service as actions_service
    from src.db.db import session_scope

    with session_scope() as session:
        resolved = _resolve_action(
            session,
            action_id=action_id,
            action=action,
        )
        updated = actions_service.approve_action(
            session,
            str(resolved["id"]),
        )

    return {
        "received": True,
        "action_id": str(updated["id"]),
        "action": updated.get("action"),
        "note": note,
        "status": "APPROVED",
        "action_status": updated.get("status"),
        "routes": list(updated.get("routes") or []),
        "impact": updated.get("impact"),
        "simulation_summary": updated.get("simulation_summary"),
        "note_to_agent": (
            "The action status is now approved in storage. Do not imply "
            "the remediation was executed. Report the approved status and "
            "routing owners; execution still requires the execution agent."
        ),
    }


COMMON_ALERT_ACTION_TOOLS = {
    "get_alert_action_plan": get_alert_action_plan,
    "simulate_action_impact": simulate_action_impact,
    "request_action_approval": request_action_approval,
}


__all__ = [
    "COMMON_ALERT_ACTION_TOOLS",
    "get_alert_action_plan",
    "simulate_action_impact",
    "request_action_approval",
    "_resolve_action",
]
