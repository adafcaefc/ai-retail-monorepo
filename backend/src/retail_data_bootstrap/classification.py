from __future__ import annotations

from .models import SheetSpec

VALID_CLASSIFICATIONS = frozenset(
    {"STRUCTURED", "SEMANTIC", "BOTH", "DERIVED", "IGNORE"}
)


def _s(
    classification: str,
    reason: str,
    orientation: str,
    header_row: int = 5,
    *keys: tuple[str, ...],
) -> SheetSpec:
    return SheetSpec(classification, reason, orientation, header_row, keys)


SHEET_SPECS: dict[str, SheetSpec] = {
    "LISTING": _s("IGNORE", "Workbook navigation index; it duplicates sheet metadata.", "documentation", 1, ("no",), ("sheet",)),
    "Cover & Storyline": _s("SEMANTIC", "Narrative scope and usage context is useful for retrieval but is not a fact table.", "documentation", 3),
    "Constants": _s("BOTH", "Named model parameters and what-if levers are exact values with business-rule context.", "source", 5, ("parameter",)),
    "Verticals": _s("BOTH", "Legal-entity/vertical master data is relational and useful semantic scope context.", "source", 5, ("id",), ("vertical",)),
    "Stores": _s("BOTH", "Store master supports exact joins and concise store context documents.", "source", 5, ("store_id",)),
    "Categories": _s("BOTH", "Category master supports exact joins and category/perishability context.", "source", 5, ("cat_id",)),
    "Main Vendor": _s("BOTH", "Vendor master contains exact commercial/service attributes and supplier context.", "source", 5, ("vendor_account",), ("vendor",)),
    "Trade Agreement": _s("STRUCTURED", "Item-vendor price agreements are high-volume exact commercial facts best queried in SQL.", "source", 5, ("item", "vendor_account", "valid_from", "min_qty_break")),
    "SKU_Master": _s("BOTH", "The SKU master is the main product fact source and the anchor for joined SKU documents.", "source", 5, ("sku_id",)),
    "ENGINE": _s("DERIVED", "Formula-derived chain-level inventory snapshot; load as structured facts, do not document each raw row separately.", "derived", 5, ("sku",)),
    "ENGINE_STORE": _s("DERIVED", "Formula-derived store-by-SKU calculation grid; retain in SQL only because row-level semantic documents would be repetitive.", "derived", 3, ("sku_id", "store")),
    "A1 Demand Forecasting": _s("DERIVED", "Agent summary/reporting output derived from engine facts.", "reporting", 5, ("vertical",)),
    "A2 Inventory Risk": _s("DERIVED", "Agent summary/reporting output derived from engine facts.", "reporting", 5, ("vertical",)),
    "A3 Replenishment": _s("DERIVED", "Agent summary/reporting output derived from engine facts.", "reporting", 5, ("vertical",)),
    "Replenishment Detail": _s("DERIVED", "Formula-derived requisition proposal; useful as structured operational facts.", "derived", 5, ("item",)),
    "A4 Promotion": _s("DERIVED", "Agent summary/reporting output derived from promotion and engine facts.", "reporting", 5, ("vertical",)),
    "Promotion & Discount Detail": _s("BOTH", "Promotion definitions contain exact dates/amounts plus human-readable mechanism and D365 context.", "source", 5, ("promo_id",)),
    "A5 Pricing & Markdown": _s("DERIVED", "Agent summary/reporting output derived from engine facts.", "reporting", 5, ("vertical",)),
    "A6 Assortment": _s("DERIVED", "Agent summary/reporting output derived from engine facts.", "reporting", 5, ("vertical",)),
    "A7 Workforce Optimizer": _s("DERIVED", "Agent summary/reporting output derived from workforce facts.", "reporting", 5, ("vertical",)),
    "A8 Vendor & Brand": _s("DERIVED", "Agent summary/reporting output derived from vendor and brand facts.", "reporting", 5, ("vertical",)),
    "A9 AI Summary": _s("DERIVED", "Consolidated reporting output derived from other agent summaries.", "reporting", 5, ("vertical",)),
    "Vendor Scorecard": _s("DERIVED", "Calculated vendor performance rollup derived from vendor, SKU, and engine facts.", "derived", 5, ("vendor",)),
    "Brand Performance": _s("DERIVED", "Calculated brand performance rollup derived from SKU and engine facts.", "derived", 5, ("brand",)),
    "Brand Events": _s("BOTH", "Store event master has exact store relationships and meaningful event context.", "source", 5, ("store", "event")),
    "Workforce": _s("DERIVED", "Calculated store staffing snapshot; retain as structured facts.", "derived", 5, ("store",)),
    "Vertical Rollup": _s("DERIVED", "Cross-agent vertical rollup is reproducible reporting output.", "reporting", 5, ("vertical",)),
    "What-If Simulator": _s("DERIVED", "Baseline/live scenario output is derived from editable constants.", "reporting", 6, ("vertical", "metric")),
    "What-If · Per Agent": _s("DERIVED", "Illustrative +20% scenario output is derived and explicitly labelled illustrative.", "reporting", 5, ("vertical",)),
    "Command Center Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A1 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A2 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A3 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A4 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A5 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A6 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A7 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "A8 Charts": _s("IGNORE", "Presentation-only chart backing ranges duplicate report calculations.", "presentation", 6),
    "UOM & PO Summary": _s("DERIVED", "Vertical purchase-order summary is derivable from SKU and engine facts.", "reporting", 5, ("vertical",)),
    "Time Series 24mo": _s("DERIVED", "Generated vertical monthly sales series; normalize to exact SQL facts, not semantic prose.", "derived", 5, ("month",)),
    "Formulas": _s("SEMANTIC", "Business calculation definitions are retrieval-oriented knowledge; runtime formula storage remains separate.", "documentation", 5, ("metric",)),
    "Terminology": _s("SEMANTIC", "Business glossary is designed for semantic retrieval.", "documentation", 5, ("term",)),
    "Data Sources": _s("SEMANTIC", "Source-system and refresh mapping is integration knowledge rather than current business facts.", "documentation", 5, ("source_object",)),
    "D365 Table Reference": _s("SEMANTIC", "D365 tables, keys, joins, and retrieval notes are integration knowledge.", "documentation", 5, ("number",)),
    "D365 Field Mapping": _s("SEMANTIC", "Field-level D365 mapping and transformations are integration knowledge.", "documentation", 5),
    "D365 Worked Example": _s("SEMANTIC", "Worked integration trace is explanatory validation knowledge.", "documentation", 6, ("number",)),
    "ERP Approval Matrix": _s("SEMANTIC", "Approval tiers and roles are governance rules for retrieval; thresholds are not transactional data.", "documentation", 5, ("flow",)),
    "Agentic Prompts": _s("SEMANTIC", "Agent roles, triggers, outputs, and guardrails are operating knowledge.", "documentation", 5, ("agent",)),
    "Demo Script": _s("IGNORE", "Presales presentation script is not a business fact or production knowledge source.", "presentation", 5, ("step",)),
}


def validate_sheet_specs(sheet_names: list[str]) -> None:
    missing = sorted(set(sheet_names) - set(SHEET_SPECS))
    extra = sorted(set(SHEET_SPECS) - set(sheet_names))
    invalid = sorted(
        name
        for name, spec in SHEET_SPECS.items()
        if spec.classification not in VALID_CLASSIFICATIONS
    )
    if missing or extra or invalid:
        raise ValueError(
            f"Sheet classification mismatch: missing={missing}, extra={extra}, invalid={invalid}"
        )


def classification_counts() -> dict[str, int]:
    return {
        classification: sum(
            spec.classification == classification for spec in SHEET_SPECS.values()
        )
        for classification in sorted(VALID_CLASSIFICATIONS)
    }
