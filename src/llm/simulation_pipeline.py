from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from src.llm.chivon_impl import load_chivon
from src.llm.agents.chivon import chivon


@dataclass
class SimulationRunResult:
    success: bool
    results: Any | None = None
    error: str = ""


@dataclass
class SimulationUpdateResult:
    success: bool
    card_output: str = ""
    adaptive_card: dict[str, Any] | None = None
    simulator_results: Any | None = None
    teams_status_code: int | None = None
    teams_response: str = ""
    error: str = ""


def _log(msg: str) -> None:
    print(
        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [simulation-pipeline] {msg}",
        flush=True,
    )


def _output(result: Any) -> Any:
    return result.output if hasattr(result, "output") else result


def _coerce_value(value: Any) -> Any:
    """
    Adaptive Card inputs usually arrive as strings.
    Convert numeric-looking values into int/float.
    Keep non-numeric values as strings.
    """

    if isinstance(value, (int, float, bool)):
        return value

    if value is None:
        return None

    if not isinstance(value, str):
        return value

    cleaned = (
        value.replace(",", "")
        .replace("$", "")
        .replace("USD", "")
        .replace("IDR", "")
        .replace("%", "")
        .strip()
    )

    if cleaned == "":
        return value

    try:
        if "." in cleaned:
            return float(cleaned)

        return int(cleaned)

    except ValueError:
        return value


def _parse_card_output(card_output: str) -> dict[str, Any]:
    """
    RendererOutput.card_output is currently a string.

    Sometimes the model returns:
    1. A normal JSON string
    2. A double-encoded JSON string

    This safely parses until the result is a dict.
    """

    parsed: Any = card_output

    if isinstance(parsed, str):
        parsed = json.loads(parsed)

    if isinstance(parsed, str):
        parsed = json.loads(parsed)

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Parsed adaptive card must be dict, got {type(parsed)}"
        )

    return parsed


def _safe_json_loads(value: Any, fallback: Any) -> Any:
    """
    Action.Submit data fields sometimes arrive as JSON strings.
    This safely parses them where possible.
    """

    if value is None:
        return fallback

    if isinstance(value, (dict, list)):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback

    return fallback


def _metadata_keys() -> set[str]:
    return {
        "action",
        "simulation_id",
        "simulation_title",
        "sim_title",
        "source_agent",
        "calculation_instructions",
        "calcuation_instructions",
        "calcuation_instruction",
        "outputs",
        "expected_outputs",
        "original_inputs",
        "original_outputs",
        "card_instance_id",
    }


def _extract_simulation_inputs(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract user-submitted simulation values from an Adaptive Card submit payload.

    Excludes metadata fields that are not simulation inputs.
    """

    fields: list[dict[str, Any]] = []

    for key, value in payload.items():
        if key in _metadata_keys():
            continue

        fields.append(
            {
                "name": key,
                "value": _coerce_value(value),
            }
        )

    return fields


def _extract_expected_outputs(
    payload: dict[str, Any],
    ) -> list:
    """
    Get requested output names from the submitted payload.

    Supports either:
    - expected_outputs
    - outputs
    """

    raw_outputs = (
        payload.get("expected_outputs")
        or payload.get("outputs")
        or []
    )

    if isinstance(raw_outputs, str):
        # Allows renderer to pass comma-separated outputs if needed.
        return [
            item.strip()
            for item in raw_outputs.split(",")
            if item.strip()
        ]

    if isinstance(raw_outputs, list):
        return [
            str(item)
            for item in raw_outputs
        ]

    return []


def _get_calculation_instructions(payload: dict[str, Any]) -> str:
    """
    Supports both the correct spelling and older misspelled field names.
    """

    return (
        payload.get("calculation_instructions")
        or payload.get("calcuation_instructions")
        or payload.get("calcuation_instruction")
        or ""
    )


def _get_simulation_title(payload: dict[str, Any]) -> str:
    return (
        payload.get("simulation_title")
        or payload.get("sim_title")
        or "Simulation Recalculation"
    )


def _get_source_agent(payload: dict[str, Any]) -> str:
    """
    FinanceAgentOutput.agent must match your allowed literals.

    Use one of:
    Finance, Cashflow, Collections, Leakage
    """

    source_agent = payload.get("source_agent") or "Collections"

    allowed = {
        "Finance",
        "Cashflow",
        "Collections",
        "Leakage",
    }

    if source_agent not in allowed:
        return "Collections"

    return source_agent


def _simulator_results_to_map(simulator_output: Any) -> dict[str, Any]:
    result_map: dict[str, Any] = {}

    for result in simulator_output.results:
        result_map[str(result.name)] = result.value

    return result_map


async def recalculate_simulation(
    payload: dict[str, Any],
) -> SimulationRunResult:
    """
    Runs the simulator_agent for an Adaptive Card simulation submit.

    Expected payload shape from Teams / Power Automate:

    {
        "action": "recalculate_simulation",
        "simulation_title": "Collections Recovery Scenario",
        "calculation_instructions": "Recovered Amount = Outstanding Balance * Collection Rate / 100...",
        "expected_outputs": ["Recovered Amount", "New Credit Balance"],

        "Outstanding Balance": "1000000000",
        "Collection Rate": "20",
        "Current Credit Balance": "250000000"
    }
    """

    try:
        load_chivon()

        SimulatorInput = chivon.type("SimulatorInput")
        SimulationField = chivon.type("SimulationField")
        SimulatorOutput = chivon.type("SimulatorOutput")

        calculation_instructions = _get_calculation_instructions(payload)

        if not calculation_instructions:
            return SimulationRunResult(
                success=False,
                error="Missing calculation_instructions.",
            )

        simulation_title = _get_simulation_title(payload)

        input_fields_raw = _extract_simulation_inputs(payload)
        expected_outputs = _extract_expected_outputs(payload)

        if not input_fields_raw:
            return SimulationRunResult(
                success=False,
                error="No simulation input values were provided.",
            )

        if not expected_outputs:
            return SimulationRunResult(
                success=False,
                error="No expected output names were provided.",
            )

        input_fields = [
            SimulationField(
                name=item["name"],
                value=item["value"],
            )
            for item in input_fields_raw
        ]

        simulator_input = SimulatorInput(
            sim_title=simulation_title,
            inputs=input_fields,
            outputs=expected_outputs,
            calculation_instructions=calculation_instructions,
        )

        _log("running simulator_agent")

        simulator_result = _output(
            await chivon.run_async(
                "simulator_agent",
                simulator_input,
            )
        )

        if not isinstance(simulator_result, SimulatorOutput):
            return SimulationRunResult(
                success=False,
                error=f"simulator_agent returned invalid output: {type(simulator_result)}",
            )

        _log("simulation recalculation successful")

        return SimulationRunResult(
            success=True,
            results=simulator_result,
        )

    except Exception as exc:
        _log(f"simulation failed: {exc}")

        return SimulationRunResult(
            success=False,
            error=f"simulation failed: {exc}",
        )


def _rebuild_simulation_inputs(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Rebuild simulation input definitions.

    Preferred:
    - use original_inputs from Action.Submit metadata
    - update defaults/values with submitted values

    Fallback:
    - create basic number input definitions from submitted payload values
    """

    original_inputs = _safe_json_loads(
        payload.get("original_inputs"),
        fallback=[],
    )

    submitted_values = {
        item["name"]: item["value"]
        for item in _extract_simulation_inputs(payload)
    }

    rebuilt_inputs: list[dict[str, Any]] = []

    if isinstance(original_inputs, list) and original_inputs:
        for input_def in original_inputs:
            if not isinstance(input_def, dict):
                continue

            input_id = (
                input_def.get("id")
                or input_def.get("name")
                or input_def.get("label")
            )

            updated = dict(input_def)

            if input_id in submitted_values:
                updated["default"] = submitted_values[input_id]
                updated["value"] = submitted_values[input_id]

            rebuilt_inputs.append(updated)

        return rebuilt_inputs

    # Fallback if original input definitions are not available.
    for name, value in submitted_values.items():
        numeric_value = _coerce_value(value)

        rebuilt_inputs.append(
            {
                "id": name,
                "label": name,
                "min": 0,
                "max": max(float(numeric_value) * 2, 100)
                if isinstance(numeric_value, (int, float))
                else 100,
                "step": 1,
                "default": numeric_value,
                "value": numeric_value,
                "unit": "",
            }
        )

    return rebuilt_inputs


def _rebuild_simulation_outputs(
    payload: dict[str, Any],
    simulator_output: Any,
) -> list[dict[str, Any]]:
    """
    Rebuild output definitions and inject freshly calculated values.
    """

    result_map = _simulator_results_to_map(simulator_output)

    original_outputs = _safe_json_loads(
        payload.get("original_outputs"),
        fallback=[],
    )

    rebuilt_outputs: list[dict[str, Any]] = []

    if isinstance(original_outputs, list) and original_outputs:
        for output_def in original_outputs:
            if not isinstance(output_def, dict):
                continue

            label = (
                output_def.get("label")
                or output_def.get("name")
                or output_def.get("id")
            )

            updated = dict(output_def)

            if label in result_map:
                updated["value"] = result_map[label]

            rebuilt_outputs.append(updated)

        return rebuilt_outputs

    # Fallback if original output definitions are not available.
    for name, value in result_map.items():
        rebuilt_outputs.append(
            {
                "id": name,
                "label": name,
                "value": value,
                "unit": "",
            }
        )

    return rebuilt_outputs


async def rerender_simulation(
    payload: dict[str, Any],
    simulator_output: Any,
) -> SimulationUpdateResult:
    """
    Rebuilds the simulation component after recalculation and sends it through
    renderer_agent.

    This keeps simulation result cards visually consistent with the rest of
    your FinanceAgentOutput -> renderer_agent architecture.
    """

    try:
        #load_chivon()

        Component = chivon.type("Component")
        FinanceAgentOutput = chivon.type("FinanceAgentOutput")
        RendererOutput = chivon.type("RendererOutput")

        simulation_title = _get_simulation_title(payload)
        calculation_instructions = _get_calculation_instructions(payload)
        source_agent = _get_source_agent(payload)

        updated_inputs = _rebuild_simulation_inputs(payload)
        updated_outputs = _rebuild_simulation_outputs(
            payload=payload,
            simulator_output=simulator_output,
        )

        simulation_content = {
            "title": simulation_title,
            "simulation_id": payload.get("simulation_id", "runtime_simulation"),
            "calculation_instructions": calculation_instructions,
            "inputs": updated_inputs,
            "outputs": updated_outputs,
        }

        component = Component(
            format="simulation",
            content=json.dumps(
                simulation_content,
                ensure_ascii=False,
            ),
        )

        agent_output = FinanceAgentOutput(
            agent=source_agent,
            components=[
                component
            ],
        )

        _log("running renderer_agent for updated simulation")

        renderer_result = _output(
            await chivon.run_async(
                "renderer_agent",
                agent_output,
            )
        )

        if not isinstance(renderer_result, RendererOutput):
            return SimulationUpdateResult(
                success=False,
                simulator_results=simulator_output,
                error=f"renderer_agent returned invalid output: {type(renderer_result)}",
            )

        adaptive_card = _parse_card_output(
            renderer_result.card_output
        )

        assert adaptive_card["type"] == "AdaptiveCard"
        assert "body" in adaptive_card
        assert isinstance(adaptive_card["body"], list)

        _log("simulation rerender successful")

        return SimulationUpdateResult(
            success=True,
            card_output=renderer_result.card_output,
            adaptive_card=adaptive_card,
            simulator_results=simulator_output,
        )

    except Exception as exc:
        _log(f"rerender failed: {exc}")

        return SimulationUpdateResult(
            success=False,
            simulator_results=simulator_output,
            error=f"rerender failed: {exc}",
        )


def _send_adaptive_card_to_teams(
    adaptive_card: dict[str, Any],
    wrap_in_adaptive_card_key: bool = False,
) -> tuple[int, str]:
    """
    Sends the Adaptive Card to Power Automate.

    If your Power Automate card field uses:
        string(triggerBody())
    use wrap_in_adaptive_card_key=False.

    If your Power Automate card field uses:
        string(variables('Body')?['adaptiveCard'])
    use wrap_in_adaptive_card_key=True.
    """

    webhook_url = os.getenv("TEAMS_POWER_AUTOMATE_WEBHOOK_URL")

    if not webhook_url:
        raise RuntimeError(
            "Missing TEAMS_POWER_AUTOMATE_WEBHOOK_URL environment variable."
        )

    if wrap_in_adaptive_card_key:
        payload = {
            "adaptiveCard": adaptive_card
        }
    else:
        payload = adaptive_card

    response = requests.post(
        webhook_url,
        json=payload,
        headers={
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    return response.status_code, response.text


async def update_simulation_pipeline(
    payload: dict[str, Any],
    send_to_teams: bool = True,
    wrap_in_adaptive_card_key: bool = False,
) -> SimulationUpdateResult:
    """
    One full simulation update pipeline.

    Runs:

        Teams submitted payload
            ↓
        simulator_agent recalculates
            ↓
        rebuild updated simulation component
            ↓
        renderer_agent rerenders full card
            ↓
        optionally send to Teams
    """

    simulation_result = await recalculate_simulation(payload)

    if not simulation_result.success:
        return SimulationUpdateResult(
            success=False,
            error=simulation_result.error,
        )

    rerendered = await rerender_simulation(
        payload=payload,
        simulator_output=simulation_result.results,
    )

    if not rerendered.success:
        return rerendered

    if not send_to_teams:
        return rerendered

    try:
        if rerendered.adaptive_card is None:
            return SimulationUpdateResult(
                success=False,
                simulator_results=simulation_result.results,
                error="No adaptive card was produced by rerender_simulation.",
            )

        status_code, response_text = _send_adaptive_card_to_teams(
            adaptive_card=rerendered.adaptive_card,
            wrap_in_adaptive_card_key=wrap_in_adaptive_card_key,
        )

        _log(f"Teams send status={status_code}")

        if status_code not in (200, 201, 202):
            return SimulationUpdateResult(
                success=False,
                card_output=rerendered.card_output,
                adaptive_card=rerendered.adaptive_card,
                simulator_results=simulation_result.results,
                teams_status_code=status_code,
                teams_response=response_text,
                error=f"Teams send failed with status {status_code}",
            )

        return SimulationUpdateResult(
            success=True,
            card_output=rerendered.card_output,
            adaptive_card=rerendered.adaptive_card,
            simulator_results=simulation_result.results,
            teams_status_code=status_code,
            teams_response=response_text,
        )

    except Exception as exc:
        _log(f"Teams send failed: {exc}")

        return SimulationUpdateResult(
            success=False,
            card_output=rerendered.card_output,
            adaptive_card=rerendered.adaptive_card,
            simulator_results=simulation_result.results,
            error=f"Teams send failed: {exc}",
        )