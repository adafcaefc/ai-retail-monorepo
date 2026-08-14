from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.llm.chivon import chivon


from src.llm.html_renderer import UiBlock, render_ui_blocks
from src.llm.suggested_response_context import (
    extract_current_assistant_text,
)
from src.retrieval.gateway import ChatRetrievalGateway
from src.retrieval.grounding import (
    build_grounding_packet,
    grounding_notice,
    validate_citations,
)
from src.retrieval.models import RetrievalResponse

logger = logging.getLogger(__name__)

# The retrieval service caches the local embedding provider.  Keep the normal
# gateway alive across chat turns so a new BGE model is not loaded for every
# Retail message.  Tests and callers can still inject a gateway explicitly.
_DEFAULT_RETAIL_GATEWAY = ChatRetrievalGateway()


@dataclass
class StructuredResult:
    """
    Result returned back to FastAPI.
    """
    blocks: list[UiBlock]
    source_agent: str
    assistant_text: str = ""
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
    *,
    retrieval_response: RetrievalResponse | None = None,
    retrieval_gateway: ChatRetrievalGateway | None = None,
) -> StructuredResult:

    FinanceAgentOutput = chivon.type(
        "FinanceAgentOutput"
    )

    input_payload = dict(_build_messages_input(messages_input))
    if retrieval_response is None and agent_name.startswith("retail."):
        query = _latest_user_query(input_payload)
        if query:
            try:
                conversation_context = [
                    str(line.get("text", ""))
                    for line in input_payload.get("lines", [])[-6:]
                    if isinstance(line, dict)
                ]
                gateway = retrieval_gateway or _DEFAULT_RETAIL_GATEWAY
                retrieval_response = await asyncio.to_thread(
                    gateway.retrieve,
                    query,
                    conversation_context=conversation_context,
                    agent_context=agent_name,
                )
            except Exception as exc:
                logger.warning("chat retrieval gateway failed for %s: %s", agent_name, exc)
                return StructuredResult(
                    blocks=[],
                    source_agent=agent_name,
                    success=False,
                    error="Retail retrieval is temporarily unavailable.",
                )

    grounding = None
    if retrieval_response is not None:
        grounding = build_grounding_packet(retrieval_response)
        input_payload["retrieval_context"] = grounding.text
        if retrieval_response.status.value == "FAILED" or not grounding.citation_ids:
            notice = grounding_notice(
                retrieval_response,
                missing_evidence=not grounding.citation_ids,
            )
            return StructuredResult(
                blocks=[UiBlock(type="html", data=notice)],
                source_agent=agent_name,
                success=False,
                error="No verified retrieval evidence was available.",
            )

    try:
        _log(f"running {agent_name}")

        agent_result = _output(
            await chivon.run_async(
                agent_name,
                input_payload,
            )
        )

    except Exception as exc:

        _log(f"{agent_name} failed: {exc}")

        return StructuredResult(
            blocks=[],
            source_agent=agent_name,
            success=False,
            error=f"{agent_name} failed: {exc}",
        )

    if not isinstance(
        agent_result,
        FinanceAgentOutput,
    ):
        return StructuredResult(
            blocks=[],
            source_agent=agent_name,
            success=False,
            error=(
                f"{agent_name} returned invalid output: "
                f"{type(agent_result)}"
            ),
        )

    if grounding is not None:
        citation_check = validate_citations(
            agent_result.model_dump(mode="json"),
            grounding.citation_ids,
            require_reference=bool(grounding.citation_ids),
        )
        if not citation_check.valid:
            notice = grounding_notice(
                retrieval_response,
                invalid_ids=citation_check.invalid_ids,
                missing_citation=citation_check.missing_required,
            )
            return StructuredResult(
                blocks=[UiBlock(type="html", data=notice)],
                source_agent=agent_name,
                success=False,
                error=(
                    "Generated answer omitted required verified citations."
                    if citation_check.missing_required
                    else "Generated answer contained unverified citation identifiers: "
                    + ", ".join(citation_check.invalid_ids)
                ),
            )

    _log(
        f"{agent_name} produced "
        f"{len(agent_result.components)} components"
        f"component preview: {agent_result.components}"
    )

    assistant_text = extract_current_assistant_text(
        agent_result.components
    )

    blocks = render_ui_blocks(
        agent_result.components
    )

    if retrieval_response is not None and retrieval_response.status.value in {"PARTIAL", "FAILED"}:
        notice = grounding_notice(retrieval_response)
        if notice.get("html"):
            blocks.insert(0, UiBlock(type="html", data=notice))

    return StructuredResult(
        blocks=blocks,
        source_agent=agent_name,
        assistant_text=assistant_text,
        success=True,
    )


def _latest_user_query(messages_input: dict[str, Any]) -> str:
    lines = messages_input.get("lines", [])
    for line in reversed(lines if isinstance(lines, list) else []):
        if isinstance(line, dict) and line.get("sender") == "user":
            return str(line.get("text", "")).strip()
    return ""
