"""Leakage dashboard payload + illustrative scenario simulation."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_blocks import (
    _bar_chart,
    _call_with_timeout,
    _donut_chart,
    _fmt,
    _line_chart,
    _pct,
    _row_get,
    _table_view,
    _waterfall_chart,
)
from src.llm.agents.finance.leakage.tools.leakage_data import (
    get_payment_leakage_snapshot,
)


def simulate_leakage_scenario(
    hold: float,
    dup_rec: float,
    ov_rec: float,
    *,
    duplicates_amount: float = 3050,
    overbill_amount: float = 400,
    other_blocked: float = 500,
    at_risk: float = 7845,
) -> dict[str, Any]:
    blocked = hold + other_blocked
    recovered = (
        duplicates_amount * dup_rec / 100
        + overbill_amount * ov_rec / 100
    )
    total = blocked + recovered
    return {
        "success": True,
        "illustrative": True,
        "blocked": round(blocked, 2),
        "recovered": round(recovered, 2),
        "total_protected": round(total, 2),
        "at_risk": at_risk,
        "pct_of_at_risk": round(total / at_risk * 100, 1) if at_risk else 0,
        "gauge": {
            "ratio": total / at_risk if at_risk else 0,
            "center": _fmt(total),
            "txt": f"{round(total / at_risk * 100) if at_risk else 0}% of at risk",
        },
    }


def _leakage_dashboard(snap: dict[str, Any]) -> dict[str, Any]:
    summary_rows = snap.get("summary") or []
    categories = snap.get("category_breakdowns") or []
    anomalies = snap.get("anomalies") or []
    worklist = snap.get("action_worklist") or []
    summary = summary_rows[0] if summary_rows else {}

    def cat_amount(row: dict[str, Any]) -> float:
        val = _row_get(row, "amount_idr_mn", "amount", "value", "exposure_idr_mn")
        try:
            return float(val or 0)
        except (TypeError, ValueError):
            return 0.0

    def cat_name(row: dict[str, Any]) -> str:
        return str(
            _row_get(row, "category_name", "category", "name", "label") or "Other"
        )

    cat_rows = [
        {"label": cat_name(c), "value": cat_amount(c)}
        for c in categories
    ]
    at_risk = float(
        _row_get(
            summary,
            "total_at_risk_idr_mn",
            "flagged_idr_mn",
            "total_idr_mn",
            "amount_idr_mn",
        )
        or sum(r["value"] for r in cat_rows)
        or 7845
    )
    fraud = 0.0
    duplicates = 0.0
    for row in cat_rows:
        low = row["label"].lower()
        if "fraud" in low or "bank" in low:
            fraud += row["value"]
        if "dup" in low:
            duplicates += row["value"]
    if not fraud:
        fraud = 3800.0
    if not duplicates:
        duplicates = 3050.0

    base_sim = simulate_leakage_scenario(
        hold=fraud,
        dup_rec=95,
        ov_rec=90,
        duplicates_amount=duplicates,
        at_risk=at_risk,
    )

    kpis = [
        {
            "id": "flagged",
            "view": "worklist",
            "label": "Flagged this cycle",
            "value": _fmt(at_risk),
            "unit": "mn",
            "delta": f"{len(anomalies) or len(worklist)} flags",
            "alert": True,
        },
        {
            "id": "fraud",
            "view": "categories",
            "label": "Fraud held",
            "value": _fmt(fraud),
            "unit": "mn",
            "delta": "bank change",
            "alert": fraud > 0,
        },
        {
            "id": "dup",
            "view": "vendors",
            "label": "Duplicates",
            "value": _fmt(duplicates),
            "unit": "mn",
            "delta": "recoverable",
            "alert": False,
        },
        {
            "id": "blocked",
            "view": "blockvs",
            "label": "Blocked",
            "value": _fmt(base_sim["blocked"]),
            "unit": "mn",
            "delta": "before payment",
            "alert": False,
        },
        {
            "id": "protected",
            "view": "recovery",
            "label": "Total protected",
            "value": _fmt(base_sim["total_protected"]),
            "unit": "mn",
            "delta": "this cycle",
            "alert": False,
        },
    ]

    if not cat_rows:
        cat_rows = [
            {"label": "Bank-change fraud", "value": fraud},
            {"label": "Duplicate pay", "value": duplicates},
            {"label": "Overbilling", "value": 900},
            {"label": "Lost discount", "value": 95},
        ]

    wl_headers = ["#", "Item", "Type", "Amount"]
    wl_rows: list[list[Any]] = []
    for idx, row in enumerate(worklist[:10], start=1):
        wl_rows.append(
            [
                idx,
                str(
                    _row_get(row, "vendor_name", "counterparty", "title", "name")
                    or ""
                ),
                str(_row_get(row, "anomaly_type", "type", "category") or ""),
                _fmt(
                    float(
                        _row_get(row, "amount_idr_mn", "amount", "value") or 0
                    )
                ),
            ]
        )
    if not wl_rows:
        for idx, row in enumerate(anomalies[:10], start=1):
            wl_rows.append(
                [
                    idx,
                    str(_row_get(row, "vendor_name", "name") or ""),
                    str(_row_get(row, "anomaly_type", "type") or ""),
                    _fmt(
                        float(
                            _row_get(row, "amount_idr_mn", "amount", "value")
                            or 0
                        )
                    ),
                ]
            )

    views = {
        "categories": {
            **_bar_chart(
                "Leakage & fraud by category",
                cat_rows,
                tag="breakdown",
            ),
        },
        "blockvs": {
            **_bar_chart(
                "Blocked vs recoverable",
                [
                    {"label": "Blocked", "value": base_sim["blocked"]},
                    {"label": "Recoverable", "value": duplicates + 400},
                ],
                tag="money",
            ),
        },
        "recovery": {
            **_bar_chart(
                "Protected vs at risk",
                [
                    {"label": "At risk", "value": at_risk},
                    {
                        "label": "Protected",
                        "value": base_sim["total_protected"],
                    },
                ],
                tag="recovery",
            ),
        },
        "worklist": _table_view(
            "Action worklist",
            wl_headers,
            wl_rows,
            tag="worklist",
        ),
        "vendors": _table_view(
            "Vendor / anomaly radar",
            wl_headers,
            wl_rows,
            tag="risk",
        ),
    }

    side = {
        "top": _donut_chart("Leakage mix", cat_rows, tag="risk"),
        "bottom": {
            **_bar_chart(
                "Protected vs at risk",
                [
                    {"label": "At risk", "value": at_risk},
                    {
                        "label": "Protected",
                        "value": base_sim["total_protected"],
                    },
                ],
                tag="recovery",
            ),
        },
    }

    return {
        "agent": "leakage",
        "import_batch_id": snap.get("import_batch_id"),
        "default_view": "categories",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            "action": "simulate_leakage",
            "gauge_label": f"Total protected vs {_fmt(at_risk)}",
            "inputs": [
                {
                    "id": "hold",
                    "label": "Hold amount mn",
                    "min": 0,
                    "max": max(fraud, 1),
                    "step": 50,
                    "default": fraud,
                    "unit": "IDR mn",
                },
                {
                    "id": "dupRec",
                    "label": "Dup recovery %",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "default": 95,
                    "unit": "%",
                },
                {
                    "id": "ovRec",
                    "label": "Overbill rec %",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "default": 90,
                    "unit": "%",
                },
            ],
            "baseline": {
                "duplicates_amount": duplicates,
                "overbill_amount": 400,
                "other_blocked": 500,
                "at_risk": at_risk,
                "fraud": fraud,
            },
            "illustrative": True,
        },
    }


def build() -> dict[str, Any]:
    return _leakage_dashboard(_call_with_timeout(get_payment_leakage_snapshot))
