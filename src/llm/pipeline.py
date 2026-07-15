from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.llm.chivon_impl import load_chivon
from src.llm.agents.chivon import chivon


@dataclass
class RenderedResult:
    """
    Result returned back to FastAPI / Logic Apps.

    Logic Apps are responsible for posting
    Adaptive Cards to Teams.
    """

    card_output: str
    source_agent: str
    success: bool = True
    error: str = ""

    adaptive_card: dict[str, Any] | None = None


def _log(msg: str) -> None:
    print(
        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [finance-pipeline] {msg}",
        flush=True,
    )


def _output(result: Any) -> Any:
    return result.output if hasattr(result, "output") else result


def _build_messages_input(
    user_request: dict[str, Any],
) -> dict[str, Any]:
    """
    Supports:

    {
        "user": "hello"
    }

    or

    {
        "lines": [...]
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
        "Expected either {'user': ...} or {'lines': [...]} format."
    )


def _parse_card_output(
    card_output: str,
) -> dict[str, Any]:
    """
    RendererOutput.card_output may be:

    1. JSON string
    2. Double encoded JSON string

    Converts to dict.
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


def _validate_adaptive_card(
    adaptive_card: dict[str, Any],
) -> None:

    if adaptive_card.get("type") != "AdaptiveCard":
        raise ValueError(
            "adaptive_card['type'] must be 'AdaptiveCard'."
        )

    if "body" not in adaptive_card:
        raise ValueError(
            "Adaptive Card must contain a body."
        )

    if not isinstance(adaptive_card["body"], list):
        raise ValueError(
            "Adaptive Card body must be a list."
        )

    adaptive_card.setdefault(
        "$schema",
        "http://adaptivecards.io/schemas/adaptive-card.json",
    )

    adaptive_card.setdefault(
        "version",
        "1.5",
    )


async def render_agent_response(
    agent_name: str,
    messages_input: dict[str, Any],
) -> RenderedResult:
    """
    Pipeline:

        Specialist Agent
                ↓
        FinanceAgentOutput
                ↓
         Renderer Agent
                ↓
          Adaptive Card
                ↓
             Return
    """

    load_chivon()

    FinanceAgentOutput = chivon.type(
        "FinanceAgentOutput"
    )

    RendererOutput = chivon.type(
        "RendererOutput"
    )

    # --------------------------------------------------
    # Step 1
    # Run selected specialist agent
    # --------------------------------------------------

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

    if not isinstance(
        agent_result,
        FinanceAgentOutput,
    ):
        return RenderedResult(
            card_output="",
            source_agent=agent_name,
            success=False,
            error=(
                f"{agent_name} returned invalid output: "
                f"{type(agent_result)}"
            ),
        )

    _log(
        f"{agent_name} produced "
        f"{len(agent_result.components)} components"
    )

    # --------------------------------------------------
    # Step 2
    # Render adaptive card
    # --------------------------------------------------

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

    if not isinstance(
        renderer_result,
        RendererOutput,
    ):
        return RenderedResult(
            card_output="",
            source_agent=agent_name,
            success=False,
            error=(
                "renderer returned invalid output: "
                f"{type(renderer_result)}"
            ),
        )

    _log("render successful")

    # --------------------------------------------------
    # Step 3
    # Parse card
    # --------------------------------------------------

    try:
        adaptive_card = _parse_card_output(
            renderer_result.card_output
        )

        _validate_adaptive_card(
            adaptive_card
        )

    except Exception as exc:
        _log(
            f"adaptive card validation failed: {exc}"
        )

        return RenderedResult(
            card_output=renderer_result.card_output,
            source_agent=agent_name,
            success=False,
            error=(
                "adaptive card validation failed: "
                f"{exc}"
            ),
        )

    # --------------------------------------------------
    # Step 4
    # Return card
    # --------------------------------------------------

    return RenderedResult(
        card_output=renderer_result.card_output,
        source_agent=agent_name,
        success=True,
        adaptive_card=adaptive_card,
    )