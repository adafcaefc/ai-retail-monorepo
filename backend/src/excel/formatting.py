"""Pure helpers that turn openpyxl cell state into JSON the viewer can render.

Nothing here touches the filesystem or FastAPI, so every guard below is
testable without loading the 10 MB workbook.

Cell payloads use short keys and omit every default, because a page is up to
500 rows x 31 columns and the verbose form is roughly four times the bytes for
no extra information. The legend, used by
`frontend/src/pages/main/data_source/cellStyle.js`:

    v   display string (already formatted; absent when empty)
    t   "n" when the underlying value is numeric -> right-aligned by default
    b   bold
    i   italic
    a   horizontal alignment: "left" | "center" | "right"
    va  vertical alignment: "top" | "middle" | "bottom"
    w   wrap text
    fg  font colour, "#RRGGBB"
    bg  solid fill colour, "#RRGGBB"

A cell with nothing to say serialises as null, not {}.
"""

from __future__ import annotations

import math

from datetime import (
    date,
    datetime,
    time,
)

from decimal import Decimal
from typing import Any


# Excel's "maximum digit width" for the default font. A column's stored width
# is in character units; px = width * MDW + padding is the conversion Excel
# itself documents.
_MAX_DIGIT_WIDTH = 7
_COLUMN_PADDING = 5

# Widths are clamped so one absurd column cannot push the grid off screen:
# 'LISTING' stores column C at width 98, which is 691px unclamped, next to a
# 220px sidebar.
MIN_COLUMN_PX = 32
MAX_COLUMN_PX = 420

# openpyxl's fallback when a sheet declares no default column width.
DEFAULT_COLUMN_WIDTH = 8.43

_HORIZONTAL_ALIGNMENTS = {
    "left",
    "center",
    "right",
}

# openpyxl says "center", CSS vertical-align says "middle".
_VERTICAL_ALIGNMENTS = {
    "top": "top",
    "center": "middle",
    "bottom": "bottom",
}

# Colours equal to the CSS defaults are dropped so cells inherit --ink and the
# surface behind them, which keeps the payload small and the page themable.
_IGNORED_FONT_COLOURS = {"000000"}
_IGNORED_FILL_COLOURS = {"FFFFFF"}


def rgb_hex(
    color: Any,
) -> str:
    """An ARGB colour as "RRGGBB", or "" when openpyxl cannot resolve it.

    The isinstance check has to come first. On a theme-coloured cell `.rgb` is
    not a bad string but an openpyxl RGB *descriptor object*: str() of it reads
    "Values must be of type <class 'str'>" and slicing it raises TypeError. The
    workbook uses thousands of theme colours, so a len()/slice guard alone
    would crash the endpoint outright.
    """
    if color is None:
        return ""

    if getattr(color, "type", None) != "rgb":
        # theme / indexed / auto -> let CSS decide.
        return ""

    raw = color.rgb

    if not isinstance(raw, str):
        return ""

    if len(raw) == 8:
        # Fully transparent is openpyxl's "no colour set", and it is what an
        # unfilled cell reports (00000000). Emitting it paints every blank
        # cell solid black.
        if raw[:2] == "00":
            return ""
        return raw[2:].upper()

    if len(raw) == 6:
        return raw.upper()

    return ""


def font_colour(
    font: Any,
) -> str:
    if font is None:
        return ""

    value = rgb_hex(font.color)

    if value in _IGNORED_FONT_COLOURS:
        return ""

    return value


def fill_colour(
    fill: Any,
) -> str:
    """A solid fill's colour, or "" for every other pattern type.

    Gradient and pattern fills are deliberately dropped rather than
    approximated -- the workbook uses solid fills exclusively.
    """
    if fill is None or fill.patternType != "solid":
        return ""

    value = rgb_hex(fill.fgColor)

    if value in _IGNORED_FILL_COLOURS:
        return ""

    return value


def column_width_px(
    width: float | None,
    default_width: float | None = None,
) -> int:
    effective = width

    if effective is None:
        effective = default_width or DEFAULT_COLUMN_WIDTH

    pixels = round(
        effective * _MAX_DIGIT_WIDTH
    ) + _COLUMN_PADDING

    return max(
        MIN_COLUMN_PX,
        min(
            MAX_COLUMN_PX,
            pixels,
        ),
    )


def is_numeric(
    value: Any,
) -> bool:
    # bool is a subclass of int, and TRUE/FALSE are not right-aligned numbers.
    if isinstance(value, bool):
        return False

    return isinstance(
        value,
        (int, float, Decimal),
    )


def format_value(
    value: Any,
    number_format: str | None,
) -> str:
    """The string Excel would show for this cell.

    Only the five number formats the workbook actually uses are implemented.
    Anything else falls back to General, which is what Excel does for a format
    it cannot apply -- this is deliberately not a general format engine.
    """
    if value is None:
        return ""

    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"

    if isinstance(
        value,
        (datetime, date, time),
    ):
        return value.isoformat()

    if isinstance(value, Decimal):
        value = float(value)

    if not isinstance(
        value,
        (int, float),
    ):
        return str(value)

    if isinstance(value, float) and (
        math.isnan(value)
        or math.isinf(value)
    ):
        return ""

    pattern = (number_format or "").strip()

    if pattern == "#,##0":
        return f"{value:,.0f}"

    if pattern == "0.0":
        return f"{value:.1f}"

    if pattern == "0.00":
        return f"{value:.2f}"

    if pattern == "0.0%":
        return f"{value * 100:.1f}%"

    return _format_general(value)


def _format_general(
    value: int | float,
) -> str:
    if isinstance(value, int):
        return str(value)

    if value.is_integer():
        return str(int(value))

    # %.10g keeps 7.45 from rendering as 7.450000000000001 while staying close
    # to the ~11 significant digits Excel shows for General.
    return f"{value:.10g}"


def cell_payload(
    cell: Any,
) -> dict[str, Any] | None:
    """One cell as a short-key dict, or None when it has nothing to render."""
    payload: dict[str, Any] = {}

    text = format_value(
        cell.value,
        cell.number_format,
    )

    if text:
        payload["v"] = text

    if is_numeric(cell.value):
        payload["t"] = "n"

    font = cell.font

    if font is not None:
        if font.bold:
            payload["b"] = True

        if font.italic:
            payload["i"] = True

        colour = font_colour(font)

        if colour:
            payload["fg"] = f"#{colour}"

    background = fill_colour(cell.fill)

    if background:
        payload["bg"] = f"#{background}"

    alignment = cell.alignment

    if alignment is not None:
        if alignment.horizontal in _HORIZONTAL_ALIGNMENTS:
            payload["a"] = alignment.horizontal

        vertical = _VERTICAL_ALIGNMENTS.get(
            alignment.vertical or ""
        )

        if vertical:
            payload["va"] = vertical

        if alignment.wrap_text:
            payload["w"] = True

    return payload or None
