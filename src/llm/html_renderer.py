from __future__ import annotations

import html
import json
from typing import Any, Literal

from pydantic import BaseModel


class UiBlock(BaseModel):
    type: Literal[
        "html",
        "chart",
        "simulation",
        "next_route",
    ]

    data: dict[str, Any]


def render_ui_blocks(
    components,
) -> list[UiBlock]:
    """
    Accepts:
        agent_result.components

    Each component must expose:
        component.format
        component.content
    """

    blocks : list[UiBlock] = []

    for component in components:

        try:
            content = json.loads(
                component.content
            )
        except Exception:
            content = {}

        match component.format:

            case "text":
                blocks.append(
                    UiBlock(
                        type="html",
                        data={
                            "html": render_text(
                                content
                            )
                        },
                    )
                )

            case "table":
                blocks.append(
                    UiBlock(
                        type="html",
                        data={
                            "html": render_table(
                                content
                            )
                        },
                    )
                )

            case "recommendation":
                blocks.append(
                    UiBlock(
                        type="html",
                        data={
                            "html": render_recommendation(
                                content
                            )
                        },
                    )
                )

            case "chart":
                blocks.append(
                    UiBlock(
                        type="chart",
                        data=content,
                    )
                )

            case "simulation":
                blocks.append(
                    UiBlock(
                        type="simulation",
                        data=content,
                    )
                )

            case "next_route":
                blocks.append(
                    UiBlock(
                        type="next_route",
                        data=content,
                    )
                )

            case _:
                blocks.append(
                    UiBlock(
                        type="html",
                        data={
                            "html": render_unknown(
                                component.content
                            )
                        },
                    )
                )

    return blocks


def render_text(
    content: dict,
) -> str:

    return f"""
    <section class="text-block">
        <h2>{html.escape(content.get("title", ""))}</h2>
        <p>{html.escape(content.get("content", ""))}</p>
    </section>
    """

def render_table(
    content: dict,
) -> str:

    headers = "".join(
        f"<th>{html.escape(str(col))}</th>"
        for col in content.get(
            "columns",
            [],
        )
    )

    rows = []

    for row in content.get(
        "rows",
        [],
    ):

        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(v))}</td>"
                for v in row
            )
            + "</tr>"
        )

    return f"""
    <section class="table-block">

        <h2>
            {html.escape(content.get("title", ""))}
        </h2>

        <table>

            <thead>
                <tr>{headers}</tr>
            </thead>

            <tbody>
                {''.join(rows)}
            </tbody>

        </table>

    </section>
    """

def render_recommendation(
    content: dict,
) -> str:

    recommendations = []

    for rec in content.get(
        "recommendations",
        [],
    ):

        assumptions = "".join(
            f"<li>{html.escape(x)}</li>"
            for x in rec.get(
                "assumptions",
                [],
            )
        )

        risks = "".join(
            f"<li>{html.escape(x)}</li>"
            for x in rec.get(
                "risks",
                [],
            )
        )

        recommendations.append(
            f"""
            <div class="recommendation">

                <h3>
                    {html.escape(rec.get("action", ""))}
                </h3>

                <p>
                    <strong>
                        Expected Impact:
                    </strong>

                    {html.escape(rec.get("expected_impact", ""))}
                </p>

                <h4>Assumptions</h4>

                <ul>
                    {assumptions}
                </ul>

                <h4>Risks</h4>

                <ul>
                    {risks}
                </ul>

            </div>
            """
        )

    return f"""
    <section class="recommendation-block">

        <h2>
            {html.escape(content.get("title", ""))}
        </h2>

        {''.join(recommendations)}

    </section>
    """

def render_unknown(
    raw_content: str,
) -> str:

    return f"""
    <section class="unknown-component">

        <h3>
            Unknown Component
        </h3>

        <pre>
            {html.escape(raw_content)}
        </pre>

    </section>
    """