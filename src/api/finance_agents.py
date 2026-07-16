from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.llm.pipeline import render_agent_response


router = APIRouter(
    prefix="/api/finance-agents",
    tags=["Finance Agents"],
)


class MessageLine(BaseModel):
    sender: str = Field(..., examples=["user"])
    text: str


class TeamsContext(BaseModel):
    teamId: str | None = None
    channelId: str | None = None
    messageId: str | None = None
    parentMessageId: str | None = None
    replyToId: str | None = None


class RenderAgentRequest(BaseModel):
    agent_name: str

    context: TeamsContext | None = None

    lines: list[MessageLine] | None = None

    messages: list[dict[str, Any]] | None = None


class RenderAgentResponse(BaseModel):
    success: bool
    sourceAgent: str
    error: str = ""

    context: TeamsContext | None = None

    adaptiveCard: dict[str, Any] | None = None


@router.post(
    "/render",
    response_model=RenderAgentResponse,
)
async def render_finance_agent(
    request: RenderAgentRequest,
) -> RenderAgentResponse:

    if request.lines:
        messages_input = {
            "lines": [
                line.model_dump()
                for line in request.lines
            ]
        }

    elif request.messages:
        messages_input = {
            "lines": [
                {
                    "sender": (
                        "assistant"
                        if msg.get("from", {})
                            .get("application")
                        else "user"
                    ),
                    "text": (
                        msg.get("body", {})
                        .get("content", "")
                    ),
                }
                for msg in request.messages
            ]
        }

    else:
        return RenderAgentResponse(
            success=False,
            sourceAgent=request.agent_name,
            error="No messages received.",
        )

    result = await render_agent_response(
        agent_name=request.agent_name,
        messages_input=messages_input,
    )

    return RenderAgentResponse(
        success=result.success,
        sourceAgent=result.source_agent,
        error=result.error,
        context=request.context,
        adaptiveCard=result.adaptive_card,
    )