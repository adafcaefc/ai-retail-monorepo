#same as finance_agents.py, but suited for the new architecture in html

#Models
import asyncio
import inspect
import json
import logging
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
)

from fastapi.responses import (
    StreamingResponse,
)

from pydantic import (
    BaseModel,
    Field,
)

from src.chatflow.repository import(
    create_conversation,
    save_message,
    get_messages,
    list_conversations,
    get_conversation_messages,
)

from src.db.db import session_scope

from src.llm.tool_events import (
    set_tool_event_queue,
    reset_tool_event_queue,
)

from src.llm.pipeline import (
    render_agent_response,
)

from src.llm.tools.finance_data import (
    calculate_collection_scenario
)

from src.llm.suggested_response import (
    generate_suggested_responses,
)
from src.llm.suggested_response_context import (
    build_suggested_response_context,
)

logger = logging.getLogger(__name__)
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

class CollectionSimulationRequest(
    BaseModel
):
    customer_name: str = Field(
        default=(
            "PT Anugerah Prima "
            "(Customer A)"
        ),
        min_length=1,
    )

    cash_to_collect_idr_mn: float = Field(
        ge=0,
    )

    discount_pct: float = Field(
        default=0,
        ge=0,
        le=100,
    )

class ToolCallEvent(BaseModel):
    id: str
    tool: str
    arguments: dict


class ToolResultEvent(BaseModel):
    id: str
    tool: str
    result: dict

#SSE helpers
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

    event_queue = asyncio.Queue()

    token = set_tool_event_queue(
        event_queue
    )

    yield sse(
        "status",
        {
            "conversation_id": conversation_id,
            "message": "Analyzing request",
        },
    )

    agent_task = asyncio.create_task(
        run_chat_agent(
            agent=request.agent,
            history_lines=history_lines,
            emitter=None,
        )
    )

    try:
        while not agent_task.done():

            try:
                event_name, event_data = await asyncio.wait_for(
                    event_queue.get(),
                    timeout=0.1,
                )

                event_data["conversation_id"] = conversation_id

                yield sse(
                    event_name,
                    event_data,
                )

            except asyncio.TimeoutError:
                pass

        result = await agent_task

        while not event_queue.empty():

            event_name, event_data = event_queue.get_nowait()

            event_data["conversation_id"] = conversation_id

            yield sse(
                event_name,
                event_data,
            )

    except Exception as exc:

        yield sse(
            "error",
            {
                "conversation_id": conversation_id,
                "message": str(exc),
            },
        )

        return

    finally:
        reset_tool_event_queue(
            token
        )

    suggestion_task: asyncio.Task[list[str]] | None = None
    # Start the optional suggestion process after the primary
    # chatbot has successfully produced a readable answer.
    logger.info(
        "Suggestion eligibility: success=%s assistant_text_length=%d",
        result.success,
        len(result.assistant_text),
    )

    if (
        result.success
        and result.assistant_text.strip()
    ):
        try:
            suggestion_context = (
                build_suggested_response_context(
                    history=history,
                    channel=request.agent,
                    agent_type=CHAT_AGENT_MAP[
                        request.agent
                    ],
                    latest_user_question=(
                        request.message
                    ),
                    latest_assistant_answer=(
                        result.assistant_text
                    ),
                )
            )

            logger.info(
                "Suggestion context built: history_lines=%d",
                len(suggestion_context.recent_history),
            )

            suggestion_task = asyncio.create_task(
                generate_suggested_responses(
                    suggestion_context
                )
            )

        except Exception:
            # Suggestions are optional. Failure to construct their
            # context must not affect the primary chatbot response.
            logger.exception(
                "Failed to build suggested-response context."
            )
            suggestion_task = None

    try:
        assistant_blocks = [
            block.model_dump()
            for block in result.blocks
        ]

        with session_scope() as session:
            save_message(
                session=session,
                conversation_id=conversation_id,
                sender="chatbot",
                channel=request.agent,
                message=json.dumps(
                    assistant_blocks
                ),
            )

        # Send the primary answer without waiting for suggestions.
        yield sse(
            "assistant_response",
            {
                "conversation_id": (
                    conversation_id
                ),
                "blocks": assistant_blocks,
            },
        )

        suggestions: list[str] = []

        if suggestion_task is not None:
            try:
                suggestions = await suggestion_task
            except asyncio.CancelledError:
                raise
            except Exception:
                # Extra protection around the optional task.
                suggestions = []

        yield sse(
            "suggestions",
            {
                "conversation_id": (
                    conversation_id
                ),
                "suggestions": suggestions,
            },
        )

        yield sse(
            "done",
            {
                "conversation_id": (
                    conversation_id
                ),
            },
        )

    finally:
        # Stop the optional Azure request if the browser disconnects
        # or the stream closes before it finishes.
        if (
            suggestion_task is not None
            and not suggestion_task.done()
        ):
            suggestion_task.cancel()

            try:
                await suggestion_task
            except asyncio.CancelledError:
                pass

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

@router.post(
    "/simulations/collections/recalculate"
)
async def recalculate_collection_simulation(
    payload: CollectionSimulationRequest,
) -> dict[str, Any]:
    try:
        result = calculate_collection_scenario(
            customer_name=
                payload.customer_name,

            cash_to_collect_idr_mn=
                payload.cash_to_collect_idr_mn,

            discount_pct=
                payload.discount_pct,
        )

        if hasattr(
            result,
            "model_dump",
        ):
            result_data = (
                result.model_dump()
            )

        elif isinstance(
            result,
            dict,
        ):
            result_data = result

        elif hasattr(
            result,
            "__dict__",
        ):
            result_data = {
                key: value
                for key, value
                in vars(result).items()
                if not key.startswith("_")
            }

        else:
            raise ValueError(
                "Unsupported collection "
                "simulation result."
            )

        return {
            "success": True,
            "result": result_data,
        }

    except (
        ValueError,
        TypeError,
        KeyError,
    ) as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Collection simulation "
                f"failed: {error}"
            ),
        ) from error
    
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