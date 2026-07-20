from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.llm.agents.chivon import chivon




@dataclass
class StructuredResult:
    """
    Result returned back to FastAPI 
    """

    response_text: str
    source_agent: str
    success: bool = True
    error: str = ""



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




async def render_agent_response(
    agent_name: str,
    messages_input: dict[str, Any],
    ) -> StructuredResult:

    FinanceAgentOutput = chivon.type(
        "FinanceAgentOutput"
    )

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

        return StructuredResult(
            source_agent=agent_name,
            success=False,
            error=f"{agent_name} failed: {exc}",
        )

    if not isinstance(
        agent_result,
        FinanceAgentOutput,
    ):
        return StructuredResult(
            source_agent=agent_name,
            success=False,
            error=(
                f"{agent_name} returned invalid output: "
                f"{type(agent_result)}"
            ),
        )

    return StructuredResult(
        success=True,
        source_agent=agent_name,
        response_text=agent_result.html_output
    )