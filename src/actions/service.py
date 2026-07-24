"""Alert/action workflow service: list, approve, simulate, populate."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy.orm import Session

from src.actions import repository
from src.actions.monitoring_registry import (
    MONITORING_PASSES_BY_DOMAIN,
    MonitoringPass,
    monitoring_passes_for,
)
from src.llm.chivon_impl import get_chivon
from src.llm.tools.freeform_query import (
    CASHFLOW_ALLOWED_TABLES,
    COLLECTIONS_ALLOWED_TABLES,
    FINANCE_ALLOWED_TABLES,
    LEAKAGE_ALLOWED_TABLES,
    reset_simulation_domain,
    set_simulation_domain,
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

# Snapshot + schema fetchers per domain. populate_alerts calls these ONCE and
# hands the result to every monitoring pass, so the passes do not each spend
# two LLM round trips (and two remote DB calls) fetching identical data.
_DOMAIN_SNAPSHOT: dict[str, tuple[str, str]] = {
    "finance": (
        "get_financial_performance_snapshot",
        "describe_financial_performance_tables",
    ),
    "cashflow": (
        "get_cashflow_baseline",
        "describe_cashflow_tables",
    ),
    "collection": (
        # Snapshot plus precomputed concentration/aging/utilization/scenario
        # aggregates, so a pass does not spend a round trip deriving them.
        "get_collections_monitoring_context",
        "describe_collections_tables",
    ),
    "leakage": (
        "get_payment_leakage_snapshot",
        "describe_payment_leakage_tables",
    ),
}

# Importer agent that owns audit.import_batches rows per domain. Simulation
# gets the latest completed batch id up front so the agent does not spend
# LLM round trips rediscovering it.
_DOMAIN_IMPORT_AGENT: dict[str, str] = {
    "finance": "financial_performance_agent",
    "cashflow": "cashflow_agent",
    "collection": "collections_credit_agent",
    "leakage": "payment_leakage_fraud_agent",
}

# Outer retries when the simulation agent run fails hard. Soft tool errors
# are recovered inside the agent; previous_error is fed on each outer retry.
SIMULATE_MAX_ATTEMPTS = 3


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
    Build the simulate/execute allow-list JSON with live column names.

    Thin wrapper over the cached schema lookup so callers can pass domain
    aliases such as 'collections' or 'treasury'.
    """
    from src.llm.tools.freeform_query import allowed_data_for_domain

    return allowed_data_for_domain(_normalize_agent(agent))


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


def list_actions(
    session: Session,
    *,
    agent: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List stored actions (history), optionally filtered by domain or status."""
    normalized = _normalize_agent(agent) if agent else None
    return repository.get_actions(
        session,
        agent=normalized,
        status=status,
    )


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


def _alert_row(
    *,
    domain: str,
    alert: dict[str, Any],
    subagent_name: str,
) -> dict[str, Any]:
    """Normalize one agent alert into an insertable row, no DB access."""
    return {
        "name": str(alert.get("name") or "")[:120],
        "subagent": str(alert.get("subagent") or subagent_name)[:50],
        "agent": domain,
        "issue": str(alert.get("issue") or ""),
    }


def _action_rows(
    *,
    domain: str,
    alert: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize an alert's action specs into insertable rows, no DB access."""
    rows: list[dict[str, Any]] = []
    for action in alert.get("actions") or []:
        if not isinstance(action, dict):
            if hasattr(action, "model_dump"):
                action = action.model_dump(mode="json")
            else:
                continue
        action_name = str(action.get("name") or "").strip()
        if not action_name or action_name.lower() == "no action":
            continue
        rows.append(
            {
                "action": action_name[:120],
                "agent": domain,
                "routes": list(action.get("routes") or []),
                "alert_id": None,  # filled once the alert id is known
                "status": repository.ACTION_STATUS_PLANNED,
                "spec": action.get("spec"),
                "impact": action.get("impact"),
            }
        )
    return rows


def _persist_run(
    session: Session,
    *,
    pending: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """
    Write a whole monitoring run: one executemany per table, one commit.

    Row-at-a-time inserts cost a network round trip each, which against a
    remote Postgres dominated the persistence phase.
    """
    if not pending:
        session.commit()
        return []

    alert_ids = repository.save_alerts(
        session,
        [alert_row for alert_row, _ in pending],
        commit=False,
    )

    action_rows: list[dict[str, Any]] = []
    for alert_id, (_, rows) in zip(alert_ids, pending):
        for row in rows:
            row["alert_id"] = alert_id
            action_rows.append(row)

    action_ids = repository.save_actions(
        session,
        action_rows,
        commit=False,
    )
    session.commit()

    for action_id, row in zip(action_ids, action_rows):
        row["id"] = action_id

    saved: list[dict[str, Any]] = []
    for alert_id, (alert_row, rows) in zip(alert_ids, pending):
        saved.append({"id": alert_id, **alert_row, "actions": rows})
    return saved


async def _prefetch_domain_context(
    domain: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Read the domain snapshot and live table schema once per populate run.

    Both reads are blocking DB calls, so they run in worker threads and in
    parallel with each other. A failure here is not fatal: the monitoring
    agents still hold the snapshot/describe tools and can fetch it themselves.
    """
    from src.llm.tools import LOCAL_TOOLS

    snapshot_tool, schema_tool = _DOMAIN_SNAPSHOT[domain]

    async def _call(tool_name: str) -> dict[str, Any] | None:
        tool = LOCAL_TOOLS.get(tool_name)
        if tool is None:
            return None
        try:
            return await asyncio.to_thread(tool)
        except Exception:  # noqa: BLE001
            return None

    snapshot, schema = await asyncio.gather(
        _call(snapshot_tool),
        _call(schema_tool),
    )
    return snapshot, schema


async def populate_alerts(
    session: Session,
    agent: str,
) -> dict[str, Any]:
    """
    Run all specialized monitoring agents for a domain concurrently.

    Every monitor receives the same previous_alerts snapshot (alerts already
    stored for the domain) so specialists avoid duplicates against known
    issues. Agent runs happen in parallel; DB persistence is sequential.
    """
    domain = _normalize_agent(agent)
    passes = monitoring_passes_for(domain)
    chivon = get_chivon()

    previous_alerts = [
        _prior_from_stored(item)
        for item in repository.get_alerts(session, agent=domain)
    ]
    previous_count = len(previous_alerts)
    allowed_tables = list(_DOMAIN_TABLES[domain])
    domain_snapshot, table_schema = await _prefetch_domain_context(domain)

    async def _run_pass(monitoring_pass: MonitoringPass) -> dict[str, Any]:
        payload = {
            "subagent_name": monitoring_pass.agent_name,
            "instructions": monitoring_pass.instructions,
            "allowed_tables": allowed_tables,
            "previous_alerts": list(previous_alerts),
            "domain_snapshot": domain_snapshot,
            "table_schema": table_schema,
        }
        try:
            result = await chivon.run_async(
                monitoring_pass.agent_name,
                payload,
            )
            output = _dump_output(result.output)
            return {
                "monitoring_pass": monitoring_pass,
                "raw_alerts": output.get("alerts") or [],
                "error": None,
            }
        except Exception as error:  # noqa: BLE001
            return {
                "monitoring_pass": monitoring_pass,
                "raw_alerts": [],
                "error": str(error),
            }

    run_outputs = await asyncio.gather(
        *[_run_pass(monitoring_pass) for monitoring_pass in passes]
    )

    # Collect every row first, then write the whole run in two executemany
    # statements. Row-at-a-time inserts cost a round trip each.
    pending: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    pass_spans: list[tuple[dict[str, Any], int, int]] = []
    pass_results: list[dict[str, Any]] = []

    for run_output in run_outputs:
        monitoring_pass = run_output["monitoring_pass"]
        raw_alerts = run_output["raw_alerts"]
        pass_error = run_output["error"]
        start = len(pending)

        for raw in raw_alerts:
            if hasattr(raw, "model_dump"):
                alert = raw.model_dump(mode="json")
            elif isinstance(raw, dict):
                alert = raw
            else:
                continue
            if _is_none_alert(alert):
                continue
            pending.append(
                (
                    _alert_row(
                        domain=domain,
                        alert=alert,
                        subagent_name=monitoring_pass.agent_name,
                    ),
                    _action_rows(domain=domain, alert=alert),
                )
            )

        pass_entry: dict[str, Any] = {
            "monitoring_agent": monitoring_pass.agent_name,
            "instructions": monitoring_pass.instructions,
            "previous_alert_count": previous_count,
            "created_count": len(pending) - start,
            "alerts": [],
        }
        if pass_error:
            pass_entry["error"] = pass_error
        pass_results.append(pass_entry)
        pass_spans.append((pass_entry, start, len(pending)))

    created_alerts = _persist_run(session, pending=pending)

    for pass_entry, start, end in pass_spans:
        pass_entry["alerts"] = created_alerts[start:end]

    return {
        "agent": domain,
        "monitoring_passes": len(passes),
        "created_count": len(created_alerts),
        "items": created_alerts,
        "passes": pass_results,
    }


async def _prefetch_simulation_context(
    domain: str,
) -> tuple[dict[str, Any] | None, int | None, dict[str, Any] | None]:
    """
    Read schema, latest import batch id, and the domain snapshot per simulation.

    All three are blocking DB reads, so they run in worker threads in parallel.
    None of them is fatal: the agent keeps describe_*/query_* tools and can
    fetch what is missing itself. The snapshot is what removes the agent's
    discovery round trips, since it already carries the rows a spec refers to.
    """
    from src.llm.tools import LOCAL_TOOLS
    from src.llm.tools.finance_data import latest_import_batch_id
    from src.llm.tools.freeform_query import allowed_data_for_domain

    async def _schema() -> dict[str, Any] | None:
        try:
            return await asyncio.to_thread(allowed_data_for_domain, domain)
        except Exception:  # noqa: BLE001
            return None

    async def _batch_id() -> int | None:
        importer = _DOMAIN_IMPORT_AGENT.get(domain)
        if importer is None:
            return None
        try:
            return await asyncio.to_thread(latest_import_batch_id, importer)
        except Exception:  # noqa: BLE001
            return None

    async def _snapshot() -> dict[str, Any] | None:
        snapshot_tool, _ = _DOMAIN_SNAPSHOT[domain]
        tool = LOCAL_TOOLS.get(snapshot_tool)
        if tool is None:
            return None
        try:
            return await asyncio.to_thread(tool)
        except Exception:  # noqa: BLE001
            return None

    table_schema, import_batch_id, domain_snapshot = await asyncio.gather(
        _schema(),
        _batch_id(),
        _snapshot(),
    )
    return table_schema, import_batch_id, domain_snapshot


def _simulation_blocks(output: Any) -> list[dict[str, Any]]:
    """
    Render the agent's table/chart components into UI blocks.

    Same renderer the chat pipeline uses, so the alerts panel can display a
    simulation with the components the chat agent produces.
    """
    from src.llm.html_renderer import render_ui_blocks

    components = getattr(output, "components", None) or []
    if not components:
        return []
    try:
        return [block.model_dump() for block in render_ui_blocks(components)]
    except Exception:  # noqa: BLE001
        return []


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
    (
        table_schema,
        import_batch_id,
        domain_snapshot,
    ) = await _prefetch_simulation_context(domain)
    base_payload = {
        "action_name": str(action["action"]),
        "spec": spec,
        "agent": domain,
        "impact": action.get("impact") or None,
        "allowed_tables": sorted(_DOMAIN_TABLES[domain]),
        "domain_snapshot": domain_snapshot,
        "table_schema": table_schema,
        "import_batch_id": import_batch_id,
    }

    previous_error: str | None = None
    summary_payload: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []

    scope_token = set_simulation_domain(domain)
    try:
        for attempt in range(1, SIMULATE_MAX_ATTEMPTS + 1):
            payload = dict(base_payload)
            if previous_error:
                payload["previous_error"] = previous_error
            try:
                result = await chivon.run_async(agent_name, payload)
                summary_payload = _dump_output(result.output)
                attempts.append(
                    {
                        "attempt": attempt,
                        "ok": True,
                        "previous_error": previous_error,
                    }
                )
                break
            except Exception as error:  # noqa: BLE001
                previous_error = str(error)
                attempts.append(
                    {
                        "attempt": attempt,
                        "ok": False,
                        "error": previous_error,
                    }
                )
                if attempt >= SIMULATE_MAX_ATTEMPTS:
                    raise
    finally:
        reset_simulation_domain(scope_token)

    assert summary_payload is not None

    metrics_json = summary_payload.get("metrics_json")
    if isinstance(metrics_json, str) and metrics_json.strip():
        try:
            summary_payload["metrics"] = json.loads(metrics_json)
        except json.JSONDecodeError:
            summary_payload["metrics"] = metrics_json

    summary_payload["simulate_attempts"] = attempts
    summary_payload["blocks"] = _simulation_blocks(result.output)
    # Components are stored as rendered blocks; keep the payload lean.
    summary_payload.pop("components", None)

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
    "list_actions",
    "list_actions_for_alert",
    "list_alerts",
    "list_monitoring_agents",
    "populate_alerts",
    "simulate_action",
]
