"""The HTTP surface every agent board is served through.

Chat, conversations, the agent list, and `GET /dashboard/{agent}` — the route
all three Retail boards call.

Named `finance_agents_html.py` until the Retail migration, which was misleading
in the direction that costs the most: the finance modules in `modules.py` are
all commented out, so a reader could reasonably have concluded this file was
dead and deleted the only live dashboard endpoint in the app. The finance
imports below are still real — the simulation routes they feed are reachable —
but nothing here is finance-specific.
"""

# Models

import asyncio
import inspect
import json
import logging
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
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

from src.llm.agents.common.tools.scope import (
    set_active_legal_entity_id,
    reset_active_legal_entity_id,
    set_active_period,
    reset_active_period,
    set_active_category_group,
    reset_active_category_group,
)

from src.llm.pipeline import (
    render_agent_response,
)

from src.llm.agents.finance.treasury.cashflow.models import CashFlowSimulationRequest
from src.llm.agents import get_agent
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.finance.finance.dashboard import simulate_finance_scenario
from src.llm.agents.finance.leakage.dashboard import simulate_leakage_scenario
from src.llm.agents.finance.collection.tools.collection_data import (
    calculate_collection_scenario,
)
from src.llm.agents.retail.demand_forecasting.forecast_basket import (
    BASKET_QUERY_PARAMS,
    ForecastBasketError,
    build_forecast_basket,
)
from src.llm.agents.finance.treasury.tools.treasury_data import (
    simulate_cashflow,
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
    # The board's currently selected server_filters values, so a question
    # asked while the dashboard is scoped gets answered about that same
    # slice — see common/tools/scope.py. "ALL" and omitted both mean
    # unfiltered, matching how the dashboard route treats the same value.
    legal_entity_id: str | None = None
    period: str | None = None
    category_group: str | None = None

class CollectionSimulationRequest(
    BaseModel
):
    # No default name. It used to carry "PT Anugerah Prima (Customer A)",
    # the previous dataset's label for CU-001; the current dataset drops the
    # suffix, so the old string matched no customer and a request that
    # omitted the field failed. Omitted now means "the most overdue
    # customer", resolved from the ledger by the tool.
    customer_name: str | None = Field(default=None)

    cash_to_collect_idr_mn: float = Field(
        ge=0,
    )

    discount_pct: float = Field(
        default=0,
        ge=0,
        le=100,
    )


class FinanceSimulationRequest(BaseModel):
    price: float = 0
    cost: float = 0
    vol: float = 0
    fx: float = 0
    opex: float = 0
    scope: str = "all"
    # Forwarded from the dashboard baseline so the gauge measures against the
    # same EBITDA margin target the KPI card shows.
    target: float = Field(default=0.15, gt=0, le=1)


class LeakageSimulationRequest(BaseModel):
    hold: float = Field(ge=0)
    dupRec: float = Field(default=95, ge=0, le=100)
    ovRec: float = Field(default=90, ge=0, le=100)
    duplicates_amount: float = Field(default=3050, ge=0)
    overbill_amount: float = Field(default=400, ge=0)
    other_blocked: float = Field(default=500, ge=0)
    at_risk: float = Field(default=7845, ge=0)

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

from src.llm.pipeline import render_agent_response


async def run_chat_agent(
    agent: str,
    history_lines: list,
    emitter,
):
    descriptor = get_agent(agent)
    if descriptor.dashboard_only:
        raise ValueError(
            f"{descriptor.display} is a dashboard-only module."
        )
    agent_name = descriptor.chat_agent

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

    # Same "ALL" normalisation as GET /dashboard/{agent}: the dropdowns'
    # "clear" option round-trips as the literal string "ALL", not as a value
    # a chat tool would try to match against a real column.
    scoped_entity_id = (
        request.legal_entity_id
        if request.legal_entity_id and request.legal_entity_id != "ALL"
        else None
    )
    scoped_period = (
        request.period
        if request.period and request.period != "ALL"
        else None
    )
    scoped_category_group = (
        request.category_group
        if request.category_group and request.category_group != "ALL"
        else None
    )
    entity_token = set_active_legal_entity_id(scoped_entity_id)
    period_token = set_active_period(scoped_period)
    category_group_token = set_active_category_group(scoped_category_group)

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
        reset_active_legal_entity_id(
            entity_token
        )
        reset_active_period(
            period_token
        )
        reset_active_category_group(
            category_group_token
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
                    agent_type=get_agent(
                        request.agent
                    ).chat_agent,
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


@router.get("/agents")
async def list_agents() -> dict[str, Any]:
    """Registry-driven list of user-facing agents for the frontend sidebar.

    Ordered by `agents/modules.py:ENABLED_MODULES` — that order is the sidebar
    order, and the presentation strings below are what the sidebar renders.
    """
    from src.llm.agents import AGENT_REGISTRY

    return {
        "items": [
            {
                "id": descriptor.id,
                "folder": descriptor.folder,
                "name": descriptor.name,
                "display": descriptor.display,
                "description": descriptor.description,
                "prompt": descriptor.prompt,
                "starter_prompts": list(descriptor.starter_prompts),
                "dashboard_only": descriptor.dashboard_only,
            }
            for descriptor in AGENT_REGISTRY.values()
        ]
    }


# Derived from the scope rather than typed out, so a new filter cannot be added
# to `DashboardScope` and left out of the guard below.
_KNOWN_QUERY_PARAMS: frozenset[str] = frozenset(DashboardScope().__dataclass_fields__)


@router.get("/dashboard/{agent}")
async def get_agent_dashboard(
    request: Request,
    agent: str,
    legal_entity_id: str | None = Query(
        default=None,
        description=(
            "Narrow the dashboard to one legal entity "
            "(see server_filters on any dashboard response). "
            "Omitted or 'ALL' returns every entity."
        ),
    ),
    period: str | None = Query(
        default=None,
        description=(
            "Narrow the dashboard to one month ('2026-03-01'). Omitted or "
            "'ALL' returns the full reporting window."
        ),
    ),
    category_group: str | None = Query(
        default=None,
        description="Narrow to one product category group. Omitted or 'ALL' returns every one.",
    ),
    store_id: str | None = Query(
        default=None,
        description="Retail. Narrow to one store. Omitted or 'ALL' returns every store.",
    ),
    state: str | None = Query(
        default=None,
        description="Retail. Narrow to one inventory state (Stockout, Low, Expiry, …).",
    ),
    route: str | None = Query(
        default=None,
        description="Retail. Narrow to one purchase route (direct, flow, cross).",
    ),
    sku: str | None = Query(
        default=None,
        description="Retail. Narrow to SKUs matching this code or name.",
    ),
    reorder_only: bool = Query(
        default=False,
        description="Retail. Return only lines below their reorder point.",
    ),
) -> dict[str, Any]:
    """One dashboard payload for one agent, narrowed to one scope.

    Filters an agent's data cannot support come back named in
    `ignored_filters` rather than being dropped. Silently returning unfiltered
    figures under a filtered heading is the failure this route used to have,
    and it is invisible from the client side — the response is still a 200 and
    still well-formed, only wrong.
    """
    try:
        descriptor = get_agent(agent)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    # FastAPI drops query parameters it was not told about, before any of this
    # runs — so a misspelt filter would still return a clean 200 carrying
    # chain-wide figures under a narrowed heading. `DashboardScope.from_query`
    # cannot catch that on its own; the raw query string is the only place the
    # mistake is still visible.
    unknown = sorted(set(request.query_params) - _KNOWN_QUERY_PARAMS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown dashboard filter(s): {', '.join(unknown)}. "
                f"Known filters: {', '.join(sorted(_KNOWN_QUERY_PARAMS))}."
            ),
        )

    try:
        scope = DashboardScope.from_query(
            legal_entity_id=legal_entity_id,
            period=period,
            category_group=category_group,
            store_id=store_id,
            state=state,
            route=route,
            sku=sku,
            reorder_only=reorder_only,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        payload = descriptor.build_dashboard(scope)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Dashboard data unavailable: {error}",
        ) from error

    ignored = scope.ignored_by(descriptor.supported_filters)
    if ignored:
        payload = {**payload, "ignored_filters": list(ignored)}
    return payload


@router.get("/dashboard/retail.demand_forecasting/forecast-basket")
async def get_demand_forecast_basket(
    request: Request,
    legal_entity_id: str | None = Query(
        default=None,
        description="Narrow the basket to one legal entity; omitted or 'ALL' means all.",
    ),
    category_group: str | None = Query(
        default=None,
        description="Narrow the basket to one dim_item.category_id.",
    ),
    store_id: str | None = Query(
        default=None,
        description="Narrow the basket to one Store; omitted or 'ALL' means all.",
    ),
    sku: str | None = Query(
        default=None,
        description="Case-insensitive substring search over SKU ID or item name.",
    ),
) -> dict[str, Any]:
    """Return the complete baseline Demand Forecasting Store x SKU basket."""

    unknown = sorted(set(request.query_params) - BASKET_QUERY_PARAMS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown forecast basket filter(s): {', '.join(unknown)}. "
                f"Known filters: {', '.join(sorted(BASKET_QUERY_PARAMS))}."
            ),
        )

    try:
        scope = DashboardScope.from_query(
            legal_entity_id=legal_entity_id,
            category_group=category_group,
            store_id=store_id,
            sku=sku,
        )
        return build_forecast_basket(scope)
    except ForecastBasketError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Forecast basket unavailable: {error}",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Forecast basket unavailable: {error}",
        ) from error


@router.post(
    "/simulations/collection/recalculate"
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


@router.post("/simulations/treasury/recalculate")
async def recalculate_cashflow_simulation(
    payload: CashFlowSimulationRequest,
) -> dict[str, Any]:
    try:
        result = simulate_cashflow(
            accelerate_collection_idr_mn=payload.accelerate_collection_idr_mn,
            defer_payment_idr_mn=payload.defer_payment_idr_mn,
            credit_line_draw_idr_mn=payload.credit_line_draw_idr_mn,
            hedge_usd=payload.hedge_usd,
        )
        return {"success": True, "result": result}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Cashflow simulation failed: {error}",
        ) from error


@router.post("/simulations/finance/recalculate")
async def recalculate_finance_simulation(
    payload: FinanceSimulationRequest,
) -> dict[str, Any]:
    result = simulate_finance_scenario(
        price=payload.price,
        cost=payload.cost,
        vol=payload.vol,
        fx=payload.fx,
        opex=payload.opex,
        scope=payload.scope,
        target=payload.target,
    )
    return result


@router.post("/simulations/leakage/recalculate")
async def recalculate_leakage_simulation(
    payload: LeakageSimulationRequest,
) -> dict[str, Any]:
    result = simulate_leakage_scenario(
        hold=payload.hold,
        dup_rec=payload.dupRec,
        ov_rec=payload.ovRec,
        duplicates_amount=payload.duplicates_amount,
        overbill_amount=payload.overbill_amount,
        other_blocked=payload.other_blocked,
        at_risk=payload.at_risk,
    )
    return result


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
