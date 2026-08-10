"""HTTP API for the Data Source page: read-only windows over the workbook.

Both endpoints are plain `def`, not `async def`, on purpose -- the first
request may trigger a ~13 s openpyxl parse, and FastAPI runs sync endpoints on
a threadpool where that cannot stall the event loop.
"""

from __future__ import annotations

import logging

from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Path,
    Query,
)

from src.excel import workbook

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/excel",
    tags=["Workbook viewer"],
)


def _missing_workbook(
    error: workbook.WorkbookMissing,
) -> HTTPException:
    # 503 rather than 404, matching how main.py reports a missing frontend
    # build: the URL is right, the deployment is not, so the page offers Retry.
    logger.warning(
        "Data Source workbook not found: %s",
        error,
    )

    return HTTPException(
        status_code=503,
        detail=(
            "Data source workbook was not found. Set "
            "EXCEL_WORKBOOK_PATH or restore "
            f"resources/{workbook.DEFAULT_WORKBOOK_NAME}."
        ),
    )


def _unreadable_workbook(
    error: workbook.WorkbookUnreadable,
) -> HTTPException:
    logger.error(
        "Data Source workbook could not be read",
        exc_info=error,
    )

    return HTTPException(
        status_code=500,
        detail=(
            "Data source workbook could not be read: "
            f"{error}"
        ),
    )


@router.get("/sheets")
def get_sheets() -> dict[str, Any]:
    """Every sheet in the workbook, with its dimensions."""
    try:
        return workbook.list_sheets()
    except workbook.WorkbookMissing as error:
        raise _missing_workbook(error) from error
    except workbook.WorkbookUnreadable as error:
        raise _unreadable_workbook(error) from error


@router.get("/sheets/{sheet_name}")
def get_sheet(
    sheet_name: str = Path(
        description=(
            "Sheet name exactly as it appears in the workbook, "
            "percent-encoded."
        ),
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="0-based index of the first row to return.",
    ),
    limit: int = Query(
        default=workbook.DEFAULT_PAGE_ROWS,
        ge=1,
        le=workbook.MAX_PAGE_ROWS,
        description=(
            "Rows per page. Capped because an unpaged ENGINE_STORE is "
            "~10 MB of JSON and ~500k DOM nodes."
        ),
    ),
) -> dict[str, Any]:
    """One window of a sheet, carrying the workbook's own cell formatting."""
    try:
        return workbook.read_sheet(
            sheet_name,
            offset=offset,
            limit=limit,
        )
    except workbook.WorkbookMissing as error:
        raise _missing_workbook(error) from error
    except workbook.WorkbookUnreadable as error:
        raise _unreadable_workbook(error) from error
    except workbook.UnknownSheet as error:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown sheet: '{sheet_name}'.",
        ) from error
