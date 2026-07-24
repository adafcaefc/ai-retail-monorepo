"""Alert/action workflow service: list, approve, simulate, populate."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from src.actions import repository
from src.actions.monitoring_registry import (
    MONITORING_PASSES_BY_DOMAIN,
    monitoring_passes_for,
)
from src.llm.chivon_impl import get_chivon
from src.llm.tools.freeform_query import (
    CASHFLOW_ALLOWED_TABLES,
    COLLECTIONS_ALLOWED_TABLES,
    FINANCE_ALLOWED_TABLES,
    LEAKAGE_ALLOWED_TABLES,
)

DOMAIN_AGENTS = {
    "finance",
    "cashflow",
    "collection",
    "leakage",
}

_DOMAIN_TABLES: dict[str, tuple[str, ...]] = {
    "finance": FINANCE_ALLOWED_TABLES,
    "cashflow": CASHFLOW_ALLOWED_TABLES,
    "collection": COLLECTIONS_ALLOWED_TABLES,
    "leakage": LEAKAGE_ALLOWED_TABLES,
}

_SIMULATION_AGENT_BY_DOMAIN = {
    "finance": "finance_simulation_agent",
    "cashflow": "cashflow_simulation_agent",
    "collection": "collection_simulation_agent",
    "leakage": "leakage_simulation_agent",
}


def _normalize_agent(agent: str) -> str:
    value = agent.strip().lower()
    aliases = {
        "collections": "collection",
        "treasury": "cashflow",
    }
    value = aliases.get(value, value)
    if value not in DOMAIN_AGENTS:
        raise ValueError(
            f"Unsupported agent {agent!r}. "
            f"Allowed: {', '.join(sorted(DOMAIN_AGENTS))}."
        )
    return value


def allowed_data_for_agent(agent: str) -> dict[str, Any]:
    """
    Build simulate_impact allow-list JSON with live column names.

    Uses information_schema via describe_tables so invented columns fail
    validation before SQL execution.
    """
    from src.llm.tools.freeform_query import describe_tables

    domain = _normalize_agent(agent)
    schema = describe_tables(allowed_tables=_DOMAIN_TABLES[domain])
    allowed: dict[str, Any] = {}
    for table, columns in (schema.get("tables") or {}).items():
        allowed[table] = {
            "columns": {
                str(column["column"]): str(column.get("data_type") or "unknown")
                for column in columns
            }
        }
    return allowed


def list_monitoring_agents(
    agent: str | None = None,
) -> dict[str, Any]:
    """
    List specialized monitoring subagents.

    When agent is provided, return only that domain's ordered passes.
    When omitted, return all domains.
    """
    if agent is not None:
        domain = _normalize_agent(agent)
        domains = {domain: monitoring_passes_for(domain)}
    else:
        domains = MONITORING_PASSES_BY_DOMAIN

    items = []
    for domain, passes in domains.items():
        items.append(
            {
                "agent": domain,
                "count": len(passes),
                "monitoring_agents": [
                    {
                        "name": monitoring_pass.agent_name,
                        "instructions": monitoring_pass.instructions,
                        "order": index + 1,
                    }
                    for index, monitoring_pass in enumerate(passes)
                ],
            }
        )

    return {
        "items": items,
        "count": len(items),
    }


def list_alerts(
    session: Session,
    *,
    agent: str | None = None,
) -> list[dict[str, Any]]:
    normalized = _normalize_agent(agent) if agent else None
    return repository.get_alerts(session, agent=normalized)


def clear_alerts(
    session: Session,
    *,
    agent: str | None = None,
) -> dict[str, Any]:
    normalized = _normalize_agent(agent) if agent else None
    deleted = repository.clear_alerts(session, agent=normalized)
    return {
        "agent": normalized,
        **deleted,
    }


def list_actions_for_alert(
    session: Session,
    alert_id: str,
) -> list[dict[str, Any]]:
    alert = repository.get_alert(session, alert_id)
    if alert is None:
        raise LookupError(f"Alert {alert_id!r} was not found.")
    return repository.get_actions(session, alert_id=alert_id)


def approve_action(
    session: Session,
    action_id: str,
) -> dict[str, Any]:
    action = repository.get_action(session, action_id)
    if action is None:
        raise LookupError(f"Action {action_id!r} was not found.")
    updated = repository.update_action_status(
        session,
        action_id,
        repository.ACTION_STATUS_APPROVED,
    )
    if updated is None:
        raise LookupError(f"Action {action_id!r} was not found.")
    return updated


def _dump_output(output: Any) -> dict[str, Any]:
    if hasattr(output, "model_dump"):
        return output.model_dump(mode="json")
    if isinstance(output, dict):
        return output
    return {"summary": str(output)}


def _is_none_alert(alert: dict[str, Any]) -> bool:
    name = str(alert.get("name") or "").strip().lower()
    issue = str(alert.get("issue") or "").strip().lower()
    return name in {"none", "no alert"} or issue == "no alert detected"


def _prior_from_stored(alert: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(alert.get("name") or ""),
        "issue": str(alert.get("issue") or ""),
        "subagent": str(alert.get("subagent") or ""),
    }


def _prior_from_generated(alert: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(alert.get("name") or ""),
        "issue": str(alert.get("issue") or ""),
        "subagent": str(alert.get("subagent") or ""),
    }


def _persist_alert_with_actions(
    session: Session,
    *,
    domain: str,
    alert: dict[str, Any],
    subagent_name: str,
) -> dict[str, Any]:
    alert_id = repository.save_alert(
        session,
        name=str(alert.get("name") or "")[:120],
        subagent=str(alert.get("subagent") or subagent_name)[:50],
        agent=domain,
        issue=str(alert.get("issue") or ""),
    )
    saved_actions: list[dict[str, Any]] = []
    for action in alert.get("actions") or []:
        if not isinstance(action, dict):
            if hasattr(action, "model_dump"):
                action = action.model_dump(mode="json")
            else:
                continue
        action_name = str(action.get("name") or "").strip()
        if not action_name or action_name.lower() == "no action":
            continue
        action_id = repository.save_action(
            session,
            action=action_name[:120],
            agent=domain,
            routes=list(action.get("routes") or []),
            alert_id=alert_id,
            spec=action.get("spec"),
            impact=action.get("impact"),
            status=repository.ACTION_STATUS_PLANNED,
        )
        saved_actions.append(
            {
                "id": action_id,
                "action": action_name[:120],
                "agent": domain,
                "routes": list(action.get("routes") or []),
                "alert_id": alert_id,
                "status": repository.ACTION_STATUS_PLANNED,
                "spec": action.get("spec"),
                "impact": action.get("impact"),
            }
        )
    return {
        "id": alert_id,
        "name": str(alert.get("name") or ""),
        "subagent": str(alert.get("subagent") or subagent_name),
        "agent": domain,
        "issue": str(alert.get("issue") or ""),
        "actions": saved_actions,
    }


async def populate_alerts(
    session: Session,
    agent: str,
) -> dict[str, Any]:
    """
    Run all specialized monitoring agents for a domain sequentially.

    Each pass receives previous_alerts (existing DB alerts for the domain plus
    alerts created earlier in this run) so specialists avoid duplicates.
    """
    domain = _normalize_agent(agent)
    passes = monitoring_passes_for(domain)
    chivon = get_chivon()

    previous_alerts = [
        _prior_from_stored(item)
        for item in repository.get_alerts(session, agent=domain)
    ]
    created_alerts: list[dict[str, Any]] = []
    pass_results: list[dict[str, Any]] = []

    for monitoring_pass in passes:
        previous_count = len(previous_alerts)
        payload = {
            "subagent_name": monitoring_pass.agent_name,
            "instructions": monitoring_pass.instructions,
            "previous_alerts": list(previous_alerts),
        }
        try:
            result = await chivon.run_async(
                monitoring_pass.agent_name,
                payload,
            )
            output = _dump_output(result.output)
            raw_alerts = output.get("alerts") or []
            pass_error = None
        except Exception as error:  # noqa: BLE001
            raw_alerts = []
            pass_error = str(error)

        new_alerts: list[dict[str, Any]] = []
        for raw in raw_alerts:
            if hasattr(raw, "model_dump"):
                alert = raw.model_dump(mode="json")
            elif isinstance(raw, dict):
                alert = raw
            else:
                continue
            if _is_none_alert(alert):
                continue
            saved = _persist_alert_with_actions(
                session,
                domain=domain,
                alert=alert,
                subagent_name=monitoring_pass.agent_name,
            )
            new_alerts.append(saved)
            created_alerts.append(saved)
            previous_alerts.append(_prior_from_generated(alert))

        pass_entry: dict[str, Any] = {
            "monitoring_agent": monitoring_pass.agent_name,
            "instructions": monitoring_pass.instructions,
            "previous_alert_count": previous_count,
            "created_count": len(new_alerts),
            "alerts": new_alerts,
        }
        if pass_error:
            pass_entry["error"] = pass_error
        pass_results.append(pass_entry)

    return {
        "agent": domain,
        "monitoring_passes": len(passes),
        "created_count": len(created_alerts),
        "items": created_alerts,
        "passes": pass_results,
    }


async def simulate_action(
    session: Session,
    action_id: str,
) -> dict[str, Any]:
    action = repository.get_action(session, action_id)
    if action is None:
        raise LookupError(f"Action {action_id!r} was not found.")

    spec = (action.get("spec") or "").strip()
    if not spec:
        raise ValueError(
            f"Action {action_id!r} has no spec to simulate."
        )

    domain = _normalize_agent(str(action["agent"]))
    agent_name = _SIMULATION_AGENT_BY_DOMAIN[domain]
    chivon = get_chivon()
    payload = {
        "action_name": str(action["action"]),
        "spec": spec,
        "agent": domain,
        "impact": action.get("impact") or None,
        "allowed_data": allowed_data_for_agent(domain),
    }

    result = await chivon.run_async(agent_name, payload)
    summary_payload = _dump_output(result.output)

    metrics_json = summary_payload.get("metrics_json")
    if isinstance(metrics_json, str) and metrics_json.strip():
        try:
            summary_payload["metrics"] = json.loads(metrics_json)
        except json.JSONDecodeError:
            summary_payload["metrics"] = metrics_json

    updated = repository.update_action_simulation_summary(
        session,
        action_id,
        summary_payload,
    )
    if updated is None:
        raise LookupError(f"Action {action_id!r} was not found.")

    return {
        "action": updated,
        "simulation": summary_payload,
    }


__all__ = [
    "DOMAIN_AGENTS",
    "allowed_data_for_agent",
    "approve_action",
    "clear_alerts",
    "list_actions_for_alert",
    "list_alerts",
    "list_monitoring_agents",
    "populate_alerts",
    "simulate_action",
]
