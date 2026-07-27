"""Leakage dashboard payload + illustrative scenario simulation."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_blocks import (
    _bar_chart,
    _call_with_timeout,
    _donut_chart,
    _enriched,
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


def _leakage_vendor_rollup(rows: list[dict[str, Any]]) -> list[list[Any]]:
    """Cluster flagged items by vendor.

    The worklist answers "what do I work next"; this answers "who keeps
    doing this to us". Repeat offenders and duplicated vendor masters only
    show up once the per-item flags are grouped.
    """

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(
            _row_get(row, "vendor_name", "counterparty", "title", "name") or ""
        ).strip()
        if not name:
            continue

        try:
            amount = float(
                _row_get(row, "amount_idr_mn", "amount", "value") or 0
            )
        except (TypeError, ValueError):
            amount = 0.0

        kind = str(
            _row_get(row, "anomaly_type", "type", "category") or ""
        ).strip()

        try:
            score = float(_row_get(row, "risk_score", "score") or 0)
        except (TypeError, ValueError):
            score = 0.0

        bucket = grouped.setdefault(
            name,
            {"amount": 0.0, "flags": 0, "kinds": set(), "score": 0.0},
        )
        bucket["amount"] += amount
        bucket["flags"] += 1
        bucket["score"] = max(bucket["score"], score)
        if kind:
            bucket["kinds"].add(kind)

    ordered = sorted(
        grouped.items(), key=lambda kv: kv[1]["amount"], reverse=True
    )

    out: list[list[Any]] = []
    for name, agg in ordered[:10]:
        kinds = ", ".join(sorted(agg["kinds"])) or "—"
        # No stored score: fall back to an exposure-weighted proxy so the
        # column still ranks. Flagged as illustrative in the view note.
        score = agg["score"] or min(99.0, agg["flags"] * 20 + agg["amount"] / 100)
        out.append(
            [
                name,
                agg["flags"],
                kinds,
                _fmt(agg["amount"]),
                str(round(score)),
            ]
        )
    return out


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

    vendor_rows = _leakage_vendor_rollup(worklist or anomalies)

    # Everything at risk that is neither held nor clawable — currently the
    # lost early-payment discounts.
    lost = max(0.0, at_risk - base_sim["blocked"] - (duplicates + 400))

    recovery_rows = [
        {
            "label": label,
            "value": simulate_leakage_scenario(
                hold=fraud,
                dup_rec=rate,
                ov_rec=rate,
                duplicates_amount=duplicates,
                at_risk=at_risk,
            )["total_protected"],
        }
        for label, rate in (
            ("Pessimistic 60%", 60),
            ("Base 80%", 80),
            ("Current 95%", 95),
        )
    ]

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
                "Blocked vs recoverable vs lost",
                [
                    {"label": "Blocked", "value": base_sim["blocked"]},
                    {"label": "Recoverable", "value": duplicates + 400},
                    {"label": "Lost", "value": round(lost, 2)},
                ],
                tag="money",
                note=(
                    "Blocked never leaves; recoverable must be clawed back; "
                    "lost is already gone."
                ),
            ),
        },
        # Sensitivity, not a restatement of side:bottom. Shows how much of
        # "protected" is an assumption about claw-back rather than cash held.
        "recovery": {
            **_bar_chart(
                "Recovery scenario · protected by claw-back rate",
                recovery_rows,
                tag="recovery",
                target=at_risk,
                target_label=f"At risk {_fmt(at_risk)}",
                note=(
                    f"Blocked {_fmt(base_sim['blocked'])} is certain; the rest "
                    "moves with the recovery rate you assume."
                ),
            ),
        },
        "worklist": _table_view(
            "Action worklist",
            wl_headers,
            wl_rows,
            tag="worklist",
        ),
        "vendors": _table_view(
            "Vendor risk radar",
            ["Vendor", "Flags", "Types", "At risk", "Score"],
            vendor_rows,
            tag="risk",
            note="Flags clustered by vendor. Score is illustrative (0–100).",
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
    return _enriched(
        _leakage_dashboard(_call_with_timeout(get_payment_leakage_snapshot))
    )
