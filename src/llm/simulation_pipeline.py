from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.llm.chivon_impl import load_chivon
from src.llm.agents.chivon import chivon


@dataclass
class SimulationRunResult:
    success: bool
    results: Any | None = None
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

    cleaned = value.replace(",", "").strip()

    if cleaned == "":
        return value

    try:
        if "." in cleaned:
            return float(cleaned)

        return int(cleaned)

    except ValueError:
        return value


def _extract_simulation_inputs(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract user-submitted simulation values from an Adaptive Card submit payload.

    Excludes metadata fields that are not simulation inputs.
    """

    metadata_keys = {
        "action",
        "simulation_id",
        "simulation_title",
        "calculation_instructions",
        "outputs",
        "expected_outputs",
        "source_agent",
        "card_instance_id",
    }

    fields: list[dict[str, Any]] = []

    for key, value in payload.items():
        if key in metadata_keys:
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

        calculation_instructions = payload.get("calculation_instructions")

        if not calculation_instructions:
            return SimulationRunResult(
                success=False,
                error="Missing calculation_instructions.",
            )

        simulation_title = payload.get(
            "simulation_title",
            "Simulation Recalculation",
        )

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