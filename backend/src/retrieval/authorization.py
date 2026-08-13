from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from .models import RetrievalRequest


@dataclass(frozen=True)
class PrincipalContext:
    principal_id: str
    is_internal: bool
    legal_entity_ids: tuple[str, ...] = ()


class AuthorizationPolicy(Protocol):
    def authorize(self, principal: PrincipalContext, request: RetrievalRequest) -> None:
        ...


class InternalPocAuthorizationPolicy:
    """Phase 6 hook: internal marker only, not enterprise authentication."""

    def authorize(self, principal: PrincipalContext, request: RetrievalRequest) -> None:
        if not principal.is_internal:
            raise PermissionError("Retrieval is restricted to the internal POC boundary")


def retrieval_api_enabled() -> bool:
    return os.getenv("RETAIL_RETRIEVAL_API_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def cli_principal() -> PrincipalContext:
    return PrincipalContext(principal_id="phase6-cli", is_internal=True)

