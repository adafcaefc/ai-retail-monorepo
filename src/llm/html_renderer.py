import json
import html


def render_component(component):
    format_type = component.format
    content = json.loads(component.content)

    if format_type == "text":
        return render_text(content)

    if format_type == "table":
        return render_table(content)

    if format_type == "chart":
        return render_chart(content)

    if format_type == "recommendation":
        return render_recommendation(content)

    if format_type == "simulation":
        return render_simulation(content)

    if format_type == "next_route":
        return render_next_route(content)

    return f"""
    <section class="unknown">
        <h3>Unknown Component</h3>
        <pre>{html.escape(component.content)}</pre>
    </section>
    """

def render_text(content):
    return f"""
    <section class="text-block">
        <h2>{html.escape(content['title'])}</h2>
        <p>{html.escape(content['content'])}</p>
    </section>
    """

def render_table(content):
    headers = "".join(
        f"<th>{html.escape(str(c))}</th>"
        for c in content["columns"]
    )

    rows = []

    for row in content["rows"]:
        rows.append(
            "<tr>" +
            "".join(
                f"<td>{html.escape(str(v))}</td>"
                for v in row
            ) +
            "</tr>"
        )

    return f"""
    <section class="table-block">
      <h2>{html.escape(content['title'])}</h2>
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

def render_chart(content):

    data = html.escape(
        json.dumps(content["data"])
    )

    return f"""
    <section class="chart-block">
      <h2>{html.escape(content['title'])}</h2>

      <div
          class="chart-placeholder"
          data-chart-type="{content['chart_type']}"
          data-chart='{data}'
      ></div>
    </section>
    """

def render_recommendation(content):

    sections = []

    for rec in content["recommendations"]:

        sections.append(f"""
        <div class="recommendation">
            <h3>{html.escape(rec["action"])}</h3>

            <p>
                <strong>Impact:</strong>
                {html.escape(rec["expected_impact"])}
            </p>

            <ul>
                {
                    "".join(
                        f"<li>{html.escape(x)}</li>"
                        for x in rec["assumptions"]
                    )
                }
            </ul>
        </div>
        """)

    return f"""
    <section>
      <h2>{html.escape(content["title"])}</h2>
      {''.join(sections)}
    </section>
    """


def render_simulation(content: dict) -> str:

    inputs_html = []

    for inp in content["inputs"]:

        inputs_html.append(
            f"""
            <div class="simulation-input">
                <label>
                    <strong>{html.escape(inp["label"])}</strong>
                </label>

                <input
                    type="range"
                    min="{inp['min']}"
                    max="{inp['max']}"
                    step="{inp['step']}"
                    value="{inp['default']}"
                    data-input-id="{inp['id']}"
                />

                <span>
                    Default: {inp["default"]} {html.escape(inp["unit"])}
                </span>
            </div>
            """
        )

    outputs_html = []

    for output in content["outputs"]:

        outputs_html.append(
            f"""
            <div
                class="simulation-output"
                data-output-label="{html.escape(output['label'])}"
            >
                <strong>{html.escape(output['label'])}</strong>
                <span>Pending calculation</span>
                <small>{html.escape(output['unit'])}</small>
            </div>
            """
        )

    return f"""
    <section
        class="simulation-card"
        data-simulation-id="{content['simulation_id']}"
        data-action="{content['action']}"
    >

        <h2>{html.escape(content['title'])}</h2>

        <div class="simulation-inputs">
            {''.join(inputs_html)}
        </div>

        <div class="simulation-outputs">
            {''.join(outputs_html)}
        </div>

        <button
            class="simulation-run"
            data-action="{content['action']}"
        >
            Recalculate
        </button>

    </section>
    """

def render_next_route(content: dict) -> str:

    cards = []

    for route in content["routes"]:

        cards.append(
            f"""
            <div
                class="route-card"
                data-destination="{html.escape(route['destination'])}"
            >

                <h3>
                    {html.escape(route['destination'])}
                </h3>

                <p>
                    {html.escape(route['reason'])}
                </p>

                <button
                    class="open-agent"
                    data-agent="{route['destination'].lower()}"
                >
                    Open Agent
                </button>

            </div>
            """
        )

    return f"""
    <section class="next-route-card">

        <h2>
            {html.escape(content['title'])}
        </h2>

        <div class="route-list">
            {''.join(cards)}
        </div>

    </section>
    """