from __future__ import annotations

import json
from typing import Any

from src.llm.adaptive_cards import render_finance_agent_output


def _component(component_format: str, content: dict[str, Any]) -> dict[str, str]:
    return {
        "format": component_format,
        "content": json.dumps(content, ensure_ascii=False),
    }


def _simulation_content(
    customer_name: str,
    maximum_collection: float,
    collection_amount: float = 5000,
    discount_pct: float = 1,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outputs: list[dict[str, Any]] = [
        {"label": "Cash collected", "unit": "IDR mn"},
        {"label": "Discount cost", "unit": "IDR mn"},
        {"label": "Customer overdue", "unit": "IDR mn"},
        {"label": "Portfolio DSO", "unit": "days"},
    ]
    if result is not None:
        values = (
            result["cash_collected_idr_mn"],
            result["discount_cost_idr_mn"],
            result["customer_overdue_after_idr_mn"],
            result["dso_after_days"],
        )
        for output, value in zip(outputs, values, strict=True):
            output["value"] = value

    return {
        "title": f"Collection offer - {customer_name}",
        "simulation_id": "collection_offer",
        "action": "calculate_collection_scenario",
        "submit_data": {"customer_name": customer_name},
        "calculation_instructions": (
            "Cash collected reduces the customer's overdue balance and total "
            "AR by the same gross amount. Discount cost equals cash collected "
            "times the discount percentage. Portfolio DSO is recalculated "
            "from remaining total AR and daily credit sales."
        ),
        "inputs": [
            {
                "id": "cash_to_collect_idr_mn",
                "label": "Cash to collect",
                "min": 1,
                "max": maximum_collection,
                "default": min(collection_amount, maximum_collection),
                "unit": "IDR mn",
            },
            {
                "id": "discount_pct",
                "label": "Early-pay discount",
                "min": 0,
                "max": 100,
                "default": discount_pct,
                "unit": "%",
            },
        ],
        "outputs": outputs,
    }


def build_collections_snapshot_card(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    summary = snapshot.get("summary") or {}
    customers = snapshot.get("customers") or []
    worklist = snapshot.get("worklist") or []
    customer_a = next(
        (
            customer
            for customer in customers
            if "customer a" in str(customer.get("customer_name", "")).lower()
        ),
        customers[0] if customers else {},
    )
    customer_name = str(customer_a.get("customer_name") or "Customer A")
    maximum_collection = float(customer_a.get("overdue_idr_mn") or 0)
    top_accounts = customers[:5]
    expected_recovery = sum(
        float(item.get("expected_recovery_idr_mn") or 0)
        for item in worklist
    )

    agent_output = {
        "agent": "Collections",
        "components": [
            _component(
                "text",
                {
                    "title": "Collections and DSO position",
                    "content": (
                        f"Total AR is IDR {float(summary.get('total_ar_idr_mn') or 0):,.0f} mn; "
                        f"IDR {float(summary.get('overdue_ar_idr_mn') or 0):,.0f} mn is overdue. "
                        f"Current DSO is {float(summary.get('current_dso_days') or 0):,.1f} days "
                        f"against a {float(summary.get('target_dso_days') or 0):,.1f}-day target. "
                        f"The current worklist has IDR {expected_recovery:,.0f} mn of modeled recovery."
                    ),
                },
            ),
            _component(
                "chart",
                {
                    "title": "Largest overdue customer balances",
                    "chart_type": "bar",
                    "x_axis_title": "Customer",
                    "y_axis_title": "IDR mn",
                    "data": [
                        {
                            "label": customer.get("customer_name"),
                            "value": customer.get("overdue_idr_mn"),
                        }
                        for customer in top_accounts
                    ],
                },
            ),
            _component(
                "simulation",
                _simulation_content(
                    customer_name,
                    maximum_collection,
                    min(5000, maximum_collection),
                    1,
                ),
            ),
        ],
    }
    return render_finance_agent_output(agent_output)


def build_collection_scenario_card(
    result: dict[str, Any],
) -> dict[str, Any]:
    customer_name = str(result["customer_name"])
    rows = [
        [
            "Cash pulled forward",
            0,
            result["cash_collected_idr_mn"],
            result["cash_collected_idr_mn"],
            "IDR mn",
        ],
        [
            "Discount cost",
            0,
            result["discount_cost_idr_mn"],
            -result["discount_cost_idr_mn"],
            "IDR mn",
        ],
        [
            "Customer overdue",
            result["customer_overdue_before_idr_mn"],
            result["customer_overdue_after_idr_mn"],
            -result["cash_collected_idr_mn"],
            "IDR mn",
        ],
        [
            "Total AR",
            result["total_ar_before_idr_mn"],
            result["total_ar_after_idr_mn"],
            -result["cash_collected_idr_mn"],
            "IDR mn",
        ],
        [
            "DSO",
            result["dso_before_days"],
            result["dso_after_days"],
            result["dso_change_days"],
            "days",
        ],
    ]
    agent_output = {
        "agent": "Collections",
        "components": [
            _component(
                "chart",
                {
                    "title": "Collection scenario - before and after",
                    "chart_type": "bar",
                    "x_axis_title": "Balance",
                    "y_axis_title": "IDR mn",
                    "data": [
                        {
                            "label": "Customer overdue before",
                            "value": result["customer_overdue_before_idr_mn"],
                            "color": "attention",
                        },
                        {
                            "label": "Customer overdue after",
                            "value": result["customer_overdue_after_idr_mn"],
                            "color": "good",
                        },
                        {
                            "label": "Cash collected",
                            "value": result["cash_collected_idr_mn"],
                            "color": "categoricalBlue",
                        },
                        {
                            "label": "Discount cost",
                            "value": result["discount_cost_idr_mn"],
                            "color": "warning",
                        },
                    ],
                },
            ),
            _component(
                "table",
                {
                    "title": "On-demand calculation - your parameters",
                    "columns": ["Item", "Before", "After", "Change", "Unit"],
                    "rows": rows,
                },
            ),
            _component(
                "simulation",
                _simulation_content(
                    customer_name,
                    result["customer_overdue_before_idr_mn"],
                    result["cash_collected_idr_mn"],
                    result["discount_pct"],
                    result,
                ),
            ),
            _component(
                "decision",
                {
                    "title": "CFO Decision Required",
                },
            ),
        ],
    }
    return render_finance_agent_output(agent_output)


__all__ = [
    "build_collection_scenario_card",
    "build_collections_snapshot_card",
]