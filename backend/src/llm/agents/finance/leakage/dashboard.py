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
    _num,
    _pct,
    _row_get,
    _table_view,
    _waterfall_chart,
)
from src.llm.agents.finance.leakage.tools.leakage_data import (
    get_payment_leakage_snapshot,
)

# Baseline claw-back rates the workbook assumes. Kept as module constants so
# the KPI cards, the recovery chart and the simulator defaults cannot drift.
_DUP_REC = 95.0
_OV_REC = 90.0


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

        amount = _num(
            _row_get(
                row,
                "amount_at_risk_idr_mn",
                "amount_idr_mn",
                "amount",
                "value",
            )
        )

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
        return _num(
            _row_get(
                row,
                "amount_at_risk_idr_mn",
                "amount_idr_mn",
                "amount",
                "value",
                "exposure_idr_mn",
            )
        )

    def cat_name(row: dict[str, Any]) -> str:
        return str(
            _row_get(row, "category_name", "category", "name", "label") or "Other"
        )

    def cat_is_direct_loss(row: dict[str, Any]) -> bool:
        """Split/threshold flags are control weaknesses, not lost cash.

        The workbook keeps them out of the at-risk total, so the category
        charts have to as well — otherwise the bars stop adding up to the
        "Flagged this cycle" card.
        """
        val = _row_get(row, "is_direct_loss", "direct_loss")
        if val is None:
            return True
        if isinstance(val, str):
            return val.strip().lower() in {"true", "t", "yes", "y", "1"}
        return bool(val)

    direct_rows: list[dict[str, Any]] = []
    control_rows: list[dict[str, Any]] = []
    for category in categories:
        row = {"label": cat_name(category), "value": cat_amount(category)}
        if not row["value"]:
            continue
        target = direct_rows if cat_is_direct_loss(category) else control_rows
        target.append(row)

    # A batch with no resolvable amounts still has to render something, but it
    # must say so — an unannounced fallback is how the previous column-name
    # miss stayed hidden behind numbers that looked right.
    cat_is_live = bool(direct_rows)
    if not cat_is_live:
        direct_rows = [
            {"label": "Bank-change fraud", "value": 3800.0},
            {"label": "Duplicate payment", "value": 3050.0},
            {"label": "Overbilling (3-way)", "value": 900.0},
            {"label": "Lost discount", "value": 95.0},
        ]
    cat_rows = direct_rows

    # Everything below is derived from `summary` when the batch has it and
    # from the category rows otherwise, so a single number backs each figure.
    at_risk = (
        _num(
            _row_get(
                summary,
                "total_amount_at_risk_idr_mn",
                "total_at_risk_idr_mn",
                "flagged_idr_mn",
                "total_idr_mn",
            )
        )
        or sum(r["value"] for r in cat_rows)
        or 7845.0
    )
    items_flagged = int(
        _num(_row_get(summary, "items_flagged", "flagged_count"))
        or len(anomalies)
        or len(worklist)
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

    blocked_db = _num(
        _row_get(summary, "blocked_before_payment_idr_mn", "blocked_idr_mn")
    )
    recoverable_db = _num(
        _row_get(summary, "recoverable_already_paid_idr_mn", "recoverable_idr_mn")
    )
    protected_db = _num(
        _row_get(summary, "total_cash_protected_idr_mn", "protected_idr_mn")
    )
    lost_db = _row_get(summary, "lost_this_cycle_idr_mn", "lost_idr_mn")

    # Hold + other-blocked and duplicates + overbill are the two splits the
    # simulator works on; back them out of the stored totals so a zero-delta
    # run reproduces the cards exactly.
    other_blocked = max(0.0, blocked_db - fraud) if blocked_db else 500.0
    overbill = max(0.0, recoverable_db - duplicates) if recoverable_db else 400.0

    base_sim = simulate_leakage_scenario(
        hold=fraud,
        dup_rec=_DUP_REC,
        ov_rec=_OV_REC,
        duplicates_amount=duplicates,
        overbill_amount=overbill,
        other_blocked=other_blocked,
        at_risk=at_risk,
    )

    blocked = blocked_db or base_sim["blocked"]
    protected = protected_db or base_sim["total_protected"]
    recoverable = recoverable_db or (duplicates + overbill)
    lost = (
        _num(lost_db)
        if lost_db is not None
        else max(0.0, at_risk - blocked - recoverable)
    )

    kpis = [
        {
            "id": "flagged",
            "view": "worklist",
            "label": "Flagged this cycle",
            "value": _fmt(at_risk),
            "unit": "mn",
            "delta": f"{items_flagged} flags",
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
            "value": _fmt(blocked),
            "unit": "mn",
            "delta": "before payment",
            "alert": False,
        },
        {
            "id": "protected",
            "view": "recovery",
            "label": "Total protected",
            "value": _fmt(protected),
            "unit": "mn",
            "delta": "this cycle",
            "alert": False,
        },
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
                    _num(
                        _row_get(
                            row,
                            "amount_at_risk_idr_mn",
                            "amount_idr_mn",
                            "amount",
                            "value",
                        )
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
                        _num(
                            _row_get(
                                row,
                                "amount_at_risk_idr_mn",
                                "amount_idr_mn",
                                "amount",
                                "value",
                            )
                        )
                    ),
                ]
            )

    vendor_rows = _leakage_vendor_rollup(worklist or anomalies)

    def _protected_at(dup_rate: float, ov_rate: float) -> float:
        return simulate_leakage_scenario(
            hold=fraud,
            dup_rec=dup_rate,
            ov_rec=ov_rate,
            duplicates_amount=duplicates,
            overbill_amount=overbill,
            other_blocked=other_blocked,
            at_risk=at_risk,
        )["total_protected"]

    recovery_rows = [
        {"label": "Pessimistic 60%", "value": _protected_at(60, 60)},
        {"label": "Base 80%", "value": _protected_at(80, 80)},
        # The current point is the KPI card's number, not a re-derivation of
        # it, so the bar and the card can never disagree.
        {
            "label": f"Current {_DUP_REC:.0f}/{_OV_REC:.0f}%",
            "value": round(protected, 2),
        },
    ]

    if not cat_is_live:
        cat_note = (
            "Illustrative breakdown; category_breakdowns has no resolvable "
            "amount column in this batch."
        )
    else:
        cat_note = (
            f"Direct-loss categories; they add up to the {_fmt(at_risk)} at risk."
        )
    if control_rows:
        control_total = sum(r["value"] for r in control_rows)
        control_names = ", ".join(r["label"] for r in control_rows)
        cat_note += (
            f" {control_names} adds {_fmt(control_total)} more as a control"
            " weakness — flagged, but not counted as lost cash."
        )

    views = {
        "categories": {
            **_bar_chart(
                "Leakage & fraud by category",
                cat_rows,
                tag="breakdown",
                target=at_risk,
                target_label=f"At risk {_fmt(at_risk)}",
                note=cat_note,
            ),
        },
        "blockvs": {
            **_bar_chart(
                "Blocked vs recoverable vs lost",
                [
                    {"label": "Blocked", "value": round(blocked, 2)},
                    {"label": "Recoverable", "value": round(recoverable, 2)},
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
                    f"Blocked {_fmt(blocked)} is certain; the rest moves with "
                    "the recovery rate you assume."
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
                    {"label": "At risk", "value": round(at_risk, 2)},
                    {"label": "Protected", "value": round(protected, 2)},
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
                    "default": _DUP_REC,
                    "unit": "%",
                },
                {
                    "id": "ovRec",
                    "label": "Overbill rec %",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "default": _OV_REC,
                    "unit": "%",
                },
            ],
            "baseline": {
                "duplicates_amount": duplicates,
                "overbill_amount": overbill,
                "other_blocked": other_blocked,
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
