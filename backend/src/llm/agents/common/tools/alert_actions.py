"""Cross-agent alert/action plan tools (list, simulate, approve).

RESOLVING AN ACTION
-------------------
simulate and approve both act on a row already in chat.actions, so the caller
has to name one. A title is matched exactly, then as a substring in either
direction -- the agent's phrasing is usually longer than the stored title, not
shorter, so a one-directional test misses the ordinary case.

Matching never reaches into `spec`. The SKU ids, vendor names and thresholds an
action turns on live there, which makes spec text tempting to match on and
dangerous to match on: the same SKU appears in several specs, and a near miss
would silently simulate the wrong remediation. So an unresolved name returns
every stored action with its id and spec instead of guessing, in the shape
formula_tools uses for a missing formula id -- the recovery the agent needs is
just the right id, so hand it over rather than raising. Raising is worse than
unhelpful here: a plain exception from a tool aborts the whole pydantic-ai run
(pipeline.py catches it and reports failure), so the agent never reads the
message and cannot correct itself.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.tools.db import _read_connection, _rows

# How many stored actions travel back on an unresolved name, and how much of
# each spec. The spec excerpt is what lets the agent map "DGT-046" onto the
# action that targets it, so it has to be long enough to carry the ids.
_CANDIDATE_LIMIT = 25
_SPEC_EXCERPT = 220

# A stored title is only matched inside a longer request when it is specific
# enough for the containment to mean something. "Clarify accuracy KPI" landing
# in a long question is a coincidence; "CFO approval: switch sourcing on top
# DGT SKUs" is a reference. Short titles stay fully reachable by exact match
# and by a quoted fragment -- they are only excluded from this one direction.
_CONTAINABLE_TITLE_CHARS = 24
_CONTAINABLE_TITLE_WORDS = 4


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
            SELECT TOP (:limit) id, name, subagent, agent, issue, date_created
            FROM chat.alerts
            WHERE :agent = ''
               OR lower(agent) LIKE '%' + lower(:agent) + '%'
               OR lower(subagent) LIKE '%' + lower(:agent) + '%'
            ORDER BY date_created DESC
            """,
            {"agent": agent_filter, "limit": limit},
        )
        alert_ids = [str(alert["id"]) for alert in alerts]
        actions = (
            _rows(
                connection,
                """
                SELECT TOP (200) id, alert_id, action, agent, routes, status,
                       spec, impact, reason, simulation_summary, created_at
                FROM chat.actions
                WHERE CAST(alert_id AS NVARCHAR(64)) IN :alert_ids
                ORDER BY created_at
                """,
                {"alert_ids": alert_ids},
                expand=("alert_ids",),
            )
            if alert_ids
            else []
        )
        unlinked_actions = _rows(
            connection,
            """
            SELECT TOP (20) id, action, agent, routes, status, spec, impact, reason,
                   simulation_summary, created_at
            FROM chat.actions
            WHERE alert_id IS NULL
            ORDER BY created_at DESC
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


class UnresolvedAction(LookupError):
    """A named action did not resolve to exactly one stored row.

    Carries the payload the tool returns instead of raising, so the agent gets
    the stored ids back and can retry with one.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(str(payload.get("error") or "Action not resolved."))
        self.payload = payload


def _title(item: dict[str, Any]) -> str:
    return str(item.get("action") or "").strip()


def _is_containable(title: str) -> bool:
    """Whether finding this title inside a longer request means anything."""

    return (
        len(title) >= _CONTAINABLE_TITLE_CHARS
        and len(title.split()) >= _CONTAINABLE_TITLE_WORDS
    )


def _digest(item: dict[str, Any]) -> dict[str, Any]:
    """One stored action, trimmed to what choosing between them needs."""

    spec = " ".join(str(item.get("spec") or "").split())
    if len(spec) > _SPEC_EXCERPT:
        spec = spec[:_SPEC_EXCERPT].rstrip() + "..."
    return {
        "action_id": str(item.get("id")),
        "action": _title(item),
        "agent": item.get("agent"),
        "status": item.get("status"),
        "routes": list(item.get("routes") or []),
        "spec": spec,
    }


def _unresolved(
    *,
    error: str,
    candidates: list[dict[str, Any]],
    requested_action: str,
    requested_action_id: str,
) -> UnresolvedAction:
    """Build the retry payload: the failure, then every id worth trying."""

    return UnresolvedAction(
        {
            "error": error,
            "resolved": False,
            "requested_action": requested_action,
            "requested_action_id": requested_action_id,
            "stored_action_count": len(candidates),
            "stored_actions": [
                _digest(item) for item in candidates[:_CANDIDATE_LIMIT]
            ],
            "truncated": len(candidates) > _CANDIDATE_LIMIT,
            "note_to_agent": (
                "The action was not resolved, so nothing was simulated, "
                "approved or changed. This is not a data source outage and "
                "the stored actions below are live. An action's SKU ids, "
                "vendors and thresholds live in its spec, not in its title, "
                "so do not compose a title from the user's wording. Read the "
                "specs, pick the action that covers what the user asked "
                "about, and call again with its action_id. Never repeat this "
                "call unchanged. If no stored action covers the request, tell "
                "the user no such action is stored rather than simulating a "
                "neighbouring one."
            ),
        }
    )


def _resolve_action(
    session: Any,
    *,
    action_id: str = "",
    action: str = "",
) -> dict[str, Any]:
    """Resolve a stored action by id, falling back to title match.

    Raises UnresolvedAction, carrying the stored ids, when a name matches no
    action or more than one. Callers return its payload rather than letting it
    propagate.
    """

    from src.actions import repository

    action_id = (action_id or "").strip()
    action_title = (action or "").strip()

    if action_id:
        found = repository.get_action(session, action_id)
        if found is not None:
            return found
        raise _unresolved(
            error=f"Action {action_id!r} was not found.",
            candidates=repository.get_actions(session),
            requested_action=action_title,
            requested_action_id=action_id,
        )

    if not action_title:
        raise ValueError(
            "Provide action_id or action title so the action can be resolved."
        )

    candidates = repository.get_actions(session)
    wanted = action_title.lower()

    exact = [item for item in candidates if _title(item).lower() == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise _unresolved(
            error=(
                f"Multiple stored actions are titled {action_title!r}. "
                "Pass action_id to say which one."
            ),
            candidates=exact,
            requested_action=action_title,
            requested_action_id=action_id,
        )

    # Both directions: the agent may quote a fragment of a stored title, or
    # wrap the whole title in a sentence of its own.
    partial = [
        item
        for item in candidates
        if (title := _title(item).lower())
        and (
            wanted in title
            or (_is_containable(title) and title in wanted)
        )
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise _unresolved(
            error=(
                f"Several stored actions match {action_title!r}. "
                "Pass action_id to say which one."
            ),
            candidates=partial,
            requested_action=action_title,
            requested_action_id=action_id,
        )

    raise _unresolved(
        error=(
            f"No stored action matches {action_title!r}. Titles are matched "
            "as stored; a title composed from the request will not match."
        ),
        candidates=candidates,
        requested_action=action_title,
        requested_action_id=action_id,
    )


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

    Pass action_id whenever you have it. A title is matched against stored
    titles only: an action's SKU ids, vendors and thresholds live in its spec,
    so a title composed from the user's wording will not resolve. When it does
    not, the result carries `resolved: false` and every stored action with its
    action_id and spec; pick one from there and call again.

    Args:
        action_id: Identifier of the action being simulated, when known.
        action: Title of the action being simulated.
        question: What the user wants to understand about the impact.
    """

    from src.actions import service as actions_service
    from src.db.db import session_scope

    with session_scope() as session:
        try:
            resolved = _resolve_action(
                session,
                action_id=action_id,
                action=action,
            )
        except UnresolvedAction as unresolved:
            return unresolved.payload
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

    Pass action_id whenever you have it. A title is matched against stored
    titles only. When it does not resolve, the result carries `resolved: false`
    and every stored action with its action_id; nothing is approved in that
    case, so pick one from the list and call again.

    Args:
        action_id: Identifier of the approved action, when known.
        action: Title of the approved action.
        note: Any condition or instruction the user attached.
    """

    from src.actions import service as actions_service
    from src.db.db import session_scope

    with session_scope() as session:
        try:
            resolved = _resolve_action(
                session,
                action_id=action_id,
                action=action,
            )
        except UnresolvedAction as unresolved:
            return unresolved.payload
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
    "UnresolvedAction",
    "get_alert_action_plan",
    "simulate_action_impact",
    "request_action_approval",
    "_resolve_action",
]
