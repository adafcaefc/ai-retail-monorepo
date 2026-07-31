"""Where each agent's figures sit in time.

QC-035: not one of the twenty-two charts said what span it covered. That is
also what makes QC-003 read as a fifteen-fold gap — a monthly revenue figure
sitting beside an annual credit-sales base, with neither labelled.

The four agents were authored as separate workbooks and genuinely cover
different spans, so there is no single answer to state. Each period is derived
from that domain's own data:

    Finance     the workbook says so outright, in its assumptions
    Treasury    the forecast's own first and last week
    Leakage     the range of invoice dates actually scanned
    Collection  an ageing snapshot with no date column anywhere; the workbook
                name is the only thing that states the period, so it is used,
                and the DSO basis is named alongside it

Nothing here invents a date. Where a domain cannot say when it is, the label
says what it is instead.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from src.llm.agents.common.tools.db import _rows

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

WORKBOOK_PERIOD = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d\d)\b"
)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None
    return None


def _day(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1][:3]} {value.year}"


def _span(start: date | None, end: date | None) -> str | None:
    if start is None or end is None:
        return None
    if start.year == end.year and start.month == end.month:
        return f"{start.day}-{end.day} {MONTHS[start.month - 1][:3]} {end.year}"
    return f"{_day(start)} to {_day(end)}"


def workbook_period(connection, import_batch_id: int | None) -> str | None:
    """The period named in the source workbook's own filename."""
    if import_batch_id is None:
        return None
    rows = _rows(
        connection,
        "SELECT workbook_name FROM audit.import_batches WHERE id = :id",
        {"id": import_batch_id},
    )
    if not rows:
        return None
    match = WORKBOOK_PERIOD.search(str(rows[0].get("workbook_name") or ""))
    return f"{match.group(1)} {match.group(2)}" if match else None


def finance_period(connection, import_batch_id: int | None) -> str:
    rows = _rows(
        connection,
        "SELECT assumption_name, text_value "
        "FROM financial_performance.assumptions "
        "WHERE assumption_group = 'PERIOD_AND_SCOPE' "
        "AND import_batch_id = :id",
        {"id": import_batch_id},
    )
    stated = {
        str(r.get("assumption_name") or ""): str(r.get("text_value") or "")
        for r in rows
    }
    span = stated.get("Period") or workbook_period(connection, import_batch_id)
    comparison = stated.get("Comparison")
    if span and comparison:
        return f"{span} · {comparison.lower()}"
    return span or "period not stated in the source workbook"


def treasury_period(connection, import_batch_id: int | None) -> str:
    rows = _rows(
        connection,
        "SELECT min(week_start) AS opens, max(week_end) AS closes, "
        "count(*) AS weeks FROM cashflow.weekly_forecast "
        "WHERE import_batch_id = :id",
        {"id": import_batch_id},
    )
    row = rows[0] if rows else {}
    span = _span(_as_date(row.get("opens")), _as_date(row.get("closes")))
    weeks = int(row.get("weeks") or 0)
    if span and weeks:
        return f"{weeks}-week forecast · {span}"
    return span or "rolling weekly forecast"


def leakage_period(connection, import_batch_id: int | None) -> str:
    rows = _rows(
        connection,
        "SELECT min(invoice_date) AS opens, max(invoice_date) AS closes "
        "FROM payment_leakage.ap_transactions WHERE import_batch_id = :id",
        {"id": import_batch_id},
    )
    row = rows[0] if rows else {}
    span = _span(_as_date(row.get("opens")), _as_date(row.get("closes")))
    if span:
        return f"invoices scanned {span}"
    fallback = workbook_period(connection, import_batch_id)
    return f"scan cycle · {fallback}" if fallback else "one scan cycle"


def collection_period(connection, import_batch_id: int | None) -> str:
    """Collections stores no date on any row — see the module docstring."""
    rows = _rows(
        connection,
        "SELECT numeric_value FROM collections.assumptions "
        "WHERE assumption_name = 'Days in year' AND import_batch_id = :id",
        {"id": import_batch_id},
    )
    days = int(float(rows[0]["numeric_value"])) if rows else 365
    stamp = workbook_period(connection, import_batch_id)
    snapshot = f"AR ageing snapshot · {stamp}" if stamp else "AR ageing snapshot"
    return f"{snapshot} · DSO on a {days}-day basis"


__all__ = [
    "collection_period",
    "finance_period",
    "leakage_period",
    "treasury_period",
    "workbook_period",
]
