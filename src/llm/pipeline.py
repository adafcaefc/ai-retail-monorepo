from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.llm.agents.chivon import chivon
from src.llm.adaptive_cards import (
    render_finance_agent_output,
    validate_adaptive_card,
)




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
    validate_adaptive_card(adaptive_card)


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
        Deterministic Renderer
                ↓
          Adaptive Card
                ↓
             Return
    """



    FinanceAgentOutput = chivon.type(
        "FinanceAgentOutput"
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
    # Render and validate adaptive card deterministically
    # --------------------------------------------------

    try:
        adaptive_card = render_finance_agent_output(
            agent_result
        )
        _validate_adaptive_card(
            adaptive_card
        )
        card_output = json.dumps(
            adaptive_card,
            ensure_ascii=False,
        )
    except Exception as exc:
        _log(
            f"adaptive card rendering failed: {exc}"
        )

        return RenderedResult(
            card_output="",
            source_agent=agent_name,
            success=False,
            error=(
                "adaptive card rendering failed: "
                f"{exc}"
            ),
        )

    _log("render successful")

    # --------------------------------------------------
    # Step 3
    # Return card
    # --------------------------------------------------

    return RenderedResult(
        card_output=card_output,
        source_agent=agent_name,
        success=True,
        adaptive_card=adaptive_card,
    )