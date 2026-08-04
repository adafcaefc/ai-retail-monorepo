"""Shared dashboard building blocks (KPI / chart / table helpers)."""

from __future__ import annotations

import re

from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_HALF_UP, Decimal
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


def _classify_value(text: Any) -> tuple[str, int]:
    """Infer a KPI value string's format kind and decimal places.

    `value` stays an en-US string (`_fmt`/`_pct` output) for every consumer
    that already reads it verbatim — the test suite, `verify_qc_fixes.py`,
    and the Teams cards. This reads the *kind* back off that same string
    instead of asking each of the 20 KPI call sites to say it twice, which
    would let the two drift (a call site claims "percent", `_fmt` was used
    instead, and now they disagree on what the frontend re-renders).
    """
    s = str(text).strip()
    match = re.search(r"-?\d[\d,]*\.?\d*", s)
    digits = len(match.group(0).split(".")[1]) if match and "." in match.group(0) else 0

    if s.endswith("%"):
        return "percent", digits
    if re.fullmatch(r"-?[\d,]+\.?\d*d", s):
        # The one KPI (Collection DSO) that bakes its unit into the value
        # string itself ("62d") instead of using the `unit` field.
        return "days", digits
    return "number", digits


_DELTA_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _extract_delta_number(delta: Any) -> tuple[str, float, str, int] | None:
    """Split a delta caption into a translatable template and its one number.

    'target 15.5%' -> ('target {v}', 15.5, 'percent', 1)
    'headroom -1,987.5 vs buffer' -> ('headroom {v} vs buffer', -1987.5, 'number', 1)
    'actual' -> None (no digit in the caption, nothing to reformat)

    The template keeps every word from the original caption and only cuts out
    the digits, so a caption gaining a new fixed phrase needs no change here —
    only a new i18n dictionary entry for the template string.
    """
    if not delta:
        return None
    text = str(delta)
    match = _DELTA_NUMBER_RE.search(text)
    if not match:
        return None
    raw = match.group(0)
    try:
        num = float(raw.replace(",", ""))
    except ValueError:
        return None

    is_percent = text[match.end():match.end() + 1] == "%"
    consumed_end = match.end() + (1 if is_percent else 0)
    template = f"{text[:match.start()]}{{v}}{text[consumed_end:]}"
    digits = len(raw.split(".")[1]) if "." in raw else 0
    return template, num, ("percent" if is_percent else "number"), digits


def _enrich_kpis(kpis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Attach RAG status + progress-to-target so the frontend can render a
    glanceable status without re-parsing strings. Direction of "good" is
    already encoded by each builder's `alert` flag, so status defaults from
    it; a builder may also pre-set `status` for a proper three-tier band.

    Also attaches `value_kind`/`value_digits` and, where the delta caption
    carries a number, `delta_template`/`delta_num`/`delta_kind`/`delta_digits`.
    These let the frontend re-render the figure in the active language's
    number convention (1.234,5 vs 1,234.5) without a second round trip — see
    frontend/src/format.js. `value`/`delta` themselves are untouched, so
    nothing that already reads them as plain en-US strings is affected.
    """
    for kpi in kpis:
        value_num = _parse_num(kpi.get("value"))
        if value_num is not None:
            kpi["value_num"] = value_num
            kind, digits = _classify_value(kpi.get("value"))
            kpi["value_kind"] = kind
            kpi["value_digits"] = digits

        delta_parts = _extract_delta_number(kpi.get("delta"))
        if delta_parts is not None:
            template, delta_num, delta_kind, delta_digits = delta_parts
            kpi["delta_template"] = template
            kpi["delta_num"] = delta_num
            kpi["delta_kind"] = delta_kind
            kpi["delta_digits"] = delta_digits

        target_num = _parse_target(kpi.get("delta"))
        if target_num is not None:
            kpi["target_num"] = target_num
            if value_num is not None and target_num:
                # On a lower-is-better metric (DSO, cycle time) the ratio has
                # to invert, or missing the target by 10 days renders as 120%
                # complete instead of 82%.
                ratio = (
                    target_num / value_num
                    if kpi.get("lower_is_better") and value_num
                    else value_num / target_num
                )
                kpi["progress"] = round(max(0.0, min(1.2, ratio)), 4)

        if "status" not in kpi:
            kpi["status"] = "bad" if kpi.get("alert") else "good"

    return kpis


def _stamp_period(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy the payload's period onto every chart in it.

    QC-035: no chart said what span it covered, so a monthly figure and an
    annual one could sit side by side and look comparable. Stamped centrally
    rather than at each of the twenty-two chart definitions, so a chart added
    later cannot arrive unlabelled.
    """
    period = str(payload.get("period") or "")
    if not period:
        return payload
    for group in ("views", "side"):
        for chart in (payload.get(group) or {}).values():
            if isinstance(chart, dict):
                chart.setdefault("period", period)
    return payload


def _chart_points(chart: dict[str, Any]) -> list[dict[str, Any]]:
    """A chart's rows. Line charts nest theirs one level deeper, under series."""
    data = chart.get("data") or []
    if data and isinstance(data[0], dict) and "values" in data[0]:
        return [point for series in data for point in (series.get("values") or [])]
    return [point for point in data if isinstance(point, dict)]


def _options_of(
    element: dict[str, Any],
    column: int = 0,
) -> list[str]:
    """The distinct values one chart or table is keyed by, in display order."""
    if element.get("table"):
        raw = [
            str(row[column])
            for row in element["table"]["rows"]
            if len(row) > column
        ]
    else:
        # A chart may abbreviate its label to fit; `key` carries the full value
        # a filter matches on.
        raw = [
            str(point.get("key") or point.get("label", ""))
            for point in _chart_points(element)
        ]

    seen: set[str] = set()
    return [
        value for value in raw
        if value and not (value in seen or seen.add(value))
    ]


def _filters(
    views: dict[str, Any],
    side: dict[str, Any],
    specs: tuple[tuple[str, str, str, tuple[str, ...], int], ...],
) -> list[dict[str, Any]]:
    """Declare the dimensions this payload can actually be sliced by.

    QC-043: no payload carried a filter parameter, so nothing on the board
    could be narrowed. Options are read back off the built charts rather than
    re-queried, which guarantees a filter can only offer values that are really
    plotted — an option that filters everything away is worse than no filter.

    Each spec is (id, label, source element, elements it applies to, column).
    Element keys are `view:<k>` / `side:<k>`, the same shape the info registry
    uses. A spec whose source is empty is dropped: this dataset predates the
    entity, store and month dimensions the tracker also asks for, and offering
    an empty control would imply otherwise.
    """
    lookup = {f"view:{k}": v for k, v in views.items()}
    lookup |= {f"side:{k}": v for k, v in side.items()}

    built = []
    for filter_id, label, source, applies_to, column in specs:
        element = lookup.get(source)
        options = _options_of(element, column) if element else []
        if len(options) < 2:
            continue
        built.append(
            {
                "id": filter_id,
                "label": label,
                "options": options,
                "applies_to": [k for k in applies_to if k in lookup],
                "column": column,
            }
        )
    return built


def _enriched(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a finished dashboard payload through KPI enrichment and stamping."""
    payload["kpis"] = _enrich_kpis(payload.get("kpis") or [])
    return _stamp_period(payload)


def _round_half_up(value: float, digits: int = 0) -> float:
    """Round .5 away from zero, the way finance reporting does.

    Python and IEEE round half to even, so `round(36.25, 1)` is 36.2. A product
    gross margin of exactly 4,930/13,600 = 36.25% therefore printed as 36.2
    where the workbook reconciliation says 36.3.
    """
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _fmt(n: float, digits: int = 0) -> str:
    """Grouped number for display. Always carries a thousands separator."""
    if digits <= 0:
        return f"{int(_round_half_up(n)):,}"
    return f"{_round_half_up(n, digits):,.{digits}f}"


def _pct(n: float, digits: int = 1) -> str:
    scaled = n * 100 if abs(n) <= 2 else n
    return f"{_round_half_up(scaled, digits):,.{digits}f}%"


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
