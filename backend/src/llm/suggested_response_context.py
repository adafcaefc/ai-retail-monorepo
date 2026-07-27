"""
This file will extract the existing conversation history from the active
AI Chatbot as context for the Suggested Response Agent.
"""
import json
from html.parser import HTMLParser
from typing import Any
from collections.abc import Sequence
from src.llm.suggested_response import (
    ConversationLine,
    SuggestedResponseContext,
)

_BLOCK_TAGS = {
    "article",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}

_IGNORED_TAGS = {
    "script",
    "style",
}

_TOP_LEVEL_TEXT_KEYS = (
    "title",
    "subtitle",
    "heading",
    "summary",
    "description",
    "content",
    "note",
    "label",
    "name",
    "destination",
    "reason",
    "unit",
)

_ITEM_KEYS = (
    "label",
    "name",
    "title",
    "category",
    "series",
    "period",
    "date",
    "value",
    "amount",
    "percentage",
    "unit",
    "default",
    "current",
    "target",
    "destination",
    "reason",
)

_COLLECTION_KEYS = (
    "data",
    "labels",
    "datasets",
    "series",
    "rows",
    "inputs",
    "outputs",
    "routes",
    "categories",
    "points",
)


def _normalize_whitespace(text: str) -> str:
    """Normalize spacing while retaining useful line boundaries."""

    normalized_lines = [
        " ".join(line.split())
        for line in text.splitlines()
    ]

    return "\n".join(
        line
        for line in normalized_lines
        if line
    )


def _truncate(text: str, max_chars: int) -> str:
    """Limit text size without leaving trailing whitespace."""

    if max_chars <= 0:
        return ""

    return text[:max_chars].rstrip()


class _ReadableHTMLParser(HTMLParser):
    """Collect visible HTML text while preserving block boundaries."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs

        tag = tag.lower()

        if tag in _IGNORED_TAGS:
            self._ignored_depth += 1
            return

        if self._ignored_depth == 0 and tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs

        if self._ignored_depth == 0 and tag.lower() in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in _IGNORED_TAGS:
            self._ignored_depth = max(
                0,
                self._ignored_depth - 1,
            )
            return

        if self._ignored_depth == 0 and tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        """Return the accumulated visible text."""

        return _normalize_whitespace(
            "".join(self._parts)
        )


def _html_to_text(html: str) -> str:
    """Convert one HTML fragment into readable text."""

    parser = _ReadableHTMLParser()
    parser.feed(html)
    parser.close()

    return parser.get_text()


def _format_scalar(value: Any) -> str:
    """Convert a simple JSON value into readable text."""

    if value is None:
        return ""

    if isinstance(value, bool):
        return str(value).lower()

    if isinstance(value, (str, int, float)):
        return str(value).strip()

    return ""

def _component_field(
    component: Any,
    field: str,
) -> Any:
    """Read a component field without requiring a static dynamic-model import."""

    if isinstance(component, dict):
        return component.get(field)

    return getattr(component, field, None)


def _component_content(
    component: Any,
) -> dict[str, Any] | None:
    """Parse the validated JSON-object string carried by a Component."""

    raw_content = _component_field(
        component,
        "content",
    )

    if not isinstance(raw_content, str):
        return None

    try:
        parsed = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed


def _component_title(
    content: dict[str, Any],
) -> list[str]:
    title = _format_scalar(
        content.get("title")
    )

    return [title] if title else []


def _extract_text_component(
    content: dict[str, Any],
) -> str:
    parts = _component_title(content)
    body = _format_scalar(
        content.get("content")
    )

    if body:
        parts.append(body)

    return "\n".join(parts)


def _extract_bullet_list_component(
    content: dict[str, Any],
) -> str:
    parts = _component_title(content)
    bullets = content.get("bullets")

    if isinstance(bullets, list):
        for bullet in bullets:
            text = _format_scalar(bullet)

            if text:
                parts.append(f"- {text}")

    return "\n".join(parts)


def _extract_table_component(
    content: dict[str, Any],
    *,
    max_rows: int,
) -> str:
    parts = _component_title(content)
    raw_columns = content.get("columns")

    columns = (
        [
            _format_scalar(column)
            for column in raw_columns
        ]
        if isinstance(raw_columns, list)
        else []
    )
    columns = [
        column
        for column in columns
        if column
    ]

    if columns:
        parts.append(
            f"Columns: {' | '.join(columns)}"
        )

    rows = content.get("rows")

    if isinstance(rows, list):
        for row_number, row in enumerate(
            rows[:max(0, max_rows)],
            start=1,
        ):
            if not isinstance(row, list):
                continue

            cells: list[str] = []

            for index, value in enumerate(row):
                value_text = _format_scalar(value)

                if not value_text:
                    continue

                if index < len(columns):
                    cells.append(
                        f"{columns[index]}: {value_text}"
                    )
                else:
                    cells.append(value_text)

            if cells:
                parts.append(
                    f"Row {row_number}: "
                    f"{' | '.join(cells)}"
                )

    return "\n".join(parts)


def _extract_chart_component(
    content: dict[str, Any],
    *,
    max_points: int,
) -> str:
    parts = _component_title(content)
    x_axis_title = _format_scalar(
        content.get("x_axis_title")
    )
    y_axis_title = _format_scalar(
        content.get("y_axis_title")
    )
    unit = _format_scalar(
        content.get("unit")
    )

    if x_axis_title:
        parts.append(
            f"X-axis: {x_axis_title}"
        )

    if y_axis_title:
        parts.append(
            f"Y-axis: {y_axis_title}"
        )
    elif unit:
        parts.append(f"Unit: {unit}")

    data = content.get("data")
    remaining = max(0, max_points)

    if (
        not isinstance(data, list)
        or remaining == 0
    ):
        return "\n".join(parts)

    for item in data:
        if remaining == 0:
            break

        if not isinstance(item, dict):
            continue

        values = item.get("values")

        if isinstance(values, list):
            legend = _format_scalar(
                item.get("legend")
            )

            for point in values:
                if remaining == 0:
                    break

                if not isinstance(point, dict):
                    continue

                label = _format_scalar(
                    point.get("label")
                )
                value = _format_scalar(
                    point.get("value")
                )

                if label and value:
                    prefix = (
                        f"{legend} — "
                        if legend
                        else ""
                    )
                    parts.append(
                        f"{prefix}{label}: {value}"
                    )
                    remaining -= 1

            continue

        label = _format_scalar(
            item.get("label")
        )
        value = _format_scalar(
            item.get("value")
        )

        if label and value:
            parts.append(
                f"{label}: {value}"
            )
            remaining -= 1

    return "\n".join(parts)


def _extract_recommendation_component(
    content: dict[str, Any],
) -> str:
    parts = _component_title(content)
    recommendations = content.get(
        "recommendations"
    )

    if not isinstance(recommendations, list):
        return "\n".join(parts)

    for recommendation in recommendations:
        if not isinstance(
            recommendation,
            dict,
        ):
            continue

        action = _format_scalar(
            recommendation.get("action")
        )
        expected_impact = _format_scalar(
            recommendation.get(
                "expected_impact"
            )
        )

        if action:
            parts.append(
                f"Action: {action}"
            )

        if expected_impact:
            parts.append(
                "Expected impact: "
                f"{expected_impact}"
            )

        for label, key in (
            ("Assumption", "assumptions"),
            ("Risk", "risks"),
        ):
            values = recommendation.get(key)

            if not isinstance(values, list):
                continue

            for value in values:
                text = _format_scalar(value)

                if text:
                    parts.append(
                        f"{label}: {text}"
                    )

    return "\n".join(parts)


def _extract_confidence_component(
    content: dict[str, Any],
) -> str:
    parts = _component_title(content)
    assessments = content.get(
        "assessments"
    )

    if not isinstance(assessments, list):
        return "\n".join(parts)

    for assessment in assessments:
        if not isinstance(assessment, dict):
            continue

        claim = _format_scalar(
            assessment.get("claim")
        )
        score = _format_scalar(
            assessment.get("score")
        )
        rationale = _format_scalar(
            assessment.get("rationale")
        )

        if claim:
            parts.append(
                f"Claim: {claim}"
            )

        if score:
            parts.append(
                f"Confidence: {score}"
            )

        if rationale:
            parts.append(
                f"Rationale: {rationale}"
            )

    return "\n".join(parts)


def _extract_simulation_component(
    content: dict[str, Any],
) -> str:
    parts = _component_title(content)
    inputs = content.get("inputs")

    if isinstance(inputs, list):
        for input_value in inputs:
            if not isinstance(input_value, dict):
                continue

            label = _format_scalar(
                input_value.get("label")
            )
            default = _format_scalar(
                input_value.get("default")
            )
            minimum = _format_scalar(
                input_value.get("min")
            )
            maximum = _format_scalar(
                input_value.get("max")
            )
            step = _format_scalar(
                input_value.get("step")
            )
            unit = _format_scalar(
                input_value.get("unit")
            )
            unit_suffix = (
                f" {unit}"
                if unit
                else ""
            )
            details: list[str] = []

            if default:
                details.append(
                    f"default {default}{unit_suffix}"
                )

            if minimum and maximum:
                details.append(
                    "range "
                    f"{minimum}–{maximum}"
                    f"{unit_suffix}"
                )

            if step:
                details.append(
                    f"step {step}{unit_suffix}"
                )

            if label:
                detail_text = (
                    f": {'; '.join(details)}"
                    if details
                    else ""
                )
                parts.append(
                    f"Input: {label}{detail_text}"
                )

    outputs = content.get("outputs")

    if isinstance(outputs, list):
        for output in outputs:
            if not isinstance(output, dict):
                continue

            label = _format_scalar(
                output.get("label")
            )
            value = _format_scalar(
                output.get("value")
            )
            unit = _format_scalar(
                output.get("unit")
            )

            if not label:
                continue

            if value:
                unit_suffix = (
                    f" {unit}"
                    if unit
                    else ""
                )
                parts.append(
                    f"Output: {label}: "
                    f"{value}{unit_suffix}"
                )
            elif unit:
                parts.append(
                    f"Output: {label} "
                    f"(unit: {unit})"
                )
            else:
                parts.append(
                    f"Output: {label}"
                )

    return "\n".join(parts)


def _extract_next_route_component(
    content: dict[str, Any],
) -> str:
    parts = _component_title(content)
    routes = content.get("routes")

    if not isinstance(routes, list):
        return "\n".join(parts)

    for route in routes:
        if not isinstance(route, dict):
            continue

        destination = _format_scalar(
            route.get("destination")
        )
        reason = _format_scalar(
            route.get("reason")
        )

        if destination and reason:
            parts.append(
                f"Route: {destination} — {reason}"
            )
        elif destination:
            parts.append(
                f"Route: {destination}"
            )
        elif reason:
            parts.append(
                f"Route reason: {reason}"
            )

    return "\n".join(parts)


_SEMANTIC_COMPONENT_EXTRACTORS = {
    "text": _extract_text_component,
    "bullet_list": (
        _extract_bullet_list_component
    ),
    "recommendation": (
        _extract_recommendation_component
    ),
    "confidence": (
        _extract_confidence_component
    ),
    "simulation": (
        _extract_simulation_component
    ),
    "next_route": (
        _extract_next_route_component
    ),
}


def extract_current_assistant_text(
    components: Sequence[Any],
    *,
    max_chars: int = 6_000,
    max_table_rows: int = 5,
    max_chart_points: int = 8,
) -> str:
    """Extract bounded readable text from semantic FinanceAgentOutput components."""

    if (
        isinstance(components, (str, bytes))
        or not isinstance(components, Sequence)
    ):
        return ""

    parts: list[str] = []

    for component in components:
        component_format = _component_field(
            component,
            "format",
        )
        content = _component_content(component)

        if (
            not isinstance(
                component_format,
                str,
            )
            or content is None
        ):
            continue

        if component_format == "table":
            text = _extract_table_component(
                content,
                max_rows=max_table_rows,
            )
        elif component_format == "chart":
            text = _extract_chart_component(
                content,
                max_points=max_chart_points,
            )
        else:
            extractor = (
                _SEMANTIC_COMPONENT_EXTRACTORS
                .get(component_format)
            )
            text = (
                extractor(content)
                if extractor is not None
                else ""
            )

        if text:
            parts.append(text)

    text = _normalize_whitespace(
        "\n".join(parts)
    )

    return _truncate(
        text,
        max_chars,
    )

def _summarize_item(
    item: Any,
    *,
    max_nested_values: int = 8,
) -> str:
    """Extract useful financial fields from one structured item."""

    scalar = _format_scalar(item)

    if scalar:
        return scalar

    if not isinstance(item, dict):
        return ""

    parts: list[str] = []

    for key in _ITEM_KEYS:
        text = _format_scalar(item.get(key))

        if text:
            parts.append(f"{key}: {text}")

    nested_data = item.get("data")

    if isinstance(nested_data, list):
        values = [
            _format_scalar(value)
            for value in nested_data[:max_nested_values]
        ]
        values = [
            value
            for value in values
            if value
        ]

        if values:
            parts.append(
                f"values: {', '.join(values)}"
            )

    return ", ".join(parts)


def _summarize_structured_data(
    data: dict[str, Any],
    *,
    max_items: int = 8,
) -> str:
    """Create a bounded readable summary of structured block data."""

    parts: list[str] = []

    for key in _TOP_LEVEL_TEXT_KEYS:
        text = _format_scalar(data.get(key))

        if not text:
            continue

        if key in {"destination", "reason"}:
            parts.append(f"{key}: {text}")
        else:
            parts.append(text)

    for key in _COLLECTION_KEYS:
        items = data.get(key)

        if not isinstance(items, list):
            continue

        for item in items[:max_items]:
            text = _summarize_item(item)

            if text:
                parts.append(text)

    return _normalize_whitespace(
        "\n".join(parts)
    )


def _extract_block_text(block: Any) -> str:
    """Extract readable text from one persisted UI block."""

    scalar = _format_scalar(block)

    if scalar:
        return scalar

    if not isinstance(block, dict):
        return ""

    block_type = block.get("type")
    data = block.get("data")

    if block_type == "html":
        if not isinstance(data, dict):
            return ""

        html = data.get("html")

        if not isinstance(html, str):
            return ""

        return _html_to_text(html)

    if isinstance(data, dict):
        return _summarize_structured_data(data)

    # Defensive support for legacy dictionaries that may not use
    # the standard {"type": ..., "data": ...} block structure.
    return _summarize_structured_data(block)


def extract_blocks_text(
    blocks: list[Any] | dict[str, Any],
    *,
    max_chars: int = 3_000,
) -> str:
    """Convert one or more UI blocks into bounded readable text."""

    if isinstance(blocks, dict):
        raw_blocks: list[Any] = [blocks]
    elif isinstance(blocks, list):
        raw_blocks = blocks
    else:
        return ""

    parts = [
        _extract_block_text(block)
        for block in raw_blocks
    ]

    text = _normalize_whitespace(
        "\n".join(
            part
            for part in parts
            if part
        )
    )

    return _truncate(text, max_chars)


def extract_persisted_assistant_text(
    message: str,
    *,
    max_chars: int = 3_000,
) -> str:
    """Convert a stored assistant message into bounded readable text.

    Supports serialized UI blocks, JSON strings, raw HTML, legacy plain
    text, malformed JSON, empty messages, and unknown block types.
    """

    if not isinstance(message, str):
        return ""

    message = message.strip()

    if not message:
        return ""

    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        if "<" in message and ">" in message:
            text = _html_to_text(message)
        else:
            text = _normalize_whitespace(message)

        return _truncate(text, max_chars)

    if isinstance(parsed, (list, dict)):
        return extract_blocks_text(
            parsed,
            max_chars=max_chars,
        )

    if isinstance(parsed, str):
        return _truncate(
            _normalize_whitespace(parsed),
            max_chars,
        )

    return ""

def normalize_history_row(
    row: dict[str, Any],
) -> ConversationLine | None:
    """Convert one database history row into suggestion context."""

    sender = row.get("sender")
    message = row.get("message")

    if sender not in {"user", "chatbot"}:
        return None

    if not isinstance(message, str):
        return None

    if sender == "user":
        normalized_sender = "user"
        text = _normalize_whitespace(message)
    else:
        normalized_sender = "assistant"
        text = extract_persisted_assistant_text(message)

    if not text:
        return None

    return ConversationLine(
        sender=normalized_sender,
        text=text,
    )


def select_recent_turns(
    lines: list[ConversationLine],
    *,
    max_user_turns: int = 2,
    max_messages: int = 6,
) -> list[ConversationLine]:
    """Select the most recent completed conversation turns."""

    if max_user_turns <= 0 or max_messages <= 0:
        return []

    selected: list[ConversationLine] = []
    user_turns = 0

    for line in reversed(lines):
        selected.append(line)

        if line.sender == "user":
            user_turns += 1

            if user_turns >= max_user_turns:
                break

        if len(selected) >= max_messages:
            break

    selected.reverse()
    return selected


def build_recent_history(
    history: list[dict[str, Any]],
    *,
    channel: str,
    latest_user_question: str,
    max_user_turns: int = 2,
) -> list[ConversationLine]:
    """Build suggestion history from the captured database snapshot."""

    channel_history = [
        row
        for row in history
        if row.get("channel") == channel
    ]

    prior_history = list(channel_history)

    # The current user question was saved before history was loaded.
    # Remove it because SuggestedResponseContext stores it separately.
    if prior_history:
        latest_row = prior_history[-1]
        latest_message = latest_row.get("message")

        if (
            latest_row.get("sender") == "user"
            and isinstance(latest_message, str)
            and latest_message.strip()
            == latest_user_question.strip()
        ):
            prior_history.pop()

    normalized_lines: list[ConversationLine] = []

    for row in prior_history:
        line = normalize_history_row(row)

        if line is not None:
            normalized_lines.append(line)

    return select_recent_turns(
        normalized_lines,
        max_user_turns=max_user_turns,
    )

def build_suggested_response_context(
    *,
    history: list[dict[str, Any]],
    channel: str,
    agent_type: str,
    latest_user_question: str,
    latest_assistant_answer: str,
) -> SuggestedResponseContext:
    """Build the complete context for suggested-response generation."""

    question = _truncate(
        _normalize_whitespace(latest_user_question),
        1_500,
    )

    answer = _truncate(
        _normalize_whitespace(latest_assistant_answer),
        6_000,
    )

    recent_history = build_recent_history(
        history,
        channel=channel,
        latest_user_question=question,
        max_user_turns=2,
    )

    return SuggestedResponseContext(
        agent_type=agent_type.strip(),
        latest_user_question=question,
        latest_assistant_answer=answer,
        recent_history=recent_history,
    )