from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import requests

from src.llm.chivon_impl import load_chivon
from src.llm.agents.chivon import chivon


LogicAppMessageType = Literal["new-card", "update-card"]


@dataclass
class RenderedResult:
    """Final rendered output ready for API / Logic Apps / Teams."""

    card_output: str
    source_agent: str
    success: bool = True
    error: str = ""

    # Parsed Adaptive Card object
    adaptive_card: dict[str, Any] | None = None

    # Payload sent to Logic Apps
    logic_app_payload: dict[str, Any] | None = None

    # Logic Apps / Teams gateway response
    teams_status_code: int | None = None
    teams_response: str = ""


def _log(msg: str) -> None:
    print(
        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [finance-pipeline] {msg}",
        flush=True,
    )


def _output(result: Any) -> Any:
    return result.output if hasattr(result, "output") else result


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_messages_input(
    user_request: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalizes incoming request into the format expected by your agents.

    Supports:
    1. New format:
       {
         "lines": [
           {"sender": "user", "text": "..."}
         ]
       }

    2. Old/simple format:
       {
         "user": "..."
       }
    """

    if "lines" in user_request:
        return user_request

    if "user" in user_request:
        return {
            "lines": [
                {
                    "sender": "user",
                    "text": user_request["user"],
                }
            ]
        }

    raise ValueError(
        "Expected either {'user': ...} or {'lines': [...]} messages format."
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


def _validate_adaptive_card(adaptive_card: dict[str, Any]) -> None:
    """
    Basic validation before sending to Logic Apps / Teams.
    """

    if adaptive_card.get("type") != "AdaptiveCard":
        raise ValueError("adaptive_card['type'] must be 'AdaptiveCard'.")

    if "body" not in adaptive_card:
        raise ValueError("Adaptive Card must contain a 'body' field.")

    if not isinstance(adaptive_card["body"], list):
        raise ValueError("Adaptive Card 'body' must be a list.")

    # Optional but recommended default.
    adaptive_card.setdefault(
        "$schema",
        "http://adaptivecards.io/schemas/adaptive-card.json",
    )

    # Teams commonly supports 1.5 well.
    adaptive_card.setdefault("version", "1.5")


def _build_logic_app_card_payload(
    *,
    adaptive_card: dict[str, Any],
    agent_name: str,
    message_type: LogicAppMessageType = "new-card",
    message_id: str | None = None,
    conversation_id: str | None = None,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Standard payload expected by your Logic App Teams gateway.

    For new card:
    {
      "messageType": "new-card",
      "agent": "...",
      "adaptiveCard": {...}
    }

    For update card:
    {
      "messageType": "update-card",
      "agent": "...",
      "messageId": "...",
      "adaptiveCard": {...}
    }
    """

    payload: dict[str, Any] = {
        "messageType": message_type,
        "agent": agent_name,
        "timestampUtc": _utc_now_iso(),
        "adaptiveCard": adaptive_card,
    }

    if message_id:
        payload["messageId"] = message_id

    if conversation_id:
        payload["conversationId"] = conversation_id

    if correlation_id:
        payload["correlationId"] = correlation_id

    if extra:
        payload["metadata"] = extra

    return payload


def _get_logic_app_webhook_url() -> str:
    """
    Primary env var:
        LOGIC_APP_TEAMS_GATEWAY_URL

    Backward-compatible fallback:
        TEAMS_POWER_AUTOMATE_WEBHOOK_URL
    """

    webhook_url = (
        os.getenv("LOGIC_APP_TEAMS_GATEWAY_URL")
        or os.getenv("TEAMS_POWER_AUTOMATE_WEBHOOK_URL")
    )

    if not webhook_url:
        raise RuntimeError(
            "Missing LOGIC_APP_TEAMS_GATEWAY_URL environment variable. "
            "Fallback TEAMS_POWER_AUTOMATE_WEBHOOK_URL was also not found."
        )

    return webhook_url


def _send_payload_to_logic_app(
    payload: dict[str, Any],
) -> tuple[int, str]:
    """
    Sends a structured payload to your Logic App / Power Automate Teams gateway.

    Logic App should expect:
    {
      "messageType": "new-card" | "update-card",
      "agent": "...",
      "adaptiveCard": {...},
      "messageId": "..." optional
    }
    """

    webhook_url = _get_logic_app_webhook_url()

    response = requests.post(
        webhook_url,
        json=payload,
        headers={
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    return response.status_code, response.text


async def render_agent_response(
    agent_name: str,
    messages_input: dict[str, Any],
    send_to_teams: bool = False,
    message_type: LogicAppMessageType = "new-card",
    message_id: str | None = None,
    conversation_id: str | None = None,
    correlation_id: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
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
        Adaptive Card dict
            ↓
        Optional Logic App send

    send_to_teams=False is recommended when Logic App A calls this API
    and posts the card itself.

    send_to_teams=True is useful when Python should call your separate
    Logic App B / Teams gateway directly.
    """

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

        _validate_adaptive_card(adaptive_card)

    except Exception as exc:
        _log(f"adaptive card validation failed: {exc}")

        return RenderedResult(
            card_output=renderer_result.card_output,
            source_agent=agent_name,
            success=False,
            error=f"adaptive card validation failed: {exc}",
        )

    # Step 4: Build Logic Apps-ready payload
    logic_app_payload = _build_logic_app_card_payload(
        adaptive_card=adaptive_card,
        agent_name=agent_name,
        message_type=message_type,
        message_id=message_id,
        conversation_id=conversation_id,
        correlation_id=correlation_id,
        extra=extra_metadata,
    )

    # Step 5: Optionally send to Logic Apps Teams gateway
    if send_to_teams:
        try:
            status_code, response_text = _send_payload_to_logic_app(
                logic_app_payload
            )

            _log(f"Logic App send status={status_code}")

            if status_code not in (200, 201, 202):
                return RenderedResult(
                    card_output=renderer_result.card_output,
                    source_agent=agent_name,
                    success=False,
                    error=f"Logic App send failed with status {status_code}",
                    adaptive_card=adaptive_card,
                    logic_app_payload=logic_app_payload,
                    teams_status_code=status_code,
                    teams_response=response_text,
                )

            return RenderedResult(
                card_output=renderer_result.card_output,
                source_agent=agent_name,
                success=True,
                adaptive_card=adaptive_card,
                logic_app_payload=logic_app_payload,
                teams_status_code=status_code,
                teams_response=response_text,
            )

        except Exception as exc:
            _log(f"Logic App send failed: {exc}")

            return RenderedResult(
                card_output=renderer_result.card_output,
                source_agent=agent_name,
                success=False,
                error=f"Logic App send failed: {exc}",
                adaptive_card=adaptive_card,
                logic_app_payload=logic_app_payload,
            )

    # Return-only mode
    return RenderedResult(
        card_output=renderer_result.card_output,
        source_agent=agent_name,
        success=True,
        adaptive_card=adaptive_card,
        logic_app_payload=logic_app_payload,
    )