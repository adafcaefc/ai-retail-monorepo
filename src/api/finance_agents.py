from __future__ import annotations

import hmac
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.cashflow import cards as cashflow_cards
from src.cashflow import service as cashflow_service
from src.cashflow.models import CashFlowSimulationRequest
from src.collections.cards import (
    build_collection_scenario_card,
    build_collections_snapshot_card,
)
from src.common.env import config
from src.db.db import get_db_session
from src.llm.pipeline import render_agent_response
from src.llm.tools.finance_data import (
    calculate_collection_scenario,
    get_collections_snapshot,
)


def verify_finance_webhook(
    provided_secret: Annotated[
        str | None,
        Header(alias="X-Teams-Webhook-Secret"),
    ] = None,
) -> None:
    expected_secret = config.TEAMS_WEBHOOK_SECRET
    if expected_secret and (
        provided_secret is None
        or not hmac.compare_digest(provided_secret, expected_secret)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid Teams webhook secret.",
        )


router = APIRouter(
    prefix="/api/finance-agents",
    tags=["Finance Agents"],
    dependencies=[Depends(verify_finance_webhook)],
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


_SIMULATION_ENVELOPE_KEYS = (
    "body",
    "data",
    "response",
    "adaptiveCardResponse",
    "submitAction",
)


def _json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_simulation_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    pending: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (payload, {})
    ]
    visited: set[int] = set()

    while pending:
        candidate, inherited = pending.pop(0)
        identity = id(candidate)
        if identity in visited:
            continue
        visited.add(identity)

        scalar_values = {
            key: value
            for key, value in candidate.items()
            if key not in _SIMULATION_ENVELOPE_KEYS
            and isinstance(value, (str, int, float, bool))
        }
        merged = {**inherited, **scalar_values}
        if candidate.get("action") and candidate.get("source_agent"):
            return {**merged, **candidate}

        for key in _SIMULATION_ENVELOPE_KEYS:
            nested = _json_object(candidate.get(key))
            if nested is not None:
                pending.append((nested, merged))

    raise ValueError(
        "Simulation payload does not contain action and source_agent. "
        "Send the Adaptive Card response data or the complete Power Automate "
        "wait-for-response output."
    )


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
                        "chatbot"
                        if (msg.get("from") or {}).get("application")
                        else "user"
                    ),
                    "text": (
                        msg.get("body", {})
                        .get("content", "")
                    ),
                }
                for msg in request.messages
                if msg.get("messageType") == "message"
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


@router.get(
    "/collections/adaptive-card",
    response_model=RenderAgentResponse,
)
def get_collections_adaptive_card() -> RenderAgentResponse:
    try:
        adaptive_card = build_collections_snapshot_card(
            get_collections_snapshot()
        )
        return RenderAgentResponse(
            success=True,
            sourceAgent="collection_agent",
            adaptiveCard=adaptive_card,
        )
    except Exception as error:
        return RenderAgentResponse(
            success=False,
            sourceAgent="collection_agent",
            error=str(error),
        )


@router.post(
    "/simulations/recalculate",
    response_model=RenderAgentResponse,
)
def recalculate_finance_simulation(
    payload: dict[str, Any],
    session: Session = Depends(get_db_session),
) -> RenderAgentResponse:
    source_agent = "unknown"

    try:
        simulation_payload = _extract_simulation_payload(payload)
        source_agent = str(simulation_payload["source_agent"])
        action = str(simulation_payload["action"])

        if source_agent == "Cashflow" and action in {
            "simulate_cashflow",
            "recalculate_simulation",
        }:
            request = CashFlowSimulationRequest.model_validate(
                simulation_payload
            )
            baseline = cashflow_service.get_baseline(session)
            result = cashflow_service.simulate(request, session)
            adaptive_card = cashflow_cards.build_cashflow_simulation_card(
                baseline,
                request,
                result,
            )
            return RenderAgentResponse(
                success=True,
                sourceAgent="cashflow_agent",
                adaptiveCard=adaptive_card,
            )

        if source_agent == "Collections" and action in {
            "calculate_collection_scenario",
            "recalculate_simulation",
        }:
            result = calculate_collection_scenario(
                customer_name=str(
                    simulation_payload.get("customer_name")
                    or "Customer A"
                ),
                cash_to_collect_idr_mn=float(
                    simulation_payload["cash_to_collect_idr_mn"]
                ),
                discount_pct=float(
                    simulation_payload.get("discount_pct") or 0
                ),
            )
            return RenderAgentResponse(
                success=True,
                sourceAgent="collection_agent",
                adaptiveCard=build_collection_scenario_card(result),
            )

        raise ValueError(
            f"Unsupported simulation action {action!r} for {source_agent!r}."
        )
    except (KeyError, TypeError, ValueError) as error:
        return RenderAgentResponse(
            success=False,
            sourceAgent=source_agent,
            error=str(error),
        )