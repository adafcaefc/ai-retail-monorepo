"""The slice of the chain a dashboard request is asking about.

Replaces three positional parameters with one labelled envelope, for a reason
that had already started to bite. `GET /dashboard/{agent}` used to forward
exactly `(legal_entity_id, period, category_group)` and drop everything else on
the query string — no error, still a 200, just an unfiltered answer. The Retail
boards send five or more (`store_id`, `state`, `route`, `sku`, `reorder_only`),
so their filters appeared to work while the figures underneath ignored them.

Two things follow from making it an object.

**A new filter costs one field, not one position.** Two people adding a fourth
positional parameter on two branches merge cleanly and silently swap meanings;
two people adding a named field collide in the same place and have to talk.

**A filter an agent cannot honour is reported rather than dropped.** Every
agent declares `supported_filters` on its descriptor, and the route names what
it could not apply in `ignored_filters` on the response. That information
already existed — it was buried in `# noqa: ARG001 - not applicable` comments
next to parameters the finance builders quietly discard — but it never reached
the caller who was relying on the filter.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

# The dropdowns' own "clear" option round-trips as the literal string "ALL"
# (see `_server_filter` in dashboard_blocks.py). Treated as "no filter" rather
# than as a value to match against a real column, where it would match nothing.
_CLEARED = {"", "ALL"}


@dataclass(frozen=True, slots=True)
class DashboardScope:
    """One dashboard request's filters. Every field defaults to "everything"."""

    # Shared across Finance and Retail.
    legal_entity_id: str | None = None
    period: str | None = None
    category_group: str | None = None

    # Retail. `store_id` and `sku` are join keys; `state`, `route` and
    # `reorder_only` narrow to a subset of rows.
    store_id: str | None = None
    state: str | None = None
    route: str | None = None
    sku: str | None = None
    reorder_only: bool = False

    @classmethod
    def from_query(cls, **raw: Any) -> DashboardScope:
        """Build a scope from query parameters, normalising "clear" to `None`.

        Unknown keys raise rather than being ignored. A caller that sends
        `store` when the field is `store_id` has a bug, and returning an
        unfiltered 200 is how that bug reaches a report instead of a log.
        """
        known = {field.name: field for field in fields(cls)}
        unknown = sorted(set(raw) - set(known))
        if unknown:
            raise ValueError(
                f"Unknown dashboard filter(s): {', '.join(unknown)}. "
                f"Known filters: {', '.join(sorted(known))}."
            )

        values: dict[str, Any] = {}
        for name, value in raw.items():
            # Keyed off the default rather than the annotation: `from __future__
            # import annotations` turns `field.type` into a string, and matching
            # on `"bool"` would break the moment someone writes `bool | None`.
            if isinstance(known[name].default, bool):
                values[name] = _as_bool(value)
            elif isinstance(value, str) and value.strip() in _CLEARED:
                values[name] = None
            else:
                values[name] = value

        return cls(**values)

    def applied(self) -> tuple[str, ...]:
        """The filters actually asking for something, in declaration order."""
        return tuple(
            field.name
            for field in fields(self)
            if getattr(self, field.name) not in (None, False)
        )

    def ignored_by(self, supported: frozenset[str]) -> tuple[str, ...]:
        """Filters this request asked for that the agent cannot honour."""
        return tuple(name for name in self.applied() if name not in supported)

    def as_query(self) -> dict[str, Any]:
        """The applied filters as a plain mapping, for logging and echoing."""
        return {name: getattr(self, name) for name in self.applied()}


def _as_bool(value: Any) -> bool:
    """Query strings arrive as text; `reorder_only=false` must not be true."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


__all__ = ["DashboardScope"]
