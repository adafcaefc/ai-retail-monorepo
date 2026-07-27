"""Collection dashboard payload."""

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
from src.llm.agents.finance.collection.tools.collection_data import (
    get_collections_snapshot,
)


def _collections_dashboard(snap: dict[str, Any]) -> dict[str, Any]:
    summary = snap.get("summary") or {}
    customers = snap.get("customers") or []
    risk_tiers = snap.get("risk_tiers") or []
    worklist = snap.get("worklist") or []

    total_ar = float(summary.get("total_ar_idr_mn") or 0)
    overdue = float(summary.get("overdue_ar_idr_mn") or 0)
    overdue_pct = float(summary.get("overdue_percentage") or 0)
    dso = float(summary.get("current_dso_days") or 0)
    target_dso = float(summary.get("target_dso_days") or 47)
    cash_freed = float(summary.get("cash_freed_at_target_idr_mn") or 0)
    high_risk = float(summary.get("high_risk_provision_idr_mn") or 0)
    if not high_risk:
        for tier in risk_tiers:
            if str(tier.get("risk_tier", "")).lower() == "high":
                high_risk = float(tier.get("exposure_idr_mn") or 0)
                break

    aging = {
        "Current": 0.0,
        "1-30": 0.0,
        "31-60": 0.0,
        "61-90": 0.0,
        "90+": 0.0,
    }
    for row in customers:
        aging["Current"] += float(row.get("current_idr_mn") or 0)
        # customer query may not include current_idr_mn — recompute from tool fields
        if "current_idr_mn" not in row:
            pass
        aging["1-30"] += float(row.get("overdue_1_30_idr_mn") or 0)
        aging["31-60"] += float(row.get("overdue_31_60_idr_mn") or 0)
        aging["61-90"] += float(row.get("overdue_61_90_idr_mn") or 0)
        aging["90+"] += float(row.get("overdue_90_plus_idr_mn") or 0)

    # If current missing from SELECT, infer from summary
    if aging["Current"] == 0 and summary.get("current_ar_idr_mn") is not None:
        aging["Current"] = float(summary["current_ar_idr_mn"])

    aging_rows = [
        {"label": label, "value": round(value, 2)}
        for label, value in aging.items()
    ]

    top_customer = worklist[0] if worklist else {}
    customer_name = str(
        top_customer.get("customer_name")
        or "PT Anugerah Prima (Customer A)"
    )
    max_pull = float(top_customer.get("overdue_idr_mn") or 10000)

    # Three reach levels: one call, a focused push, or chase everything.
    # Each converts recoverable cash into the DSO it would buy.
    daily_sales = total_ar / dso if dso else 0.0

    def _expected(rows: list[dict[str, Any]]) -> float:
        rates = {"low": 0.95, "medium": 0.85, "high": 0.40}
        got = 0.0
        for row in rows:
            amount = float(row.get("overdue_idr_mn") or 0)
            explicit = row.get("expected_recovery_idr_mn")
            if explicit is not None:
                try:
                    got += float(explicit)
                    continue
                except (TypeError, ValueError):
                    pass
            tier = str(row.get("risk_tier") or "medium").strip().lower()
            got += amount * rates.get(tier, 0.85)
        return got

    short_name = customer_name.split("(")[0].strip()[:14]
    if worklist:
        levels = [
            (short_name, _expected(worklist[:1])),
            ("Top 5", _expected(worklist[:5])),
            ("All overdue", _expected(worklist)),
        ]
    else:
        # No worklist rows — approximate the reach levels from the overdue
        # total at a blended recovery rate. Kept monotonic on purpose:
        # wider reach can never free less.
        blended = 0.85
        levels = [
            (short_name, min(max_pull, overdue) * blended),
            ("Top 5", min(max_pull * 3.5, overdue) * blended),
            ("All overdue", overdue * blended),
        ]

    options_bars = []
    for label, freed in levels:
        if daily_sales:
            new_dso = (total_ar - freed) / daily_sales
            label = f"{label} · {new_dso:.0f}d"
        options_bars.append({"label": label, "value": round(freed, 2)})

    kpis = [
        {
            "id": "ar",
            "view": "aging",
            "label": "AR outstanding",
            "value": _fmt(total_ar),
            "unit": "mn",
            "delta": "IDR book",
            "alert": False,
        },
        {
            "id": "overdue",
            "view": "aging",
            "label": "Overdue",
            "value": _fmt(overdue),
            "unit": "mn",
            "delta": f"{overdue_pct * 100:.0f}% of AR"
            if overdue_pct <= 1
            else f"{overdue_pct:.0f}% of AR",
            "alert": overdue > 0,
        },
        {
            "id": "dso",
            "view": "prize",
            "label": "DSO",
            "value": f"{dso:.0f}d",
            "unit": "",
            "delta": f"target {target_dso:.0f}",
            "alert": dso > target_dso,
        },
        {
            "id": "prize",
            "view": "prize",
            "label": "Cash freed at target",
            "value": _fmt(cash_freed),
            "unit": "mn",
            "delta": "the prize",
            "alert": False,
        },
        {
            "id": "high_risk",
            "view": "tiers",
            "label": "High-risk exposure",
            "value": _fmt(high_risk),
            "unit": "mn",
            "delta": "provision / high tier",
            "alert": high_risk > 0,
        },
    ]

    views: dict[str, Any] = {
        "aging": {
            **_bar_chart(
                "Receivables aging (IDR mn)",
                aging_rows,
                tag="aging",
                note=f"Overdue {_fmt(overdue)} of {_fmt(total_ar)}.",
            ),
        },
        "worklist": _table_view(
            "Who to chase first · ranked worklist",
            [
                "Customer",
                "Overdue",
                "Bucket",
                "Tier",
                "Exp rec",
            ],
            [
                [
                    str(w.get("customer_name") or ""),
                    _fmt(float(w.get("overdue_idr_mn") or 0)),
                    str(w.get("oldest_aging_bucket") or ""),
                    str(w.get("risk_tier") or ""),
                    _fmt(float(w.get("expected_recovery_idr_mn") or 0)),
                ]
                for w in worklist[:8]
            ],
            tag="worklist",
        ),
        "prize": {
            **_bar_chart(
                "The prize · DSO to cash",
                [
                    {"label": "Now", "value": round(dso, 2)},
                    {"label": "Target", "value": round(target_dso, 2)},
                ],
                y_axis_title="days",
                tag="impact",
                target=target_dso,
                target_label=f"Target {target_dso:.0f}",
                note=(
                    f"Hitting {target_dso:.0f} days frees about "
                    f"{_fmt(cash_freed)} mn."
                ),
            ),
        },
        "tiers": {
            **_bar_chart(
                "Risk exposure by tier",
                [
                    {
                        "label": str(t.get("risk_tier") or ""),
                        "value": float(t.get("exposure_idr_mn") or 0),
                    }
                    for t in risk_tiers
                ],
                tag="risk",
            ),
        },
        "options": {
            **_bar_chart(
                "Three collection options · cash freed",
                options_bars,
                tag="decision",
                note=(
                    "Bar is cash freed; the label carries the DSO it buys. "
                    "Wider reach frees more but costs more effort."
                ),
            ),
        },
    }

    side = {
        "top": _donut_chart(
            "Aging mix",
            aging_rows,
            tag="aging",
        ),
        "bottom": {
            **_bar_chart(
                "DSO vs target",
                [
                    {"label": "Target", "value": round(target_dso, 2)},
                    {"label": "Now", "value": round(dso, 2)},
                ],
                y_axis_title="days",
                tag="impact",
            ),
        },
    }

    return {
        "agent": "collections",
        "import_batch_id": snap.get("import_batch_id"),
        "default_view": "aging",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            "action": "calculate_collection_scenario",
            "gauge_label": f"DSO vs {target_dso:.0f}-day target",
            "submit_data": {"customer_name": customer_name},
            "inputs": [
                {
                    "id": "cash_to_collect_idr_mn",
                    "label": "Pull from customer (mn)",
                    "min": 0,
                    "max": max(max_pull, 1),
                    "step": 100,
                    "default": min(5000, max_pull) if max_pull else 0,
                    "unit": "IDR mn",
                },
                {
                    "id": "discount_pct",
                    "label": "Discount %",
                    "min": 0,
                    "max": 3,
                    "step": 0.1,
                    "default": 1,
                    "unit": "%",
                },
            ],
            "baseline": {
                "dso": dso,
                "target_dso": target_dso,
                "total_ar": total_ar,
                "daily_credit_sales": float(
                    summary.get("daily_credit_sales_idr_mn") or 0
                ),
            },
        },
        "raw": {
            "summary": summary,
            "worklist_top": top_customer,
        },
    }


def build() -> dict[str, Any]:
    return _enriched(
        _collections_dashboard(_call_with_timeout(get_collections_snapshot))
    )
