"""Shared dashboard building blocks (KPI / chart / table helpers)."""

from __future__ import annotations

import re

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

_DB_TIMEOUT_SEC = 15.0


def _call_with_timeout(fn: Callable[[], Any], timeout: float = _DB_TIMEOUT_SEC) -> Any:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        return future.result(timeout=timeout)


def _parse_num(text: Any) -> float | None:
    """Best-effort numeric value from a formatted KPI string ('9.2%', '4,300')."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = re.search(r"-?\d[\d,]*\.?\d*", str(text))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_target(delta: Any) -> float | None:
    """Pull a target number out of a delta caption like 'target 15%'."""
    if not delta:
        return None
    match = re.search(r"target\s+(-?\d[\d,]*\.?\d*)", str(delta), re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _enrich_kpis(kpis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Attach RAG status + progress-to-target so the frontend can render a
    glanceable status without re-parsing strings. Direction of "good" is
    already encoded by each builder's `alert` flag, so status defaults from
    it; a builder may also pre-set `status` for a proper three-tier band.
    """
    for kpi in kpis:
        value_num = _parse_num(kpi.get("value"))
        if value_num is not None:
            kpi["value_num"] = value_num

        target_num = _parse_target(kpi.get("delta"))
        if target_num is not None:
            kpi["target_num"] = target_num
            if value_num is not None and target_num:
                kpi["progress"] = round(
                    max(0.0, min(1.2, value_num / target_num)), 4
                )

        if "status" not in kpi:
            kpi["status"] = "bad" if kpi.get("alert") else "good"

    return kpis


def _enriched(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a finished dashboard payload through KPI enrichment."""
    payload["kpis"] = _enrich_kpis(payload.get("kpis") or [])
    return payload


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

def _num(value: Any, default: float = 0.0) -> float:
    """Coerce a DB cell to float; `default` when it is null or unparseable."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_get(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered and lowered[name.lower()] is not None:
            return lowered[name.lower()]
    return None
