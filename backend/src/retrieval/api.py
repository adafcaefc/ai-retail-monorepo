from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from .authorization import PrincipalContext, retrieval_api_enabled
from .models import RetrievalRequest, RetrievalResponse
from .service import retrieve_context

router = APIRouter(
    prefix="/api/retrieval",
    tags=["Internal retrieval"],
)


def _internal_poc_principal() -> PrincipalContext:
    if not retrieval_api_enabled():
        raise HTTPException(
            status_code=503,
            detail=(
                "The internal Phase 6 retrieval API is disabled. Set "
                "RETAIL_RETRIEVAL_API_ENABLED=true only in an internal/dev environment."
            ),
        )
    return PrincipalContext(
        principal_id="internal-retrieval-api",
        is_internal=True,
    )


InternalPrincipal = Annotated[PrincipalContext, Depends(_internal_poc_principal)]


@router.post(
    "/query",
    response_model=RetrievalResponse,
    include_in_schema=False,
)
def query_retrieval(
    payload: RetrievalRequest,
    principal: InternalPrincipal,
) -> RetrievalResponse:
    """Return evidence only; this endpoint never generates an answer."""
    try:
        return retrieve_context(payload, principal=principal)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

