#same as finance_agents.py, but suited for the new architecture in html

#Models

from pydantic import BaseModel
from src.chatflow.repository import (
    create_conversation,
    save_message,
    get_messages,
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
    message: str,
    emitter,
):
    agent_name = CHAT_AGENT_MAP[agent]

    messages_input = {
        "lines": [
            {
                "sender": "user",
                "text": message,
            }
        ]
    }

    result = await render_agent_response(
        agent_name=agent_name,
        messages_input=messages_input,
        event_callback=emitter,
    )


    return result

async def run_chat_stream(
    request: ChatRequest,
):
    yield sse(
    "assistant_response",
        {
            "blocks": [
                block.model_dump()
                for block in result.blocks
            ]
        }
    )

    result = await run_chat_agent(
        agent=request.agent,
        message=request.message,
        emitter=None,
    )

    yield sse(
        "assistant_response",
        {
            "text": result.response_text,
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