from __future__ import annotations

import hmac
import json
from html.parser import HTMLParser
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
    agent_name: str | None = None

    context: TeamsContext | None = None

    lines: list[MessageLine] | None = None

    messages: list[dict[str, Any]] | None = None


class RenderAgentResponse(BaseModel):
    success: bool
    sourceAgent: str
    error: str = ""

    context: TeamsContext | None = None

    adaptiveCard: dict[str, Any] | None = None


class _TeamsHTMLTextExtractor(HTMLParser):
    _BREAK_TAGS = {
        "br",
        "div",
        "li",
        "ol",
        "p",
        "table",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join("".join(self.parts).split())


def _plain_teams_body(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    content = body.get("content")
    if not isinstance(content, str):
        return ""
    if str(body.get("contentType") or "").lower() != "html":
        return content.strip()

    parser = _TeamsHTMLTextExtractor()
    parser.feed(content)
    parser.close()
    return parser.text()


def _adaptive_card_text(value: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        if value.get("type") == "TextBlock" and isinstance(
            value.get("text"),
            str,
        ):
            texts.append(value["text"])
        for child in value.values():
            texts.extend(_adaptive_card_text(child))
    elif isinstance(value, list):
        for child in value:
            texts.extend(_adaptive_card_text(child))
    return texts


def _teams_attachment_text(attachments: Any) -> str:
    if not isinstance(attachments, list):
        return ""
    texts: list[str] = []
    for attachment in attachments:
        if not isinstance(attachment, dict) or attachment.get(
            "contentType"
        ) != "application/vnd.microsoft.card.adaptive":
            continue
        content = attachment.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                continue
        texts.extend(_adaptive_card_text(content))
    return " ".join(" ".join(texts).split())


def _teams_message_text(message: dict[str, Any]) -> str:
    body_text = _plain_teams_body(message.get("body"))
    if body_text:
        return body_text
    return _teams_attachment_text(message.get("attachments"))


def _select_teams_thread(
    messages: list[dict[str, Any]],
    context: TeamsContext | None,
) -> list[dict[str, Any]]:
    message_rows = [
        message
        for message in messages
        if isinstance(message, dict)
        and message.get("messageType") == "message"
    ]

    if context is not None and context.messageId:
        current_message = next(
            (
                message
                for message in message_rows
                if str(message.get("id") or "") == context.messageId
            ),
            None,
        )
        current_reply_to = (
            str(current_message.get("replyToId") or "")
            if current_message is not None
            else ""
        )
        root_message_id = (
            context.parentMessageId
            or context.replyToId
            or current_reply_to
            or context.messageId
        )
        thread_rows = [
            message
            for message in message_rows
            if str(message.get("id") or "")
            in {context.messageId, root_message_id}
            or str(message.get("replyToId") or "") == root_message_id
        ]
        if thread_rows:
            message_rows = thread_rows

    return sorted(
        message_rows,
        key=lambda message: (
            str(message.get("createdDateTime") or ""),
            str(message.get("id") or ""),
        ),
    )


def _build_teams_lines(
    messages: list[dict[str, Any]],
    context: TeamsContext | None,
) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for message in _select_teams_thread(messages, context):
        text = _teams_message_text(message)
        if not text:
            continue
        lines.append(
            {
                "sender": (
                    "chatbot"
                    if (message.get("from") or {}).get("application")
                    else "user"
                ),
                "text": text,
            }
        )
    return lines


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



CHANNEL_AGENT_MAP = {
    config.FINANCE_CHANNEL_ID: "finance_agent",
    config.TREASURY_CHANNEL_ID: "cashflow_agent",
    config.COLLECTIONS_CHANNEL_ID: "collection_agent",
    config.LEAKAGE_CHANNEL_ID: "leakage_agent",
}



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
            "lines": _build_teams_lines(
                request.messages,
                request.context,
            )
        }
    else:
        return RenderAgentResponse(
            success=False,
            sourceAgent=request.agent_name,
            error="No messages received.",
        )
        
        
    channel_id = request.context.channelId

    agent_name = CHANNEL_AGENT_MAP.get(channel_id)

    if not agent_name:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported channel {channel_id}",
        )


    result = await render_agent_response(
        agent_name=agent_name,
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