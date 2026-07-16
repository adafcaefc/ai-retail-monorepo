from __future__ import annotations

import json
from typing import Any

from src.cashflow.models import (
    CashFlowBaselineResponse,
    CashFlowSimulationRequest,
    CashFlowSimulationResponse,
)
from src.llm.adaptive_cards import render_finance_agent_output


def _component(component_format: str, content: dict[str, Any]) -> dict[str, str]:
    return {
        "format": component_format,
        "content": json.dumps(content, ensure_ascii=False),
    }


def _simulation_content(
    baseline: CashFlowBaselineResponse,
    request: CashFlowSimulationRequest | None = None,
    result: CashFlowSimulationResponse | None = None,
) -> dict[str, Any]:
    request = request or CashFlowSimulationRequest()
    outputs: list[dict[str, Any]] = [
        {
            "label": "Week 5 cash",
            "unit": "IDR mn",
        },
        {
            "label": "Week 6 cash",
            "unit": "IDR mn",
        },
        {
            "label": "Week 7 cash",
            "unit": "IDR mn",
        },
        {
            "label": "Lowest headroom",
            "unit": "IDR mn",
        },
    ]
    if result is not None:
        values = (
            result.week5_cash_idr_mn,
            result.week6_cash_idr_mn,
            result.week7_cash_idr_mn,
            result.lowest_headroom_idr_mn,
        )
        for output, value in zip(outputs, values, strict=True):
            output["value"] = value

    return {
        "title": "Test your cash levers",
        "simulation_id": "cashflow_liquidity",
        "action": "simulate_cashflow",
        "calculation_instructions": (
            "Accelerated collection moves cash from Week 7 to Week 5; "
            "payment deferral moves cash from Week 5 to Week 6; a credit-line "
            "draw adds Week 5 liquidity; the hedge changes FX exposure but "
            "uses no Week 5 cash."
        ),
        "inputs": [
            {
                "id": "accelerate_collection_idr_mn",
                "label": "Accelerate Customer A collection",
                "min": 0,
                "max": baseline.customer_delay_driver.amount_idr_mn,
                "default": request.accelerate_collection_idr_mn,
                "unit": "IDR mn",
            },
            {
                "id": "defer_payment_idr_mn",
                "label": "Defer eligible vendor payment",
                "min": 0,
                "max": baseline.deferrable_payment_driver.amount_idr_mn,
                "default": request.defer_payment_idr_mn,
                "unit": "IDR mn",
            },
            {
                "id": "credit_line_draw_idr_mn",
                "label": "Credit-line draw",
                "min": 0,
                "max": 5000,
                "default": request.credit_line_draw_idr_mn,
                "unit": "IDR mn",
            },
            {
                "id": "hedge_usd",
                "label": "USD forward hedge",
                "min": 0,
                "max": baseline.net_usd_exposure,
                "default": request.hedge_usd,
                "unit": "USD",
            },
        ],
        "outputs": outputs,
    }


def build_cashflow_baseline_card(
    baseline: CashFlowBaselineResponse,
) -> dict[str, Any]:
    lowest_position = min(
        baseline.weekly_positions,
        key=lambda position: position.headroom_idr_mn,
    )
    below_buffer = [
        position
        for position in baseline.weekly_positions
        if position.headroom_idr_mn < 0
    ]
    shortfall = max(0.0, -lowest_position.headroom_idr_mn)
    summary = (
        f"Week {lowest_position.week_number} is the lowest point at "
        f"IDR {lowest_position.closing_cash_idr_mn:,.0f} mn, "
        f"IDR {shortfall:,.0f} mn below the "
        f"IDR {baseline.minimum_buffer_idr_mn:,.0f} mn buffer. "
        f"{len(below_buffer)} forecast week(s) are below buffer. "
        f"The primary movable inflow is "
        f"{baseline.customer_delay_driver.counterparty_name} "
        f"(IDR {baseline.customer_delay_driver.amount_idr_mn:,.0f} mn)."
    )

    chart_data = [
        {
            "legend": "Closing cash",
            "values": [
                {
                    "label": f"W{position.week_number}",
                    "value": position.closing_cash_idr_mn,
                }
                for position in baseline.weekly_positions
            ],
        },
        {
            "legend": "Minimum buffer",
            "values": [
                {
                    "label": f"W{position.week_number}",
                    "value": baseline.minimum_buffer_idr_mn,
                }
                for position in baseline.weekly_positions
            ],
        },
    ]

    agent_output = {
        "agent": "Cashflow",
        "components": [
            _component(
                "text",
                {
                    "title": "Cash forecast and primary drivers",
                    "content": summary,
                },
            ),
            _component(
                "chart",
                {
                    "title": "Cash forecast - closing cash vs buffer",
                    "chart_type": "line",
                    "x_axis_title": "Forecast week",
                    "y_axis_title": "IDR mn",
                    "data": chart_data,
                },
            ),
            _component(
                "simulation",
                _simulation_content(baseline),
            ),
        ],
    }
    return render_finance_agent_output(agent_output)


def build_cashflow_simulation_card(
    baseline: CashFlowBaselineResponse,
    request: CashFlowSimulationRequest,
    result: CashFlowSimulationResponse,
) -> dict[str, Any]:
    baseline_by_week = {
        position.week_number: position
        for position in baseline.weekly_positions
    }
    scenario_values = {
        5: result.week5_cash_idr_mn,
        6: result.week6_cash_idr_mn,
        7: result.week7_cash_idr_mn,
    }
    chart_data = [
        {
            "legend": "Baseline",
            "values": [
                {
                    "label": f"W{week}",
                    "value": baseline_by_week[week].closing_cash_idr_mn,
                }
                for week in (5, 6, 7)
            ],
        },
        {
            "legend": "Your scenario",
            "values": [
                {
                    "label": f"W{week}",
                    "value": scenario_values[week],
                }
                for week in (5, 6, 7)
            ],
        },
        {
            "legend": "Minimum buffer",
            "values": [
                {
                    "label": f"W{week}",
                    "value": result.minimum_buffer_idr_mn,
                }
                for week in (5, 6, 7)
            ],
        },
    ]
    details = [
        ["Accelerated collection", request.accelerate_collection_idr_mn, "IDR mn"],
        ["Payment deferral", request.defer_payment_idr_mn, "IDR mn"],
        ["Credit-line draw", request.credit_line_draw_idr_mn, "IDR mn"],
        ["Forward hedge", request.hedge_usd, "USD"],
        ["Lowest headroom", result.lowest_headroom_idr_mn, "IDR mn"],
        ["Weeks below buffer", result.weeks_below_buffer, "weeks"],
        ["FX downside avoided", result.fx_downside_avoided_idr_mn, "IDR mn"],
        ["Forward premium", result.forward_premium_idr_mn, "IDR mn"],
        ["Status", result.status, ""],
    ]
    if result.warnings:
        details.append(["Verification", "; ".join(result.warnings), ""])

    agent_output = {
        "agent": "Cashflow",
        "components": [
            _component(
                "chart",
                {
                    "title": "Cash scenario - Weeks 5 to 7",
                    "chart_type": "line",
                    "x_axis_title": "Forecast week",
                    "y_axis_title": "IDR mn",
                    "data": chart_data,
                },
            ),
            _component(
                "table",
                {
                    "title": result.recommendation,
                    "columns": ["Metric", "Value", "Unit"],
                    "rows": details,
                },
            ),
            _component(
                "simulation",
                _simulation_content(baseline, request, result),
            ),
        ],
    }
    return render_finance_agent_output(agent_output)


__all__ = [
    "build_cashflow_baseline_card",
    "build_cashflow_simulation_card",
]