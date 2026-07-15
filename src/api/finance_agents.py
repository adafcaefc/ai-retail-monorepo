from __future__ import annotations

from typing import Any, Literal

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


class RenderAgentRequest(BaseModel):
    """
    Request body used by Logic Apps.

    Supports either:
    1. user: simple single-message prompt
    2. lines: conversation history
    """

    agent_name: str = Field(..., examples=["collections_agent"])

    user: str | None = Field(
        default=None,
        examples=["Show me a collections recovery scenario."],
    )

    lines: list[MessageLine] | None = None

    # If False, API returns the adaptive card to Logic App.
    # Logic App can then post it to Teams.
    #
    # If True, Python calls your separate Logic App Teams gateway directly.
    send_to_teams: bool = False

    message_type: Literal["new-card", "update-card"] = "new-card"

    # Used later for update-card flows
    message_id: str | None = None
    conversation_id: str | None = None

    # Useful for tracing Logic App runs, Teams messages, etc.
    correlation_id: str | None = None

    metadata: dict[str, Any] | None = None


class RenderAgentResponse(BaseModel):
    success: bool
    source_agent: str
    error: str = ""

    # Main object Logic Apps should use
    adaptiveCard: dict[str, Any] | None = None

    # Fully wrapped payload for your Teams gateway Logic App
    logicAppPayload: dict[str, Any] | None = None

    # Raw string output, useful for debugging
    cardOutput: str = ""

    teamsStatusCode: int | None = None
    teamsResponse: str = ""


@router.post("/render", response_model=RenderAgentResponse)
async def render_finance_agent(
    request: RenderAgentRequest,
) -> RenderAgentResponse:
    """
    Endpoint for Logic Apps.

    Typical Logic App A flow:

        Teams message trigger
            ↓
        Read message history
            ↓
        POST /api/finance-agents/render
            ↓
        Receive adaptiveCard
            ↓
        Post adaptive card to Teams

    Request examples:

    Simple:
    {
      "agent_name": "collections_agent",
      "user": "Create a collections recovery card"
    }

    With history:
    {
      "agent_name": "collections_agent",
      "lines": [
        {"sender": "user", "text": "Show collections recovery"},
        {"sender": "assistant", "text": "Sure."},
        {"sender": "user", "text": "Use balance 1000"}
      ]
    }
    """

    if request.lines:
        messages_input = {
            "lines": [
                line.model_dump()
                for line in request.lines
            ]
        }
    elif request.user:
        messages_input = {
            "lines": [
                {
                    "sender": "user",
                    "text": request.user,
                }
            ]
        }
    else:
        return RenderAgentResponse(
            success=False,
            source_agent=request.agent_name,
            error="Expected either 'user' or 'lines'.",
        )

    result = await render_agent_response(
        agent_name=request.agent_name,
        messages_input=messages_input,
        send_to_teams=request.send_to_teams,
        message_type=request.message_type,
        message_id=request.message_id,
        conversation_id=request.conversation_id,
        correlation_id=request.correlation_id,
        extra_metadata=request.metadata,
    )

    return RenderAgentResponse(
        success=result.success,
        source_agent=result.source_agent,
        error=result.error,
        adaptiveCard=result.adaptive_card,
        logicAppPayload=result.logic_app_payload,
        cardOutput=result.card_output,
        teamsStatusCode=result.teams_status_code,
        teamsResponse=result.teams_response,
    )