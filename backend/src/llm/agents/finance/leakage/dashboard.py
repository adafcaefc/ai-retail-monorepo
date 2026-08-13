"""Leakage dashboard payload + scenario simulation."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.common.dashboard_blocks import (
    _bar_chart,
    _call_with_timeout,
    _donut_chart,
    _enriched,
    _entity_filter,
    _filters,
    _fmt,
    _line_chart,
    _num,
    _pct,
    _period_filter,
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


_SEVERITY_WEIGHT = {"high": 1.0, "critical": 1.0, "medium": 0.6, "low": 0.25}

# What the flag is, when nothing states how bad it is. The newdata ledger
# carries `leakage_type` and no severity column at all, so reading only
# `severity`/`risk_level` scored every row 0.0 and quietly retired the 35%
# severity term — the whole of QC-046. Ranked by intent and recoverability:
# deliberate fraud outranks money already paid twice, which outranks a
# control breach, which outranks a discount nobody claimed.
_TYPE_SEVERITY = {
    "bank-change fraud": 1.0,
    "duplicate payment": 0.8,
    "overbilling (3-way)": 0.6,
    "split / threshold": 0.5,
    "lost discount": 0.25,
}

# Exposure dominates, but a High-severity flag on a small amount still has to
# outrank a Low-severity one, and a repeat offender outranks a one-off.
_SCORE_WEIGHTS = {"amount": 0.5, "severity": 0.35, "flags": 0.15}


def _severity_weight(row: dict[str, Any]) -> float:
    """How serious one flag is, on 0..1.

    An explicit severity column wins when a dataset carries one; otherwise the
    kind of leakage stands in for it. A flag of an unrecognised type scores as
    medium rather than 0.0 — unknown is not the same as harmless, and scoring
    it zero is what let the severity term disappear unnoticed.
    """
    label = str(_row_get(row, "severity", "risk_level") or "").strip().lower()
    if label:
        return _SEVERITY_WEIGHT.get(label, 0.6)

    kind = str(
        _row_get(row, "leakage_type", "anomaly_type", "type", "category") or ""
    ).strip().lower()
    if kind:
        return _TYPE_SEVERITY.get(kind, 0.6)
    return 0.0


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

        bucket = grouped.setdefault(
            name,
            {
                "amount": 0.0,
                "flags": 0,
                "kinds": set(),
                "score": 0.0,
                "severity": 0.0,
            },
        )
        bucket["amount"] += amount
        bucket["flags"] += 1
        bucket["score"] = max(
            bucket["score"], _num(_row_get(row, "risk_score", "score"))
        )
        # A vendor is as risky as its worst flag, not its average.
        bucket["severity"] = max(bucket["severity"], _severity_weight(row))
        if kind:
            bucket["kinds"].add(kind)

    ordered = sorted(
        grouped.items(), key=lambda kv: kv[1]["amount"], reverse=True
    )

    # Scored relative to the worst vendor in the batch, so the column reads as
    # "how bad is this one compared with our worst" rather than an absolute.
    top_amount = max((a["amount"] for _, a in ordered), default=0.0)
    top_flags = max((a["flags"] for _, a in ordered), default=0)

    out: list[list[Any]] = []
    for name, agg in ordered[:10]:
        kinds = ", ".join(sorted(agg["kinds"])) or "—"
        score = agg["score"]
        if not score:
            score = 100.0 * (
                _SCORE_WEIGHTS["amount"]
                * (agg["amount"] / top_amount if top_amount else 0.0)
                + _SCORE_WEIGHTS["severity"] * agg["severity"]
                + _SCORE_WEIGHTS["flags"]
                * (agg["flags"] / top_flags if top_flags else 0.0)
            )
        out.append(
            [
                name,
                agg["flags"],
                kinds,
                _fmt(agg["amount"]),
                str(round(min(100.0, score))),
            ]
        )
    return out


def _leakage_dashboard(snap: dict[str, Any]) -> dict[str, Any]:
    summary_rows = snap.get("summary") or []
    categories = snap.get("category_breakdowns") or []
    anomalies = snap.get("anomalies") or []
    worklist = snap.get("action_worklist") or []
    summary = summary_rows[0] if summary_rows else {}
    daily = snap.get("daily_at_risk") or []

    def _trend(match: Any = None) -> list[float]:
        """Flagged amount per invoice date, for one KPI's slice of the cycle.

        QC-054: a KPI tile carried no trend anywhere. This is a real series —
        one point per day the scan covers — not a shape drawn to fill the
        space. Days with nothing flagged still get a zero so the spacing stays
        honest.
        """
        buckets: dict[str, float] = {}
        for row in daily:
            on_date = str(_row_get(row, "on_date", "invoice_date") or "")
            if not on_date:
                continue
            buckets.setdefault(on_date, 0.0)
            if match is None or match(row):
                buckets[on_date] += _num(_row_get(row, "amount"))
        series = [buckets[key] for key in sorted(buckets)]
        return [round(value, 2) for value in series] if len(series) >= 2 else []

    def _is_type(*names: str):
        wanted = {name.lower() for name in names}
        return lambda row: str(
            _row_get(row, "anomaly_type") or ""
        ).lower() in wanted

    def _is_status(*names: str):
        """Match on where the money stands, not on whether the invoice is paid.

        This read `payment_status`, so the Blocked card's sparkline tracked
        the six Pending invoices rather than the four cases actually stopped
        before payment -- mostly the recoverable and lost ones, i.e. the
        opposite set.
        """
        wanted = {name.lower() for name in names}
        return lambda row: str(
            _row_get(row, "leakage_status") or ""
        ).lower() in wanted

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

    # Fraud and duplicates are read off the category rows and nothing else.
    # These used to fall back to 3,800 and 3,050 when the lookup came back
    # empty -- the previous dataset's group totals. An entity with no fraud
    # case therefore still showed a 3,800 fraud card: Singapore reported
    # 3,800 + 3,050 against 940 flagged, contradicting the category chart
    # beside it. An entity with no such case has none, and zero is the answer.
    fraud = 0.0
    duplicates = 0.0
    for row in cat_rows:
        low = row["label"].lower()
        if "fraud" in low or "bank" in low:
            fraud += row["value"]
        if "dup" in low:
            duplicates += row["value"]

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
    # run reproduces the cards exactly. Both are residuals of a real figure,
    # so they carry no default of their own: if nothing is blocked beyond the
    # fraud hold, the residual is zero.
    other_blocked = max(0.0, blocked_db - fraud)
    overbill = max(0.0, recoverable_db - duplicates)

    base_sim = simulate_leakage_scenario(
        hold=fraud,
        dup_rec=_DUP_REC,
        ov_rec=_OV_REC,
        duplicates_amount=duplicates,
        overbill_amount=overbill,
        other_blocked=other_blocked,
        at_risk=at_risk,
    )

    # Presence, not truthiness. An entity can legitimately have nothing
    # blocked, and `or` would read that real zero as "unknown" and substitute
    # a simulated figure.
    blocked = (
        blocked_db
        if _row_get(summary, "blocked_before_payment_idr_mn", "blocked_idr_mn")
        is not None
        else base_sim["blocked"]
    )
    recoverable = (
        recoverable_db
        if _row_get(
            summary, "recoverable_already_paid_idr_mn", "recoverable_idr_mn"
        )
        is not None
        else duplicates + overbill
    )
    lost = (
        _num(lost_db)
        if lost_db is not None
        else max(0.0, at_risk - blocked - recoverable)
    )
    # Protection is what survives the claw-back rate, so it comes from the
    # simulator unless the snapshot states one. That keeps the card and a
    # zero-delta simulator run on the same number by construction.
    protected = protected_db or base_sim["total_protected"]

    kpis = [
        {
            "id": "flagged",
            "view": "worklist",
            "label": "Flagged this cycle",
            "value": _fmt(at_risk),
            "unit": "mn",
            "delta": f"{items_flagged} flags",
            "alert": True,
            "trend": _trend(),
        },
        {
            "id": "fraud",
            "view": "categories",
            "label": "Fraud held",
            "value": _fmt(fraud),
            "unit": "mn",
            "delta": "bank change",
            "alert": fraud > 0,
            "trend": _trend(_is_type("Bank-change fraud")),
        },
        {
            "id": "dup",
            "view": "vendors",
            "label": "Duplicates",
            "value": _fmt(duplicates),
            "unit": "mn",
            "delta": "recoverable",
            "alert": False,
            "trend": _trend(_is_type("Duplicate payment")),
        },
        {
            "id": "blocked",
            "view": "blockvs",
            "label": "Blocked",
            "value": _fmt(blocked),
            "unit": "mn",
            "delta": "before payment",
            "alert": False,
            "trend": _trend(_is_status("Blocked before payment")),
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
            "Indicative breakdown — no category amounts resolved for this "
            "batch."
        )
    else:
        # QC-001. This used to read "they add up to the {at_risk} at risk",
        # which was simply untrue once QC-015 took the control-weakness
        # categories out of the bars: the bars total 7,845 and the card reads
        # 9,795. Naming all three figures lets the reader close the gap on
        # screen instead of assuming one of them is wrong.
        cat_note = (
            f"Direct-loss categories add up to "
            f"{_fmt(sum(r['value'] for r in cat_rows))}."
        )
    if control_rows:
        control_total = sum(r["value"] for r in control_rows)
        control_names = ", ".join(r["label"] for r in control_rows)
        cat_note += (
            f" {control_names} adds {_fmt(control_total)} more as a control"
            " weakness — flagged, but not counted as lost cash, which is why"
            f" 'Flagged this cycle' reads {_fmt(at_risk)}."
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
            note=(
                "Flags clustered by vendor. Score 0–100 weights at-risk "
                "amount 50%, worst severity 35%, flag count 15%, relative to "
                "the worst vendor this cycle."
            ),
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

    # QC-043 — leakage type, status and vendor, the three lenses the tracker
    # calls "must have" for this agent.
    filters = _filters(views, side, (
        ("leakage_type", "Leakage type", "view:categories",
         ("view:categories", "side:top"), 0),
        ("status", "Status", "view:blockvs", ("view:blockvs",), 0),
        ("vendor", "Vendor", "view:vendors", ("view:vendors",), 0),
    ))

    return {
        "agent": "leakage",
        # QC-035: the span these figures cover, stamped onto every
        # chart by _enriched().
        "period": snap.get("period"),
        "filters": filters,
        "server_filters": [
            _entity_filter(
                snap.get("legal_entities"), snap.get("legal_entity_id")
            ),
            _period_filter(
                snap.get("available_months"), snap.get("period_value")
            ),
        ],
        "import_batch_id": snap.get("import_batch_id"),
        "default_view": "categories",
        "kpis": kpis,
        "views": views,
        "side": side,
        "simulator": {
            # QC-052: the recovery band the workbook brackets its case with.
            "presets": [
                {
                    "id": "pessimistic",
                    "label": "Pessimistic recovery",
                    "note": "60% claw-back on both duplicate and overbilling.",
                    "values": {"dupRec": 60, "ovRec": 60},
                },
                {
                    "id": "workbook",
                    "label": "Workbook rates",
                    "note": "95% on duplicates, 90% on overbilling.",
                    "values": {"dupRec": _DUP_REC, "ovRec": _OV_REC},
                },
                {
                    "id": "release_hold",
                    "label": "Release the hold",
                    "note": "Nothing blocked before payment.",
                    "values": {"hold": 0},
                },
            ],
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
        },
    }


# Leakage has a month but no category dimension; see
# get_payment_leakage_snapshot's docstring.
SUPPORTED_FILTERS: frozenset[str] = frozenset({"legal_entity_id", "period"})


def build(scope: DashboardScope | None = None) -> dict[str, Any]:
    scope = scope or DashboardScope()
    return _enriched(
        _leakage_dashboard(
            _call_with_timeout(
                lambda: get_payment_leakage_snapshot(
                    scope.legal_entity_id, scope.period
                )
            )
        )
    )
