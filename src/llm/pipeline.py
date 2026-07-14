from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from src.llm.chivon_impl import load_chivon
from src.llm.agents.chivon import chivon


@dataclass
class RenderedResult:
    """Final rendered output ready for Teams."""

    card_output: str
    source_agent: str
    success: bool = True
    error: str = ""
    teams_status_code: int | None = None
    teams_response: str = ""


def _log(msg: str) -> None:
    print(
        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [finance-pipeline] {msg}",
        flush=True,
    )


def _output(result: Any) -> Any:
    return result.output if hasattr(result, "output") else result

def _build_messages_input(
    user_request: dict[str, Any]
) -> dict[str, Any]:

    # Already messages format
    if "lines" in user_request:
        return user_request

    # Old format:
    # {"user": "..."}
    if "user" in user_request:
        return {
            "lines": [
                {
                    "sender": "user",
                    "text": user_request["user"]
                }
            ]
        }

    raise ValueError(
        "Expected either {'user': ...} or MessagesInput format."
    )


def _parse_card_output(card_output: str) -> dict[str, Any]:
    """
    RendererOutput.card_output is currently a string.

    Sometimes the model returns:
    1. A normal JSON string
    2. A double-encoded JSON string

    This safely parses until the result is a dict.
    """

    parsed: Any = card_output

    if isinstance(parsed, str):
        parsed = json.loads(parsed)

    if isinstance(parsed, str):
        parsed = json.loads(parsed)

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Parsed adaptive card must be dict, got {type(parsed)}"
        )

    return parsed


def _send_adaptive_card_to_teams(
    adaptive_card: dict[str, Any],
) -> tuple[int, str]:
    """
    Sends the Adaptive Card to Power Automate.

    Power Automate currently expects payload:
    {
        "adaptiveCard": { ... }
    }

    because the Teams action uses:
    string(variables('Body')?['adaptiveCard'])
    """

    webhook_url = os.getenv("TEAMS_POWER_AUTOMATE_WEBHOOK_URL")

    if not webhook_url:
        raise RuntimeError(
            "Missing TEAMS_POWER_AUTOMATE_WEBHOOK_URL environment variable."
        )

    payload = adaptive_card

    response = requests.post(
        webhook_url,
        json=payload,
        headers={
            "Content-Type": "application/json"
        },
        timeout=30,
    )

    return response.status_code, response.text


async def render_agent_response(
    agent_name: str,
    messages_input: dict[str, Any],
    send_to_teams: bool = True,
) -> RenderedResult:
    """
    Runs:

        Selected Agent
            ↓
        FinanceAgentOutput
            ↓
        Renderer Agent
            ↓
        RendererOutput
            ↓
        Optional Teams send
    """

    # Safe to call multiple times if your loader is idempotent.
    load_chivon()

    FinanceAgentOutput = chivon.type("FinanceAgentOutput")
    RendererOutput = chivon.type("RendererOutput")

    # Step 1: Execute selected specialist agent
    try:
        _log(f"running {agent_name}")



        agent_result = _output(
            await chivon.run_async(
                agent_name,
                messages_input,
            )
        )


    except Exception as exc:
        _log(f"{agent_name} failed: {exc}")

        return RenderedResult(
            card_output="",
            source_agent=agent_name,
            success=False,
            error=f"{agent_name} failed: {exc}",
        )

    if not isinstance(agent_result, FinanceAgentOutput):
        return RenderedResult(
            card_output="",
            source_agent=agent_name,
            success=False,
            error=f"{agent_name} returned invalid output: {type(agent_result)}",
        )

    _log(
        f"{agent_name} produced "
        f"{len(agent_result.components)} components"
    )

    # Step 2: Render adaptive card
    try:
        renderer_result = _output(
            await chivon.run_async(
                "renderer_agent",
                agent_result,
            )
        )

    except Exception as exc:
        _log(f"renderer failed: {exc}")

        return RenderedResult(
            card_output="",
            source_agent=agent_name,
            success=False,
            error=f"renderer failed: {exc}",
        )

    if not isinstance(renderer_result, RendererOutput):
        return RenderedResult(
            card_output="",
            source_agent=agent_name,
            success=False,
            error=f"renderer returned invalid output: {type(renderer_result)}",
        )

    _log("render successful")

    # Step 3: Validate card JSON
    try:
        adaptive_card = _parse_card_output(
            renderer_result.card_output
        )

        assert adaptive_card["type"] == "AdaptiveCard"
        assert "body" in adaptive_card
        assert isinstance(adaptive_card["body"], list)

    except Exception as exc:
        _log(f"adaptive card validation failed: {exc}")

        return RenderedResult(
            card_output=renderer_result.card_output,
            source_agent=agent_name,
            success=False,
            error=f"adaptive card validation failed: {exc}",
        )

    # Step 4: Optionally send to Teams
    if send_to_teams:
        try:
            status_code, response_text = _send_adaptive_card_to_teams(
                adaptive_card
            )

            _log(f"Teams send status={status_code}")

            if status_code not in (200, 201, 202):
                return RenderedResult(
                    card_output=renderer_result.card_output,
                    source_agent=agent_name,
                    success=False,
                    error=f"Teams send failed with status {status_code}",
                    teams_status_code=status_code,
                    teams_response=response_text,
                )

            return RenderedResult(
                card_output=renderer_result.card_output,
                source_agent=agent_name,
                success=True,
                teams_status_code=status_code,
                teams_response=response_text,
            )

        except Exception as exc:
            _log(f"Teams send failed: {exc}")

            return RenderedResult(
                card_output=renderer_result.card_output,
                source_agent=agent_name,
                success=False,
                error=f"Teams send failed: {exc}",
            )

    return RenderedResult(
        card_output=renderer_result.card_output,
        source_agent=agent_name,
        success=True,
    )