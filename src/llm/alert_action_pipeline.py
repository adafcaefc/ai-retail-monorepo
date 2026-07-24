#pipeline for all things about alert and actions
"""
    Current flow
    1. Run all monitoring agents, each with different names, instructions, and allowed_data
    2. Store all alerts in database
    3. Group all alerts by parent agent
    4. Run each action agent, one for each main parent agent
    5. Store all actions

    List of current planned monitoring agents


"""

#imports
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.llm.agents.chivon import chivon
from src.actions.repository import save_alerts, save_actions
from sqlalchemy.orm import Session

def _log(msg: str) -> None:
    print(
        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [finance-pipeline] {msg}",
        flush=True,
    )


def _output(result: Any) -> Any:
    return result.output if hasattr(result, "output") else result


#monitoring
async def run_monitoring_pipeline(
    session: Session,
    monitoring_agents: dict,
) -> list:
    """
    Runs every monitoring agent,
    saves any generated alerts,
    and returns all saved alert records.
    """

    all_alerts = []

    for agent_name, config in monitoring_agents.items():

        agent_result = _output(
            await chivon.run_async(
                name="monitoring_agent",
                subagent_name= agent_name,
                instructions=config["instructions"],
                allowed_data=config["allowed_data"],
            )
        )

        alerts = [
            alert.model_dump()
            if hasattr(alert, "model_dump")
            else alert
            for alert in agent_result.alerts
        ]

        # New empty-alert format:
        # monitors return [] when no issues exist
        if not alerts:
            continue

        saved_alerts = save_alerts(
            session=session,
            alerts=alerts,
        )

        all_alerts.extend(saved_alerts)

    return all_alerts

#alerts
def group_alerts_by_parent(
    alerts: list,
) -> dict[str, list]:
    grouped_alerts = {}

    for alert in alerts:
        grouped_alerts.setdefault(
            alert.agent,
            [],
        ).append(alert)

    return grouped_alerts

async def run_action_agents(
    session: Session,
    grouped_alerts: dict[str, list],
    action_agents: dict,
):
    saved_actions = []

    for parent_agent, alerts in grouped_alerts.items():

        if parent_agent not in action_agents:
            continue

        config = action_agents[parent_agent]

        agent_result = _output(
            await chivon.run_async(
                name="action_agent",
                instructions=config["instructions"],
                parent_agent=parent_agent,
                alerts=[
                    {
                        "id": str(alert.id),
                        "name": alert.name,
                        "issue": alert.issue,
                        "subagent": alert.subagent,
                    }
                    for alert in alerts
                ],
            )
        )

        actions = [
            action.model_dump()
            if hasattr(action, "model_dump")
            else action
            for action in agent_result.actions
        ]

        #
        # No actions generated
        #
        if not actions:
            continue

        #
        # Remove "no action" placeholders
        #
        actions = [
            action
            for action in actions
            if action.get("action") != "no action"
        ]

        if not actions:
            continue

        saved_actions.extend(
            save_actions(
                session=session,
                actions=actions,
            )
        )

    return saved_actions

#main pipeline
async def run_finance_pipeline(
    session: Session,
    monitoring_agents: dict,
    action_agents: dict,
):
    #
    # Run monitoring agents and save alerts
    #
    saved_alerts = await run_monitoring_pipeline(
        session=session,
        monitoring_agents=monitoring_agents,
    )

    #
    # No alerts generated
    #
    if not saved_alerts:
        return {
            "alerts": [],
            "actions": [],
        }

    #
    # Group alerts by parent agent
    #
    grouped_alerts = group_alerts_by_parent(
        saved_alerts
    )

    #
    # Run action agents and save actions
    #
    saved_actions = await run_action_agents(
        session=session,
        grouped_alerts=grouped_alerts,
        action_agents=action_agents,
    )

    return {
        "alerts": saved_alerts,
        "actions": saved_actions,
    }