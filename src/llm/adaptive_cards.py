from __future__ import annotations

import json
import math
from typing import Any


ADAPTIVE_CARD_VERSION = "1.5"

_CHART_TYPES = {
    "Chart.Donut",
    "Chart.Line",
    "Chart.Pie",
    "Chart.VerticalBar",
}

_ELEMENT_TYPES = {
    "ActionSet",
    "Column",
    "ColumnSet",
    "Container",
    "FactSet",
    "Image",
    "Input.ChoiceSet",
    "Input.Number",
    "Table",
    "TableCell",
    "TableRow",
    "TextBlock",
    *_CHART_TYPES,
}

_ACTION_TYPES = {
    "Action.OpenUrl",
    "Action.Submit",
    "Action.ToggleVisibility",
}


class AdaptiveCardError(ValueError):
    pass


def _text(
    value: Any,
    *,
    weight: str | None = None,
    size: str | None = None,
    subtle: bool = False,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "TextBlock",
        "text": str(value),
        "wrap": True,
    }
    if weight:
        block["weight"] = weight
    if size:
        block["size"] = size
    if subtle:
        block["isSubtle"] = True
    return block


def _parse_content(component: Any) -> dict[str, Any]:
    content = getattr(component, "content", None)
    if isinstance(component, dict):
        content = component.get("content")

    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError as error:
            raise AdaptiveCardError(
                "Component content is not valid JSON."
            ) from error

    if not isinstance(content, dict):
        raise AdaptiveCardError(
            "Component content must decode to a JSON object."
        )

    return content


def _component_format(component: Any) -> str:
    value = getattr(component, "format", None)
    if isinstance(component, dict):
        value = component.get("format")
    return str(value or "unknown").lower()


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = value
    elif isinstance(value, str):
        cleaned = (
            value.replace(",", "")
            .replace("IDR", "")
            .replace("USD", "")
            .replace("%", "")
            .strip()
        )
        try:
            number = float(cleaned)
        except ValueError:
            return None
    else:
        return None

    if not math.isfinite(number):
        return None

    if float(number).is_integer():
        return int(number)
    return float(number)


def _point_label(point: dict[str, Any], index: int) -> str | int | float:
    for key in ("x", "label", "name", "category", "week", "period"):
        value = point.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            return value
    return index + 1


def _point_value(point: dict[str, Any]) -> int | float | None:
    for key in ("y", "value", "amount"):
        number = _number(point.get(key))
        if number is not None:
            return number
    return None


def _chart_fallback(
    title: str,
    series: list[tuple[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    facts: list[dict[str, str]] = []
    for legend, values in series:
        for index, point in enumerate(values):
            label = _point_label(point, index)
            value = _point_value(point)
            if value is not None:
                fact_title = f"{legend} - {label}" if legend else str(label)
                facts.append({"title": fact_title, "value": f"{value:,}"})

    items: list[dict[str, Any]] = [
        _text(f"{title} data", weight="Bolder"),
    ]
    if facts:
        items.append({"type": "FactSet", "facts": facts[:30]})
    else:
        items.append(_text("No numeric chart data was available."))

    return {
        "type": "Container",
        "items": items,
    }


def _axis_properties(content: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    x_axis_title = content.get("x_axis_title") or content.get("xAxisTitle")
    y_axis_title = content.get("y_axis_title") or content.get("yAxisTitle")
    if x_axis_title:
        properties["xAxisTitle"] = str(x_axis_title)
    if y_axis_title:
        properties["yAxisTitle"] = str(y_axis_title)
    return properties


def _line_chart(
    title: str,
    data: list[Any],
    content: dict[str, Any],
) -> dict[str, Any]:
    raw_series: list[tuple[str, list[dict[str, Any]]]] = []
    if data and all(
        isinstance(item, dict) and isinstance(item.get("values"), list)
        for item in data
    ):
        for item in data:
            values = [value for value in item["values"] if isinstance(value, dict)]
            raw_series.append((str(item.get("legend") or title), values))
    else:
        values = [item for item in data if isinstance(item, dict)]
        raw_series.append((str(content.get("legend") or title), values))

    chart_series: list[dict[str, Any]] = []
    for legend, values in raw_series:
        points: list[dict[str, Any]] = []
        for index, point in enumerate(values):
            value = _point_value(point)
            if value is not None:
                points.append(
                    {
                        "x": _point_label(point, index),
                        "y": value,
                    }
                )
        if points:
            chart_series.append({"legend": legend, "values": points})

    if not chart_series:
        return _chart_fallback(title, raw_series)

    return {
        "type": "Chart.Line",
        "title": title,
        "showTitle": True,
        "showLegend": len(chart_series) > 1,
        "colorSet": "categorical",
        "data": chart_series,
        "fallback": _chart_fallback(title, raw_series),
        **_axis_properties(content),
    }


def _vertical_bar_chart(
    title: str,
    data: list[Any],
    content: dict[str, Any],
) -> dict[str, Any]:
    values = [item for item in data if isinstance(item, dict)]
    points: list[dict[str, Any]] = []
    for index, point in enumerate(values):
        value = _point_value(point)
        if value is not None:
            rendered_point: dict[str, Any] = {
                "x": _point_label(point, index),
                "y": value,
            }
            if point.get("color"):
                rendered_point["color"] = str(point["color"])
            points.append(rendered_point)

    if not points:
        return _chart_fallback(title, [("", values)])

    return {
        "type": "Chart.VerticalBar",
        "title": title,
        "showTitle": True,
        "showLegend": False,
        "showBarValues": True,
        "colorSet": "categorical",
        "data": points,
        "fallback": _chart_fallback(title, [("", values)]),
        **_axis_properties(content),
    }


def _circular_chart(
    title: str,
    chart_type: str,
    data: list[Any],
) -> dict[str, Any]:
    values = [item for item in data if isinstance(item, dict)]
    points: list[dict[str, Any]] = []
    for index, point in enumerate(values):
        value = _point_value(point)
        if value is not None:
            rendered_point: dict[str, Any] = {
                "legend": str(_point_label(point, index)),
                "value": value,
            }
            if point.get("color"):
                rendered_point["color"] = str(point["color"])
            points.append(rendered_point)

    if not points:
        return _chart_fallback(title, [("", values)])

    return {
        "type": chart_type,
        "title": title,
        "showTitle": True,
        "showLegend": True,
        "colorSet": "categorical",
        "data": points,
        "fallback": _chart_fallback(title, [("", values)]),
    }


def _render_chart(content: dict[str, Any]) -> dict[str, Any]:
    title = str(content.get("title") or "Financial chart")
    chart_type = str(content.get("chart_type") or "bar").lower()
    data = content.get("data")
    if not isinstance(data, list):
        data = []

    if chart_type in {"line", "area", "scatter"}:
        return _line_chart(title, data, content)
    if chart_type == "pie":
        return _circular_chart(title, "Chart.Pie", data)
    if chart_type in {"donut", "doughnut"}:
        return _circular_chart(title, "Chart.Donut", data)
    return _vertical_bar_chart(title, data, content)


def _render_table(content: dict[str, Any]) -> dict[str, Any]:
    title = str(content.get("title") or "Financial data")
    columns = content.get("columns")
    rows = content.get("rows")
    if not isinstance(columns, list) or not columns:
        return {
            "type": "Container",
            "items": [_text(title, weight="Bolder"), _text("No table columns were provided.")],
        }
    if not isinstance(rows, list):
        rows = []

    table_rows: list[dict[str, Any]] = []
    header_cells = [
        {
            "type": "TableCell",
            "items": [_text(column, weight="Bolder")],
        }
        for column in columns
    ]
    table_rows.append({"type": "TableRow", "cells": header_cells})

    for row in rows:
        values = row if isinstance(row, list) else [row]
        cells = []
        for index in range(len(columns)):
            value = values[index] if index < len(values) else ""
            cells.append(
                {
                    "type": "TableCell",
                    "items": [_text(value)],
                }
            )
        table_rows.append({"type": "TableRow", "cells": cells})

    return {
        "type": "Container",
        "items": [
            _text(title, weight="Bolder", size="Medium"),
            {
                "type": "Table",
                "firstRowAsHeaders": True,
                "showGridLines": True,
                "columns": [{"width": 1} for _ in columns],
                "rows": table_rows,
            },
        ],
    }


def _render_recommendations(content: dict[str, Any]) -> dict[str, Any]:
    title = str(content.get("title") or "Recommendations")
    recommendations = content.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []

    items: list[dict[str, Any]] = [_text(title, weight="Bolder", size="Medium")]
    for index, recommendation in enumerate(recommendations, start=1):
        if not isinstance(recommendation, dict):
            continue
        recommendation_items = [
            _text(
                f"{index}. {recommendation.get('action', 'Action')}",
                weight="Bolder",
            )
        ]
        expected_impact = recommendation.get("expected_impact")
        if expected_impact:
            recommendation_items.append(_text(f"Impact: {expected_impact}"))
        for label, key in (("Assumptions", "assumptions"), ("Risks", "risks")):
            values = recommendation.get(key)
            if isinstance(values, list) and values:
                recommendation_items.append(
                    _text(f"{label}: " + "; ".join(map(str, values)), subtle=True)
                )
        items.append(
            {
                "type": "Container",
                "separator": index > 1,
                "items": recommendation_items,
            }
        )

    return {"type": "Container", "items": items}


def _render_simulation(
    content: dict[str, Any],
    source_agent: str,
) -> dict[str, Any]:
    title = str(content.get("title") or "Financial simulation")
    inputs = content.get("inputs")
    outputs = content.get("outputs")
    if not isinstance(inputs, list):
        inputs = []
    if not isinstance(outputs, list):
        outputs = []

    items: list[dict[str, Any]] = [_text(title, weight="Bolder", size="Medium")]
    instructions = content.get("calculation_instructions")
    if instructions:
        items.append(_text(instructions, subtle=True))

    for input_definition in inputs:
        if not isinstance(input_definition, dict):
            continue
        input_id = str(
            input_definition.get("id")
            or input_definition.get("name")
            or input_definition.get("label")
            or "input"
        )
        label = str(input_definition.get("label") or input_id)
        unit = str(input_definition.get("unit") or "")
        number_input: dict[str, Any] = {
            "type": "Input.Number",
            "id": input_id,
            "label": f"{label} ({unit})" if unit else label,
        }
        for source_key, target_key in (
            ("min", "min"),
            ("max", "max"),
            ("value", "value"),
            ("default", "value"),
        ):
            value = _number(input_definition.get(source_key))
            if value is not None and target_key not in number_input:
                number_input[target_key] = value
        items.append(number_input)

    facts: list[dict[str, str]] = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        label = str(output.get("label") or output.get("name") or "Result")
        value = output.get("value", "Recalculate to update")
        unit = str(output.get("unit") or "")
        rendered_value = f"{value} {unit}".strip()
        facts.append({"title": label, "value": rendered_value})
    if facts:
        items.extend([_text("Results", weight="Bolder"), {"type": "FactSet", "facts": facts}])

    expected_outputs = [
        str(output.get("label") or output.get("name"))
        for output in outputs
        if isinstance(output, dict) and (output.get("label") or output.get("name"))
    ]
    action_data = {
        "action": str(content.get("action") or "recalculate_simulation"),
        "source_agent": source_agent,
        "simulation_id": str(content.get("simulation_id") or "runtime_simulation"),
        "simulation_title": title,
        "calculation_instructions": str(instructions or ""),
        "expected_outputs": expected_outputs,
        "original_inputs": json.dumps(inputs, ensure_ascii=True),
        "original_outputs": json.dumps(outputs, ensure_ascii=True),
    }
    submit_data = content.get("submit_data")
    if isinstance(submit_data, dict):
        for key, value in submit_data.items():
            if isinstance(key, str) and isinstance(
                value,
                (str, int, float, bool),
            ):
                action_data[key] = value
    items.append(
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.Submit",
                    "id": str(
                        content.get("action")
                        or "recalculate_simulation"
                    ),
                    "title": "Recalculate",
                    "associatedInputs": "auto",
                    "data": action_data,
                }
            ],
        }
    )

    return {"type": "Container", "items": items}


def _render_next_routes(content: dict[str, Any]) -> dict[str, Any]:
    title = str(content.get("title") or "Suggested follow-up")
    routes = content.get("routes")
    if not isinstance(routes, list):
        routes = []
    items = [_text(title, weight="Bolder", size="Medium")]
    for route in routes:
        if not isinstance(route, dict):
            continue
        destination = route.get("destination") or "Next team"
        reason = route.get("reason") or ""
        items.extend([_text(destination, weight="Bolder"), _text(reason, subtle=True)])
    return {"type": "Container", "items": items}


def _render_text(content: dict[str, Any]) -> dict[str, Any]:
    title = str(content.get("title") or "Analysis")
    body = content.get("content") or content.get("text") or ""
    return {
        "type": "Container",
        "items": [
            _text(title, weight="Bolder", size="Medium"),
            _text(body),
        ],
    }


def render_finance_agent_output(agent_output: Any) -> dict[str, Any]:
    components = getattr(agent_output, "components", None)
    source_agent = str(getattr(agent_output, "agent", "Finance"))
    if isinstance(agent_output, dict):
        components = agent_output.get("components")
        source_agent = str(agent_output.get("agent") or "Finance")
    if not isinstance(components, list) or not components:
        raise AdaptiveCardError("Finance agent output contains no components.")

    body: list[dict[str, Any]] = [
        _text(f"{source_agent} analysis", weight="Bolder", size="Large")
    ]
    for component in components:
        try:
            content = _parse_content(component)
            component_format = _component_format(component)
            if component_format == "text":
                rendered = _render_text(content)
            elif component_format == "table":
                rendered = _render_table(content)
            elif component_format == "chart":
                rendered = _render_chart(content)
            elif component_format in {"recommendation", "reccomendation"}:
                rendered = _render_recommendations(content)
            elif component_format == "simulation":
                rendered = _render_simulation(content, source_agent)
            elif component_format == "next_route":
                rendered = _render_next_routes(content)
            else:
                rendered = _render_text(
                    {
                        "title": "Unsupported component",
                        "content": json.dumps(content, ensure_ascii=True),
                    }
                )
        except AdaptiveCardError as error:
            rendered = _render_text(
                {
                    "title": "Component could not be rendered",
                    "content": str(error),
                }
            )
        rendered["separator"] = True
        body.append(rendered)

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": ADAPTIVE_CARD_VERSION,
        "fallbackText": f"{source_agent} analysis is available in Microsoft Teams.",
        "msteams": {"width": "Full"},
        "body": body,
    }
    validate_adaptive_card(card)
    return card


def _validate_number(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdaptiveCardError(f"{path} must be numeric.")
    if not math.isfinite(value):
        raise AdaptiveCardError(f"{path} must be finite.")


def _validate_chart(element: dict[str, Any], path: str) -> None:
    chart_type = element["type"]
    data = element.get("data")
    if not isinstance(data, list) or not data:
        raise AdaptiveCardError(f"{path}.data must be a non-empty list.")

    if chart_type == "Chart.Line":
        for series_index, series in enumerate(data):
            if not isinstance(series, dict) or not isinstance(series.get("legend"), str):
                raise AdaptiveCardError(
                    f"{path}.data[{series_index}] must contain a legend."
                )
            values = series.get("values")
            if not isinstance(values, list) or not values:
                raise AdaptiveCardError(
                    f"{path}.data[{series_index}].values must be non-empty."
                )
            for value_index, value in enumerate(values):
                if not isinstance(value, dict) or "x" not in value:
                    raise AdaptiveCardError(
                        f"{path}.data[{series_index}].values[{value_index}] is invalid."
                    )
                _validate_number(
                    value.get("y"),
                    f"{path}.data[{series_index}].values[{value_index}].y",
                )
        return

    for index, point in enumerate(data):
        if not isinstance(point, dict):
            raise AdaptiveCardError(f"{path}.data[{index}] must be an object.")
        if chart_type == "Chart.VerticalBar":
            if "x" not in point:
                raise AdaptiveCardError(f"{path}.data[{index}].x is required.")
            _validate_number(point.get("y"), f"{path}.data[{index}].y")
        else:
            if not isinstance(point.get("legend"), str):
                raise AdaptiveCardError(f"{path}.data[{index}].legend is required.")
            _validate_number(point.get("value"), f"{path}.data[{index}].value")


def _walk_element(element: Any, path: str) -> None:
    if not isinstance(element, dict):
        raise AdaptiveCardError(f"{path} must be an object.")
    element_type = element.get("type")
    if element_type not in _ELEMENT_TYPES:
        raise AdaptiveCardError(f"{path} has unsupported type {element_type!r}.")
    if element_type in _CHART_TYPES:
        _validate_chart(element, path)

    for collection_name in ("items", "columns", "rows", "cells"):
        children = element.get(collection_name)
        if children is None:
            continue
        if not isinstance(children, list):
            raise AdaptiveCardError(f"{path}.{collection_name} must be a list.")
        for index, child in enumerate(children):
            if collection_name == "columns" and element_type == "Table":
                if not isinstance(child, dict):
                    raise AdaptiveCardError(
                        f"{path}.{collection_name}[{index}] must be an object."
                    )
                continue
            _walk_element(child, f"{path}.{collection_name}[{index}]")

    actions = element.get("actions")
    if actions is not None:
        if not isinstance(actions, list):
            raise AdaptiveCardError(f"{path}.actions must be a list.")
        for index, action in enumerate(actions):
            if not isinstance(action, dict) or action.get("type") not in _ACTION_TYPES:
                raise AdaptiveCardError(f"{path}.actions[{index}] is unsupported.")

    fallback = element.get("fallback")
    if isinstance(fallback, dict):
        _walk_element(fallback, f"{path}.fallback")


def validate_adaptive_card(adaptive_card: dict[str, Any]) -> None:
    if adaptive_card.get("type") != "AdaptiveCard":
        raise AdaptiveCardError("Adaptive Card type must be 'AdaptiveCard'.")
    if adaptive_card.get("version") != ADAPTIVE_CARD_VERSION:
        raise AdaptiveCardError(
            f"Adaptive Card version must be {ADAPTIVE_CARD_VERSION}."
        )
    body = adaptive_card.get("body")
    if not isinstance(body, list) or not body:
        raise AdaptiveCardError("Adaptive Card body must be a non-empty list.")
    for index, element in enumerate(body):
        _walk_element(element, f"body[{index}]")


__all__ = [
    "ADAPTIVE_CARD_VERSION",
    "AdaptiveCardError",
    "render_finance_agent_output",
    "validate_adaptive_card",
]