"""The slice a live chat turn is scoped to: legal entity, period, category
group.

`LOCAL_TOOLS` (`agents/__init__.py`) is a flat dict of plain functions built
once at import time and handed to pydantic-ai — the model calls
`get_financial_performance_snapshot()` with whatever arguments it decides on,
which in practice means zero, since nothing in its prompt or tool schema
mentions `legal_entity_id`, `period` or `category_group`. Asking the model to
infer and re-state the board's active filters on every turn would be
unreliable in exactly the way QC-002 was: chat quietly drifts from what is on
screen.

A `ContextVar` per filter sidesteps that without touching the model-facing
tool schema at all — the same `set_X`/`reset_X` shape `tool_events.py`
already uses for the same kind of problem (a per-request value tool calls
need without the model ever passing it). `set_active_*()` is called once in
`run_chat_stream`, before the chat agent's task is created; each snapshot
function falls back to the matching `active_*()` only when its own argument
is `None` — the dashboard route, which always passes an explicit value
(`None` meaning "asked for everything", not "unset"), is unaffected.

`ContextVar` survives an `await` and an `asyncio.create_task()` inside the
same run, which is how pydantic-ai executes tool calls and how
`run_chat_stream` launches the agent turn. It would NOT survive being handed
to a raw thread (e.g. through `ThreadPoolExecutor.submit`), which is why the
dashboard path threads every filter as a real argument instead of relying on
this.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_active_legal_entity_id: ContextVar[str | None] = ContextVar(
    "active_legal_entity_id",
    default=None,
)
_active_period: ContextVar[str | None] = ContextVar(
    "active_period",
    default=None,
)
_active_category_group: ContextVar[str | None] = ContextVar(
    "active_category_group",
    default=None,
)


def set_active_legal_entity_id(legal_entity_id: str | None) -> Token:
    return _active_legal_entity_id.set(legal_entity_id)


def reset_active_legal_entity_id(token: Token) -> None:
    _active_legal_entity_id.reset(token)


def active_legal_entity_id() -> str | None:
    """The entity the current chat turn is scoped to, or `None` for all."""
    return _active_legal_entity_id.get()


def set_active_period(period: str | None) -> Token:
    return _active_period.set(period)


def reset_active_period(token: Token) -> None:
    _active_period.reset(token)


def active_period() -> str | None:
    """The month ("2026-03-01") the current chat turn is scoped to, or
    `None` for the full reporting window."""
    return _active_period.get()


def set_active_category_group(category_group: str | None) -> Token:
    return _active_category_group.set(category_group)


def reset_active_category_group(token: Token) -> None:
    _active_category_group.reset(token)


def active_category_group() -> str | None:
    """The category group the current chat turn is scoped to, or `None` for
    all of them."""
    return _active_category_group.get()


__all__ = [
    "set_active_legal_entity_id",
    "reset_active_legal_entity_id",
    "active_legal_entity_id",
    "set_active_period",
    "reset_active_period",
    "active_period",
    "set_active_category_group",
    "reset_active_category_group",
    "active_category_group",
]
