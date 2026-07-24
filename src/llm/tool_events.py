from __future__ import annotations

import inspect
import json
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable
from uuid import uuid4


_tool_event_queue: ContextVar[Any | None] = ContextVar(
    "tool_event_queue",
    default=None,
)


def set_tool_event_queue(
    queue: Any,
):
    return _tool_event_queue.set(queue)


def reset_tool_event_queue(
    token,
) -> None:
    _tool_event_queue.reset(
        token
    )


def _safe_value(
    value: Any,
) -> Any:
    try:
        json.dumps(
            value,
            default=str,
        )
        return value
    except TypeError:
        return str(value)


def _safe_args(
    args: tuple,
    kwargs: dict,
) -> dict[str, Any]:
    return {
        "args": [
            _safe_value(arg)
            for arg in args
        ],
        "kwargs": {
            key: _safe_value(value)
            for key, value in kwargs.items()
        },
    }


def emit_tool_event(
    event_name: str,
    data: dict[str, Any],
) -> None:
    queue = _tool_event_queue.get()

    if queue is None:
        return

    queue.put_nowait(
        (
            event_name,
            data,
        )
    )


def wrap_tool(
    tool_name: str,
    tool_func: Callable,
) -> Callable:

    if inspect.iscoroutinefunction(
        tool_func
    ):

        @wraps(tool_func)
        async def async_wrapper(
            *args,
            **kwargs,
        ):
            event_id = str(
                uuid4()
            )

            emit_tool_event(
                "tool_call",
                {
                    "id": event_id,
                    "tool": tool_name,
                    "arguments": _safe_args(
                        args,
                        kwargs,
                    ),
                },
            )

            try:
                result = await tool_func(
                    *args,
                    **kwargs,
                )

                emit_tool_event(
                    "tool_result",
                    {
                        "id": event_id,
                        "tool": tool_name,
                        "result": _safe_value(
                            result
                        ),
                    },
                )

                return result

            except Exception as exc:
                emit_tool_event(
                    "tool_result",
                    {
                        "id": event_id,
                        "tool": tool_name,
                        "result": {
                            "error": str(exc),
                        },
                    },
                )

                raise

        async_wrapper.__name__ = tool_name
        async_wrapper.__qualname__ = tool_name
        return async_wrapper

    @wraps(tool_func)
    def sync_wrapper(
        *args,
        **kwargs,
    ):
        event_id = str(
            uuid4()
        )

        emit_tool_event(
            "tool_call",
            {
                "id": event_id,
                "tool": tool_name,
                "arguments": _safe_args(
                    args,
                    kwargs,
                ),
            },
        )

        try:
            result = tool_func(
                *args,
                **kwargs,
            )

            emit_tool_event(
                "tool_result",
                {
                    "id": event_id,
                    "tool": tool_name,
                    "result": _safe_value(
                        result
                    ),
                },
            )

            return result

        except Exception as exc:
            emit_tool_event(
                "tool_result",
                {
                    "id": event_id,
                    "tool": tool_name,
                    "result": {
                        "error": str(exc),
                    },
                },
            )

            raise

    sync_wrapper.__name__ = tool_name
    sync_wrapper.__qualname__ = tool_name
    return sync_wrapper


def wrap_tools(
    tools: dict[str, Callable],
) -> dict[str, Callable]:
    return {
        tool_name: wrap_tool(
            tool_name,
            tool_func,
        )
        for tool_name, tool_func in tools.items()
    }