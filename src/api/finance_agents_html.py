#same as finance_agents.py, but suited for the new architecture in html

#Models
from fastapi import APIRouter

from pydantic import BaseModel
from src.chatflow.repository import (
    create_conversation,
    save_message,
    get_messages,
    list_conversations,
    get_conversation_messages,
)

from src.db.db import session_scope

router = APIRouter(
    prefix="/api/html",
    tags=["HTML Chat"],
)
# TODO:
# integrate conversation persistence
# 1. create conversation if missing
# 2. save user message
# 3. load conversation history
# 4. pass history into render_agent_response()
# 5. save assistant response

class ChatRequest(BaseModel):
    agent: str
    message: str
    conversation_id: str | None = None


class ToolCallEvent(BaseModel):
    id: str
    tool: str
    arguments: dict


class ToolResultEvent(BaseModel):
    id: str
    tool: str
    result: dict

#SSE helpers

import json


def sse(
    event: str,
    data: dict,
    ) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data)}\n\n"
    )

#chat service

CHAT_AGENT_MAP = {
    "finance": "finance_agent",
    "treasury": "cashflow_agent",
    "collections": "collection_agent",
    "leakage": "leakage_agent",
}

from src.llm.pipeline import render_agent_response


async def run_chat_agent(
    agent: str,
    history_lines: list,
    emitter,
):
    agent_name = CHAT_AGENT_MAP[agent]

    messages_input = {
        "lines": history_lines
    }

    result = await render_agent_response(
        agent_name=agent_name,
        messages_input=messages_input,
    )


    return result

async def run_chat_stream(
    request: ChatRequest,
):
    with session_scope() as session:

        if request.conversation_id is None:
            conversation_id = create_conversation(
                session=session,
                title=request.message[:50],
            )
        else:
            conversation_id = request.conversation_id

        save_message(
            session=session,
            conversation_id=conversation_id,
            sender="user",
            channel=request.agent,
            message=request.message,
        )

        history = get_messages(
            session=session,
            conversation_id=conversation_id,
        )

        history_lines = build_history_lines(
            history
        )

    result = await run_chat_agent(
        agent=request.agent,
        history_lines=history_lines,
        emitter=None,
    )

    with session_scope() as session:

        save_message(
            session=session,
            conversation_id=conversation_id,
            sender="assistant",
            channel=request.agent,
            message=json.dumps(
                [
                    block.model_dump()
                    for block in result.blocks
                ]
            ),
        )

    yield sse(
        "assistant_response",
        {
            "conversation_id": conversation_id,
            "blocks": [
                block.model_dump()
                for block in result.blocks
            ]
        }
    )

    yield sse(
        "done",
        {}
    )

from fastapi.responses import StreamingResponse

@router.post("/chat")
async def chat(request: ChatRequest):

    async def stream():

        async for event in run_chat_stream(
            request
        ):
            yield event

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
    )

def build_history_lines(
    messages,
):
    return [
        {
            "sender": msg["sender"],
            "text": msg["message"],
        }
        for msg in messages
    ]

@router.get("/conversations")
async def get_conversations():

    with session_scope() as session:

        conversations = list_conversations(
            session=session
        )

    return {
        "items": conversations
    }

@router.get(
    "/conversations/{conversation_id}"
)
async def get_conversation(
    conversation_id: str,
):

    with session_scope() as session:

        messages = get_conversation_messages(
            session=session,
            conversation_id=conversation_id,
        )

    return {
        "conversation_id": conversation_id,
        "messages": messages,
    }