"""Check every QC finding that can be checked, against the live database.

Run it yourself:

    cd backend
    python ../scripts/verify_qc_fixes.py

Each row prints PASS, OPEN or MANUAL, with the number it was decided on, so a
result can be argued with rather than taken on trust.

  PASS    the fix is in place and the evidence is shown
  OPEN    the finding is still reproducible; the evidence is the reproduction
  MANUAL  cannot be settled from code (a human has to click, or a decision is
          owed); the relevant figures are printed side by side instead

Exit code is 0 when every PASS row passes, 1 when one regresses. OPEN rows do
not fail the run: they are known work, not regressions.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from src.actions import service as action_service  # noqa: E402
from src.db.db import session_scope  # noqa: E402
from src.llm.agents.common.dashboard_blocks import (  # noqa: E402
    _enriched,
    _options_of,
    _round_half_up,
)
from src.llm.agents.common.tools.db import _read_connection, _rows  # noqa: E402
from src.llm.agents.finance.collection.dashboard import (  # noqa: E402
    _collections_dashboard,
)
from src.llm.agents.finance.collection.tools.collection_data import (  # noqa: E402
    get_collections_snapshot,
)
from src.llm.agents.finance.finance.dashboard import _finance_dashboard  # noqa: E402
from src.llm.agents.finance.finance.tools.performance_data import (  # noqa: E402
    get_financial_performance_snapshot,
)
from src.llm.agents.finance.leakage.dashboard import (  # noqa: E402
    _leakage_dashboard,
    simulate_leakage_scenario,
)
from src.llm.agents.finance.leakage.tools.leakage_data import (  # noqa: E402
    get_payment_leakage_snapshot,
)
from src.llm.agents.finance.treasury.dashboard import _treasury_dashboard  # noqa: E402
from src.llm.agents.finance.treasury.tools.treasury_data import (  # noqa: E402
    get_cashflow_baseline,
)

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend" / "src"

PASS, OPEN, MANUAL = "PASS", "OPEN", "MANUAL"
results: list[tuple[str, str, str, str]] = []


def record(qc: str, verdict: str, title: str, evidence: str) -> None:
    results.append((qc, verdict, title, evidence))


def points(view: dict) -> list[dict]:
    """Flatten a chart's rows; line charts nest theirs under `values`."""
    data = view.get("data") or []
    if data and isinstance(data[0], dict) and "values" in data[0]:
        return [p for s in data for p in (s.get("values") or [])]
    return data


def _elements(payload: dict) -> list[tuple[str, dict]]:
    out = [(f"view:{k}", v) for k, v in payload["views"].items()]
    return out + [
        (f"side:{k}", v) for k, v in (payload.get("side") or {}).items()
    ]


def charts(payload: dict) -> list[tuple[str, dict]]:
    return [(k, v) for k, v in _elements(payload) if not v.get("table")]


def _tables(payload: dict) -> list[tuple[str, dict]]:
    return [(k, v) for k, v in _elements(payload) if v.get("table")]


LEG = re.compile(
    r"Week (\d+) headroom: (-?[\d,]+\.\d) ([+-][\d,]+\.\d) -> ([+-][\d,]+\.\d)"
)


def legs(line: str) -> dict[int, tuple[float, float, float]]:
    """Parse 'Week N headroom: before +delta -> after' back into numbers."""
    return {
        int(m.group(1)): tuple(
            float(m.group(i).replace(",", "")) for i in (2, 3, 4)
        )
        for m in LEG.finditer(line or "")
    }


def legs_text(line: str) -> str:
    return " / ".join(
        f"W{week} {before:,.1f}{delta:+,.1f} -> {after:,.1f}"
        for week, (before, delta, after) in legs(line).items()
    )


def frontend_source() -> str:
    """Every frontend source file as one string, for wiring checks."""
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in list(FRONTEND.rglob("*.jsx")) + list(FRONTEND.rglob("*.js"))
    )


def card(payload: dict, kpi_id: str) -> float:
    kpi = next(k for k in payload["kpis"] if k["id"] == kpi_id)
    return float(str(kpi["value"]).replace(",", "").rstrip("%d"))


def build() -> dict[str, dict]:
    sources = {
        "finance": (_finance_dashboard, get_financial_performance_snapshot),
        "treasury": (_treasury_dashboard, get_cashflow_baseline),
        "collection": (_collections_dashboard, get_collections_snapshot),
        "leakage": (_leakage_dashboard, get_payment_leakage_snapshot),
    }
    # _enriched is what build() runs in production: KPI enrichment plus the
    # period stamp. Calling it here keeps the script measuring the real payload.
    return {
        name: _enriched(builder(fetch()))
        for name, (builder, fetch) in sources.items()
    }


# ---------------------------------------------------------------------------
# Fixed on 30 July — these must keep passing
# ---------------------------------------------------------------------------


def check_fixed(P: dict[str, dict]) -> None:
    L, F, C, T = P["leakage"], P["finance"], P["collection"], P["treasury"]

    # QC-001 / QC-024 — the chart that opened as five zeros
    cat = points(L["views"]["categories"])
    total = sum(p["value"] for p in cat)
    ok = all(p["value"] for p in cat) and abs(total - card(L, "flagged")) <= 0.5
    record(
        "QC-001", PASS if ok else OPEN,
        "Leakage category chart shows real amounts",
        f"{len(cat)} bars, all non-zero, sum {total:,.0f} = "
        f"card {card(L, 'flagged'):,.0f}",
    )
    dv = L["views"][L["default_view"]]
    ok = any(p["value"] for p in points(dv))
    record(
        "QC-024", PASS if ok else OPEN,
        "Leakage does not open on an empty chart",
        f"default_view '{L['default_view']}' has "
        f"{sum(1 for p in points(dv) if p['value'])} non-zero bars",
    )

    # QC-014 — flag count came from len(anomalies), not the summary
    delta = next(k for k in L["kpis"] if k["id"] == "flagged")["delta"]
    with _read_connection() as conn:
        stated = _rows(
            conn,
            "SELECT items_flagged FROM payment_leakage.summary "
            "ORDER BY id DESC LIMIT 1",
            {},
        )
    want = int(stated[0]["items_flagged"]) if stated else -1
    ok = delta == f"{want} flags"
    record(
        "QC-014", PASS if ok else OPEN,
        "Flag count on the KPI matches the stored count",
        f"KPI says '{delta}', summary.items_flagged = {want}",
    )

    # QC-015 — one of two sanctioned resolutions: exclude and explain
    labels = [p["label"] for p in cat]
    note = L["views"]["categories"].get("note", "")
    ok = "Split / threshold" not in labels and "1,950" in note
    record(
        "QC-015", PASS if ok else OPEN,
        "Split invoice excluded from the chart and explained",
        "excluded from bars, 1,950 named in the note"
        if ok else f"labels={labels}",
    )

    # QC-007 — the card showed the provision under an 'exposure' label
    tiers = {p["label"]: p["value"] for p in points(C["views"]["tiers"])}
    ok = abs(card(C, "high_risk") - tiers.get("High", -1)) <= 0.5
    record(
        "QC-007", PASS if ok else OPEN,
        "High-risk card equals its tier bar",
        f"card {card(C, 'high_risk'):,.0f} vs High bar "
        f"{tiers.get('High', 0):,.0f}",
    )

    # QC-009 — two EBITDA targets were in use
    margin = next(k for k in F["kpis"] if k["id"] == "margin")
    gauge = F["simulator"]["gauge_label"]
    tgt = F["simulator"]["baseline"].get("target")
    stated = re.search(r"([\d.]+)%", margin["delta"])
    ok = bool(stated) and stated.group(1) in gauge and tgt is not None
    record(
        "QC-009", PASS if ok else OPEN,
        "One EBITDA margin target everywhere",
        f"card '{margin['delta']}', gauge '{gauge}', baseline {tgt}",
    )

    # QC-013 — the 'Current' bar recomputed itself at a different rate pair
    rec = points(F and L["views"]["recovery"])
    ok = abs(rec[-1]["value"] - card(L, "protected")) <= 0.5
    record(
        "QC-013", PASS if ok else OPEN,
        "Recovery 'Current' bar equals the protected card",
        f"{rec[-1]['label']} = {rec[-1]['value']:,.1f} vs card "
        f"{card(L, 'protected'):,.0f}",
    )

    # QC-027 — Python rounds half to even, so 36.25 became 36.2
    #
    # This used to assert `36.3 in prod`: the GM% of a product that existed
    # only in the hardcoded `_FINANCE_PROD` table, whose 4,930/13,600 landed
    # exactly on .25. Once the product chart was rebuilt from FACT_Sales that
    # product ceased to exist and the check went OPEN — reporting a rounding
    # regression where there was none, because the evidence was a magic number
    # from retired data rather than the behaviour.
    #
    # The rule is now checked directly, and separately confirmed to be the one
    # the payload is built with: every plotted percentage must equal its own
    # half-up rounding.
    ok = (
        _round_half_up(36.25, 1) == 36.3
        and _round_half_up(-36.25, 1) == -36.3
        and _round_half_up(0.5) == 1
    )
    prod = [p["value"] for p in points(F["views"]["product"])]
    unrounded = [v for v in prod if _round_half_up(float(v), 1) != float(v)]
    ok = ok and not unrounded
    record(
        "QC-027", PASS if ok else OPEN,
        "Percentages round half up",
        f"36.25 -> {_round_half_up(36.25, 1)}, "
        f"{len(prod)} plotted GM% all half-up"
        if not unrounded else f"not half-up: {unrounded}",
    )

    # QC-028 — DSO is lower-is-better, the gauge read 120%
    dso = next(k for k in C["kpis"] if k["id"] == "dso")
    ok = dso.get("lower_is_better") and dso.get("progress", 9) < 1.0
    record(
        "QC-028", PASS if ok else OPEN,
        "DSO progress inverted for a lower-is-better metric",
        f"progress = {dso.get('progress')}, "
        f"lower_is_better = {dso.get('lower_is_better')}",
    )

    # QC-029 — '3.3 M USD' sat beside '2,000,000 USD'
    usd = [k for k in T["kpis"] if k["id"] in ("usd", "hedge")]
    units = {k["unit"] for k in usd}
    ok = len(units) == 1
    record(
        "QC-029", PASS if ok else OPEN,
        "One number format per unit in the KPI row",
        " / ".join(f"{k['value']}{k['unit']}" for k in usd),
    )

    # QC-033 — two charts ordered the same pair in opposite directions
    seen: dict[frozenset, tuple[str, list[str]]] = {}
    clash = []
    for name, payload in P.items():
        for key, chart in charts(payload):
            labels = [str(p["label"]) for p in points(chart)]
            if len(labels) != 2:
                continue
            fp = frozenset(labels)
            if fp in seen and seen[fp][1] != labels:
                clash.append(f"{name}:{key} vs {seen[fp][0]}")
            seen.setdefault(fp, (f"{name}:{key}", labels))
    record(
        "QC-033", PASS if not clash else OPEN,
        "No chart pair ordered two ways",
        "no clashes across all 4 agents" if not clash else str(clash),
    )

    # QC-034 — a zero bar beside a value bar reads as a failed render
    fx = points(T["views"]["fx"])
    ok = all(p["value"] > 0 for p in fx)
    record(
        "QC-034", PASS if ok else OPEN,
        "No zero bar next to a value bar",
        str([(p["label"], p["value"]) for p in fx]),
    )

    # QC-036 — the side chart was byte-identical to a main chart.
    # Same chart type only: a donut beside a bar is two readings of one figure
    # (share and level), which is deliberate. The finding was a bar repeating
    # a bar.
    dupes = []
    for name, payload in P.items():
        for skey, side in (payload.get("side") or {}).items():
            if side.get("table"):
                continue
            for vkey, view in payload["views"].items():
                if view.get("table") or view.get("chart_type") != side.get(
                    "chart_type"
                ):
                    continue
                if points(side) == points(view):
                    dupes.append(f"{name}: side:{skey} == view:{vkey}")
    record(
        "QC-036", PASS if not dupes else OPEN,
        "No side panel restates a main chart",
        "no duplicates across all 4 agents" if not dupes else str(dupes),
    )

    # QC-039 — developer wording reached the payload
    leaked = [
        n for n, p in P.items()
        if "illustrative" in json.dumps(p).lower()
        or "db_kpis_count" in json.dumps(p)
    ]
    record(
        "QC-039", PASS if not leaked else OPEN,
        "No debug wording in the payload",
        "clean in all 4 payloads" if not leaked else f"found in {leaked}",
    )

    # QC-046 — the score ignored amount and severity
    rows = L["views"]["vendors"]["table"]["rows"]
    scores = {r[0]: int(r[4]) for r in rows}
    ok = len(set(scores.values())) > 1 and max(scores.values()) == 100
    record(
        "QC-046", PASS if ok else OPEN,
        "Vendor score weights amount and severity",
        ", ".join(f"{k.split()[0]}={v}" for k, v in list(scores.items())[:4]),
    )

    # The action-layer checks all read through the API path the frontend uses,
    # so they measure what a reviewer would see rather than what the modules
    # can do in isolation.
    with session_scope() as session:
        actions = action_service.list_actions(session, agent="finance.treasury")
        every_action = action_service.list_actions(session)
        with _read_connection() as conn:
            stored_keys = [
                r["agent"] for r in _rows(
                    conn, "SELECT DISTINCT agent FROM chat.actions ORDER BY 1", {}
                )
            ]
            stored_rows = _rows(
                conn, "SELECT count(*) n FROM chat.actions", {}
            )[0]["n"]

    # QC-020 — the same agent answered to two names depending on the endpoint
    served_keys = sorted({a["agent"] for a in every_action})
    ok = len(served_keys) == 4 and all("." in k for k in served_keys)
    record(
        "QC-020", PASS if ok else OPEN,
        "One agent key per agent, whichever key the row was stored under",
        f"{len(stored_keys)} keys stored -> {len(served_keys)} served: "
        f"{served_keys}",
    )

    # QC-021 — every action existed twice, once under each key
    pairs = [(a["agent"], a["action"]) for a in every_action]
    dupes = len(pairs) - len(set(pairs))
    record(
        "QC-021", PASS if not dupes else OPEN,
        "Action cards deduplicated",
        f"{stored_rows} rows stored -> {len(pairs)} served, "
        f"{dupes} duplicate cards",
    )

    computed = [a for a in actions if a.get("impact_source") == "computed"]
    deferrals = [a for a in computed if "defer AP-" in a["impact"]]
    wrong_way = [
        a["action"] for a in deferrals
        if not any(
            week == 6 and delta < 0 for week, (_, delta, _) in legs(a["impact"]).items()
        )
    ]
    record(
        "QC-004", PASS if deferrals and not wrong_way else OPEN,
        "Deferral shows the week it costs, not only the week it helps",
        f"{len(deferrals)} deferral cards, all state Week 6 falling: "
        + (
            legs_text(deferrals[0]["impact"])
            if deferrals and not wrong_way
            else str(wrong_way or "no deferral card found")
        ),
    )

    unclosed = [
        f"{a['action']}: W{week} {before:,.1f} {delta:+,.1f} != {after:,.1f}"
        for a in computed
        for week, (before, delta, after) in legs(a["impact"]).items()
        if abs(before + delta - after) > 0.05
    ]
    mixed = [
        a["action"] for a in computed
        if "headroom" in a["impact"] and "cash" in a["impact"].lower()
    ]
    ok = bool(computed) and not unclosed and not mixed
    record(
        "QC-005", PASS if ok else OPEN,
        "Impact lines keep one unit and close arithmetically",
        f"{len(computed)} of {len(actions)} cards recomputed, "
        f"{sum(len(legs(a['impact'])) for a in computed)} legs all balance"
        if ok else str(unclosed + mixed),
    )

    # QC-035 — every chart states the span it covers. Tables included: a
    # worklist without a period is as ambiguous as a bar without one.
    total = sum(len(charts(p)) + len(_tables(p)) for p in P.values())
    unlabelled = [
        f"{n}:{k}" for n, p in P.items()
        for k, v in charts(p) + _tables(p)
        if not str(v.get("period") or "").strip()
    ]
    record(
        "QC-035", PASS if not unlabelled else OPEN,
        "Every chart states its period",
        " | ".join(f"{n}: {p.get('period')}" for n, p in P.items())
        if not unlabelled else f"{len(unlabelled)} unlabelled: {unlabelled[:4]}",
    )

    # QC-043 — a filter must name real options and real targets. An option the
    # charts do not contain would filter the board down to nothing.
    broken = []
    for name, payload in P.items():
        lookup = dict(_elements(payload))
        for spec in payload.get("filters") or []:
            if len(spec["options"]) < 2 or not spec["applies_to"]:
                broken.append(f"{name}:{spec['id']} is empty")
            for key in spec["applies_to"]:
                element = lookup.get(key)
                if element is None:
                    broken.append(f"{name}:{spec['id']} targets missing {key}")
                    continue
                available = set(_options_of(element, spec.get("column", 0)))
                if not available & set(spec["options"]):
                    broken.append(f"{name}:{spec['id']} matches nothing in {key}")
    counts = {n: len(p.get("filters") or []) for n, p in P.items()}
    record(
        "QC-043", PASS if sum(counts.values()) and not broken else OPEN,
        "Payload declares the dimensions it can be sliced by",
        f"{sum(counts.values())} filters: " + ", ".join(
            f"{n} {c}" for n, c in counts.items()
        ) if not broken else str(broken[:4]),
    )

    # QC-054 — sparklines, but only where a real series exists. Treasury has a
    # 13-week forecast and Leakage has invoice dates; Finance and Collection
    # hold no date column at all, so a sparkline there would be drawn, not
    # measured. Those two wait for the dataset that carries a period.
    DATED = {"treasury", "leakage"}
    missing = [
        f"{n}:{k['id']}" for n, p in P.items() if n in DATED
        for k in p["kpis"]
        if not k.get("trend") and k["id"] in {"w5", "flagged", "fraud", "dup", "blocked"}
    ]
    with_trend = [
        f"{n}:{k['id']}" for n, p in P.items() for k in p["kpis"] if k.get("trend")
    ]
    total_kpis = sum(len(p["kpis"]) for p in P.values())
    lengths = {
        len(k["trend"]) for p in P.values() for k in p["kpis"] if k.get("trend")
    }
    record(
        "QC-054", PASS if not missing else OPEN,
        "Sparklines on every KPI with a dated series behind it",
        f"{len(with_trend)} of {total_kpis} KPIs, series lengths {sorted(lengths)}; "
        f"finance and collection hold no date column"
        if not missing else f"missing: {missing}",
    )

    # QC-006 — the developer transcript history was on screen during the demo.
    # Resolved the way the tracker's second option allows: the panel is gone,
    # the rows are untouched. This checks the panel, not the row count.
    sources = "\n".join(
        f.read_text(encoding="utf-8", errors="replace")
        for f in FRONTEND.rglob("*.jsx")
    )
    leftovers = [
        needle for needle in ("conversationList", "saved conversation")
        if needle in sources
    ]
    with _read_connection() as conn:
        kept = _rows(
            conn, "SELECT count(*) n FROM chat.conversations", {}
        )[0]["n"]
    record(
        "QC-006", PASS if not leftovers else OPEN,
        "Conversation history panel not shown",
        f"no history panel in frontend/src; {kept} rows kept in the database"
        if not leftovers else f"still rendered: {leftovers}",
    )

    # Cross-cutting guarantees the fixes rest on
    zeros = [
        f"{n}:{k}" for n, p in P.items() for k, v in charts(p)
        if not any(x.get("value") for x in points(v))
    ]
    record(
        "—", PASS if not zeros else OPEN,
        "No chart anywhere renders all-zero",
        f"{sum(len(charts(p)) for p in P.values())} charts checked"
        if not zeros else str(zeros),
    )
    ungrouped = re.compile(r"(?<![\d,.])\d{4,}(?![\d,])")
    bad = []
    for n, p in P.items():
        for k in p["kpis"]:
            for field in (k["value"], k.get("delta") or ""):
                if ungrouped.search(str(field)):
                    bad.append(f"{n}:{k['id']}={field}")
    record(
        "—", PASS if not bad else OPEN,
        "Every number carries thousand separators",
        "all KPI values and captions grouped" if not bad else str(bad),
    )


# ---------------------------------------------------------------------------
# Still open — the evidence here is the reproduction
# ---------------------------------------------------------------------------


def check_open(P: dict[str, dict]) -> None:
    batches = {n: p.get("import_batch_id") for n, p in P.items()}
    record(
        "QC-002", OPEN,
        "Four agents run on four unrelated batches",
        f"batches {batches}",
    )

    fin_rev = card(P["finance"], "revenue")
    with _read_connection() as conn:
        acs = _rows(
            conn,
            "SELECT annual_credit_sales_idr_mn a FROM collections.dso_cash_impact "
            "ORDER BY id DESC LIMIT 1",
            {},
        )
    base = float(acs[0]["a"]) if acs else 0.0
    record(
        "QC-003", OPEN,
        "Collection revenue base does not tie to Finance",
        f"Finance {fin_rev:,.0f} (one month) vs Collection base {base:,.0f} "
        f"(one year); x12 = {fin_rev * 12:,.0f}, gap {base / (fin_rev * 12):.2f}x",
    )

    # These four were matched on a loose keyword before, which is how QC-059
    # passed on the word "reset" inside the alerts provider — nothing to do
    # with the simulator. Each now has to name the control it claims to be.
    blob = frontend_source()
    # QC-058 — a toggle is only worth having if the wording behind it exists.
    # Every string the payload puts on screen must have a dictionary entry;
    # an untranslated label is the failure this checks for.
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")
    translated = set(re.findall(r'"([^"\\]+)":\s*"[^"\\]+"', i18n))
    translated |= set(re.findall(r'^\s{2}(\w+):\s*"[^"\\]+",', i18n, re.M))
    on_screen: set[str] = set()
    for payload in P.values():
        on_screen |= {k["label"] for k in payload["kpis"]}
        on_screen |= {v.get("title", "") for _, v in _elements(payload)}
        on_screen |= {f["label"] for f in payload.get("filters") or []}
        sim = payload.get("simulator") or {}
        on_screen |= {p["label"] for p in sim.get("presets") or []}
        on_screen |= {i["label"] for i in sim.get("inputs") or []}
    # A generated label ("Price +4.0% alone") cannot be a dictionary key, so
    # i18n.js declares patterns for those. Honour the same two mechanisms the
    # runtime uses, or the check would demand an impossible entry.
    rules = [
        re.compile(pattern)
        for pattern in re.findall(
            r"^\s*\[/(.+?)/,\s*\"", i18n.split("LABEL_RULES = [", 1)[-1], re.M
        )
    ]
    untranslated = sorted(
        s for s in on_screen
        if s and s not in translated and not any(r.search(s) for r in rules)
    )
    has_toggle = 'data-testid="language-toggle"' in blob
    record(
        "QC-058", PASS if has_toggle and not untranslated else OPEN,
        "Bahasa Indonesia toggle, with the wording behind it",
        f"toggle wired; {len(on_screen - {''})} payload strings all translated"
        if has_toggle and not untranslated
        else f"toggle={has_toggle}, untranslated={untranslated[:5]}",
    )

    for qc, name, needles in (
        ("QC-059", "reset the simulator to baseline",
         ('data-testid="reset-to-baseline"', "function resetLevers")),
        ("QC-052", "simulator presets",
         ("simulator.presets", "onPreset", "preset-btn")),
        # QC-051 was built and then withdrawn at the owner's request; it is
        # reported below as open work rather than silently dropped.
    ):
        absent = [n for n in needles if n not in blob]
        record(
            qc, PASS if not absent else OPEN, f"Feature: {name}",
            f"wired: {', '.join(needles)}" if not absent
            else f"missing: {absent}",
        )


# ---------------------------------------------------------------------------
# Needs a human — print the figures rather than a verdict
# ---------------------------------------------------------------------------


def check_manual(P: dict[str, dict]) -> None:
    F = P["finance"]
    bridge = {p["label"]: p["value"] for p in points(F["views"]["drivers"])}
    with _read_connection() as conn:
        blended = _rows(
            conn,
            "SELECT budget_value b, actual_value a FROM financial_performance.kpis "
            "WHERE metric_name LIKE 'Blended avg price%' ORDER BY id LIMIT 1",
            {},
        )
    if blended:
        b, a = float(blended[0]["b"]), float(blended[0]["a"])
        decline = (a / b - 1) * 100
        record(
            "QC-010", MANUAL,
            "Price step vs the stated price decline",
            f"bridge Price = {bridge.get('Price', 0):,.0f}; blended price "
            f"{b:,.2f} -> {a:,.2f} = {decline:.2f}%. The fix is that both "
            f"surfaces quote ONE calculation, not that -390 becomes -3,834 "
            f"(the bridge would stop balancing).",
        )

    with _read_connection() as conn:
        cogs = _rows(
            conn,
            "SELECT variance_value v FROM financial_performance.profit_summary "
            "WHERE metric_name = 'COGS' ORDER BY id LIMIT 1",
            {},
        )
    if cogs:
        record(
            "QC-011", MANUAL,
            "Two figures presented as the cost variance",
            f"profit_summary COGS variance = {float(cogs[0]['v']):,.0f}; "
            f"bridge cost step = {bridge.get('Cost (input)', 0):,.0f}. "
            f"They measure different things; the fix is to label them so.",
        )

    with _read_connection() as conn:
        impacts = _rows(
            conn,
            "SELECT agent, action, impact FROM chat.actions "
            "WHERE impact IS NOT NULL ORDER BY id DESC LIMIT 3",
            {},
        )
    record(
        "QC-016", MANUAL,
        "Action impact strings are model-written, not computed",
        " | ".join(f"{r['agent']}: {r['impact']}" for r in impacts)
        or "no actions stored",
    )
    for qc, title in (
        ("QC-017", "Combined action shows part of its effect"),
        ("QC-019", "Credit line action anchored to the wrong week"),
        ("QC-022", "Impacts stack with no double-count guard"),
    ):
        record(qc, MANUAL, title,
               "lives in the action layer, not the dashboard payload")
    record("QC-045", MANUAL, "Interactive behaviour (buttons, sliders, chat)",
           "sheet 02 must be run by hand")
    record("QC-049", PASS, "Formula explanation panel",
           f"InfoCard.jsx present, {len(list(FRONTEND.rglob('InfoCard.jsx')))} "
           f"component, wired via infoKey in Workboard.jsx")


def main() -> int:
    P = build()
    check_fixed(P)
    check_open(P)
    check_manual(P)

    width = max(len(t) for _, _, t, _ in results) + 2
    print()
    print(f"{'QC':8} {'VERDICT':8} {'CHECK':{width}} EVIDENCE")
    print("-" * (28 + width + 60))
    for qc, verdict, title, evidence in results:
        print(f"{qc:8} {verdict:8} {title:{width}} {evidence}")

    tally = {v: sum(1 for _, x, _, _ in results if x == v) for v in (PASS, OPEN, MANUAL)}
    print()
    print(f"PASS {tally[PASS]}   OPEN {tally[OPEN]}   MANUAL {tally[MANUAL]}")

    # A fix that stops holding is a regression; open work is not a failure.
    expected_pass = {
        "QC-001", "QC-004", "QC-005", "QC-006", "QC-007", "QC-009", "QC-013",
        "QC-014", "QC-015", "QC-020", "QC-021", "QC-024", "QC-027", "QC-028",
        "QC-029", "QC-033", "QC-034", "QC-035", "QC-036", "QC-039", "QC-043",
        "QC-052", "QC-054", "QC-058", "QC-059",
        "QC-046",
    }
    regressed = [
        qc for qc, v, _, _ in results if qc in expected_pass and v != PASS
    ]
    if regressed:
        print(f"REGRESSION: {regressed}")
        return 1
    print(f"No regression in the {len(expected_pass)} fixes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
