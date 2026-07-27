"""Shared dashboard building blocks (KPI / chart / table helpers)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

_DB_TIMEOUT_SEC = 15.0


def _call_with_timeout(fn: Callable[[], Any], timeout: float = _DB_TIMEOUT_SEC) -> Any:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        return future.result(timeout=timeout)

def _fmt(n: float, digits: int = 0) -> str:
    if digits <= 0:
        return f"{round(n):,}"
    return f"{n:,.{digits}f}"


def _pct(n: float, digits: int = 1) -> str:
    return f"{n * 100:.{digits}f}%" if abs(n) <= 2 else f"{n:.{digits}f}%"


def _bar_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    y_axis_title: str = "IDR mn",
    note: str = "",
    tag: str = "",
    target: float | None = None,
    target_label: str | None = None,
) -> dict[str, Any]:
    chart: dict[str, Any] = {
        "title": title,
        "chart_type": "bar",
        "y_axis_title": y_axis_title,
        "tag": tag,
        "data": rows,
    }
    if note:
        chart["note"] = note
    if target is not None:
        chart["target"] = target
        if target_label:
            chart["target_label"] = target_label
    return chart


def _line_chart(
    title: str,
    points: list[dict[str, Any]],
    *,
    y_axis_title: str = "IDR mn",
    note: str = "",
    tag: str = "",
    target: float | None = None,
    target_label: str | None = None,
) -> dict[str, Any]:
    chart: dict[str, Any] = {
        "title": title,
        "chart_type": "line",
        "x_axis_title": "Week",
        "y_axis_title": y_axis_title,
        "tag": tag,
        "data": [
            {
                "legend": "Closing cash",
                "values": points,
            }
        ],
    }
    if note:
        chart["note"] = note
    if target is not None:
        chart["target"] = target
        if target_label:
            chart["target_label"] = target_label
    return chart


def _waterfall_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    note: str = "",
    tag: str = "variance",
) -> dict[str, Any]:
    return {
        "title": title,
        "chart_type": "waterfall",
        "y_axis_title": "IDR mn",
        "tag": tag,
        "note": note,
        "data": rows,
    }


def _donut_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    note: str = "",
    tag: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "chart_type": "donut",
        "tag": tag,
        "note": note,
        "data": rows,
    }


def _table_view(
    title: str,
    headers: list[str],
    rows: list[list[Any]],
    *,
    note: str = "",
    tag: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "tag": tag,
        "note": note,
        "table": {
            "headers": headers,
            "rows": rows,
        },
    }

def _row_get(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered and lowered[name.lower()] is not None:
            return lowered[name.lower()]
    return None
