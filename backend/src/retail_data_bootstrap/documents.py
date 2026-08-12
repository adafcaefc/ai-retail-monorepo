from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from .models import SemanticDocument
from .normalization import normalize_workbook
from .semantic_contract import VOLATILE_MODEL_PARAMETERS, retrieval_domain_for
from .source import ExcelSourceAdapter, json_value


def slugify(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip())
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def document_key(doc_type: str, source_key: Any) -> str:
    suffix = slugify(source_key)
    if not suffix:
        raise ValueError(f"Cannot build a document key from {source_key!r}")
    return f"{slugify(doc_type)}:{suffix}"


def canonical_content(content: str) -> str:
    return "\n".join(line.rstrip() for line in content.strip().splitlines())


def content_hash(content: str) -> str:
    return hashlib.sha256(canonical_content(content).encode("utf-8")).hexdigest()


def _doc(
    doc_type: str,
    source_sheet: str,
    source_key: Any,
    content: str,
    metadata: dict[str, Any],
) -> SemanticDocument:
    normalized = canonical_content(content)
    clean_metadata = {
        key: json_value(value)
        for key, value in metadata.items()
        if value is not None and value != ""
    }
    key_text = str(source_key)
    return SemanticDocument(
        doc_key=document_key(doc_type, key_text),
        doc_type=doc_type,
        retrieval_domain=retrieval_domain_for(doc_type),
        source_sheet=source_sheet,
        source_key=key_text,
        content=normalized,
        metadata=clean_metadata,
        content_hash=content_hash(normalized),
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "not provided"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)


def _days(value: Any) -> str:
    rendered = _fmt(value)
    return f"{rendered} {'day' if rendered == '1' else 'days'}"


def _index(rows: Iterable[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {row[key]: row for row in rows}


def build_documents(path: Path) -> list[SemanticDocument]:
    dataset = normalize_workbook(path)
    tables = dataset.tables
    entities = _index(tables["LegalEntity"], "legal_entity_id")
    stores = _index(tables["Store"], "store_id")
    categories = _index(tables["Category"], "category_id")
    vendors = _index(tables["Vendor"], "vendor_account")
    agreements_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tables["TradeAgreement"]:
        agreements_by_sku[row["sku_id"]].append(row)

    docs: list[SemanticDocument] = []
    for row in tables["LegalEntity"]:
        content = (
            f"{row['legal_entity_id']} is the legal-entity code for {row['legal_entity_name']}, "
            f"labelled {row['short_name']} in AI Retail 360. It defines the business scope used "
            "to organize stores, categories, SKUs, and operational facts."
        )
        docs.append(_doc("vertical", "Verticals", row["legal_entity_id"], content, {
            "legal_entity_id": row["legal_entity_id"], "vertical": row["legal_entity_name"],
            "short_name": row["short_name"], "source_row": row["source_row"],
        }))

    for row in tables["Store"]:
        entity = entities[row["legal_entity_id"]]
        content = (
            f"Store {row['store_id']} is {row['store_name']} in {entity['legal_entity_name']} "
            f"({row['legal_entity_id']}). It belongs to the {_fmt(row['cluster'])} cluster and "
            f"operates through the {_fmt(row['channel'])} channel."
        )
        docs.append(_doc("store", "Stores", row["store_id"], content, {
            "store_id": row["store_id"], "legal_entity_id": row["legal_entity_id"],
            "vertical": entity["legal_entity_name"], "cluster": row["cluster"],
            "channel": row["channel"], "source_row": row["source_row"],
        }))

    for row in tables["Category"]:
        entity = entities[row["legal_entity_id"]]
        content = (
            f"Category {row['category_id']} is {row['category_name']} in "
            f"{entity['legal_entity_name']} ({row['legal_entity_id']}). The workbook marks this "
            f"category as {'perishable' if row['is_perishable'] else 'non-perishable'}."
        )
        docs.append(_doc("category", "Categories", row["category_id"], content, {
            "category_id": row["category_id"], "category": row["category_name"],
            "legal_entity_id": row["legal_entity_id"], "perishable": row["is_perishable"],
            "source_row": row["source_row"],
        }))

    for row in tables["Vendor"]:
        content = (
            f"Vendor account {row['vendor_account']} is {row['vendor_name']} ({row['vendor_code']}), "
            f"classified as {_fmt(row['vendor_group'])}. Commercial terms are "
            f"{_fmt(row['payment_terms'])}, {_fmt(row['delivery_terms'])}, currency "
            f"{_fmt(row['currency'])}, lead time {_days(row['lead_time_days'])}, and MOQ "
            f"{_fmt(row['moq_units'])} units."
        )
        docs.append(_doc("vendor", "Main Vendor", row["vendor_account"], content, {
            "vendor_account": row["vendor_account"], "vendor": row["vendor_code"],
            "vendor_name": row["vendor_name"], "group": row["vendor_group"],
            "currency": row["currency"], "source_row": row["source_row"],
        }))

    for row in tables["Brand"]:
        content = (
            f"Brand {row['brand_name']} is a product-brand identity recorded in the SKU master."
        )
        docs.append(_doc("brand", "SKU_Master", row["brand_name"], content, {
            "brand": row["brand_name"], "source_row": row["source_row"],
        }))

    for row in tables["Sku"]:
        entity = entities[row["legal_entity_id"]]
        category = categories[row["category_id"]]
        vendor = vendors[row["vendor_account"]]
        agreements = agreements_by_sku[row["sku_id"]]
        designated = next((item for item in agreements if item["is_designated"]), None)
        alternate_exists = any(not item["is_designated"] for item in agreements)
        agreement_text = (
            f" A designated supplier agreement is recorded with "
            f"{vendors[designated['vendor_account']]['vendor_name']} "
            f"({designated['vendor_account']})."
            if designated else " No designated supplier agreement is recorded."
        )
        if alternate_exists:
            agreement_text += " Alternate approved supplier agreements are also recorded."
        content = (
            f"SKU {row['sku_id']} is {row['item_name']} in the {category['category_name']} category "
            f"of {entity['legal_entity_name']} ({row['legal_entity_id']}). It is "
            f"{'perishable' if row['is_perishable'] else 'non-perishable'}, branded {row['brand_name']}, "
            f"with main vendor {vendor['vendor_name']} ({vendor['vendor_account']}). It sells in "
            f"{_fmt(row['sales_uom'])} and is bought in {_fmt(row['buy_uom'])} with pack factor "
            f"{_fmt(row['pack_factor'])}; workbook lead time is {_days(row['lead_time_days'])} "
            f"and safety coverage is {_days(row['safety_days'])}.{agreement_text}"
        )
        docs.append(_doc("sku", "SKU_Master", row["sku_id"], content, {
            "sku_id": row["sku_id"], "legal_entity_id": row["legal_entity_id"],
            "vertical": entity["legal_entity_name"], "category_id": row["category_id"],
            "category": category["category_name"], "vendor_account": row["vendor_account"],
            "vendor": vendor["vendor_name"], "brand": row["brand_name"],
            "perishable": row["is_perishable"],
            "channel": row["channel"], "source_row": row["source_row"],
            "source_sheets": ["SKU_Master", "Categories", "Verticals", "Main Vendor", "Trade Agreement"],
        }))

    for row in tables["Promotion"]:
        entity = entities[row["legal_entity_id"]]
        content = (
            f"Promotion {row['promotion_id']}, {row['promotion_name']}, is a {row['discount_type']} "
            f"for {entity['legal_entity_name']} with {_fmt(row['scope'])} scope targeting "
            f"{_fmt(row['target_category'])}. The mechanism is {_fmt(row['mechanism'])}; the value "
            f"rule is {_fmt(row['value_rule'])}, the minimum quantity or threshold is "
            f"{_fmt(row['min_quantity_threshold'])}, and supplier funding is "
            f"{_fmt(row['supplier_funding_pct'])}%. It is valid from "
            f"{_fmt(row['valid_from'])} to {_fmt(row['valid_to'])}. The workbook maps it to "
            f"{_fmt(row['d365_construct'])}."
        )
        docs.append(_doc("promotion", "Promotion & Discount Detail", row["promotion_id"], content, {
            "promotion_id": row["promotion_id"], "legal_entity_id": row["legal_entity_id"],
            "vertical": entity["legal_entity_name"], "category": row["target_category"],
            "discount_type": row["discount_type"], "valid_from": row["valid_from"],
            "valid_to": row["valid_to"], "source_row": row["source_row"],
        }))

    for row in tables["BrandEvent"]:
        store = stores[row["store_id"]]
        content = (
            f"Store event {row['event_name']} is recorded for {store['store_name']} "
            f"({row['store_id']}) in legal entity {row['legal_entity_id']}. It provides named "
            "operational context for store and workforce planning."
        )
        key = f"{row['store_id']}-{row['event_name']}"
        docs.append(_doc("brand_event", "Brand Events", key, content, {
            "store_id": row["store_id"], "legal_entity_id": row["legal_entity_id"],
            "event": row["event_name"], "source_row": row["source_row"],
        }))

    docs.extend(_documentation_documents(path))
    return sorted(docs, key=lambda document: document.doc_key)


def _documentation_documents(path: Path) -> list[SemanticDocument]:
    adapter = ExcelSourceAdapter(path)
    docs: list[SemanticDocument] = []

    cover_rows = list(adapter.rows("Cover & Storyline"))
    cover_lines = [str(row.get("ai_retail_360_multi_vertical_dataset_v8_2_bring_to_any_retail_client")) for row in cover_rows if row.get("ai_retail_360_multi_vertical_dataset_v8_2_bring_to_any_retail_client")]
    docs.append(_doc("workbook_overview", "Cover & Storyline", "retail-360-v8-2", " ".join(cover_lines[:3]), {"source_rows": [row["_source_row"] for row in cover_rows[:3]]}))

    for row in adapter.rows("Constants"):
        if row.get("value") is None:
            continue
        parameter = row["parameter"]
        if parameter in VOLATILE_MODEL_PARAMETERS:
            content = f"Workbook defines {parameter} as an adjustable model or What-If parameter."
            metadata = {"parameter": parameter, "source_row": row["_source_row"]}
        else:
            content = f"Workbook model parameter {parameter} has configured value {_fmt(row['value'])}."
            metadata = {"parameter": parameter, "value": row["value"], "source_row": row["_source_row"]}
        docs.append(_doc("model_parameter", "Constants", parameter, content, metadata))

    for row in adapter.rows("Formulas"):
        metric = row["metric"]
        content = f"Business formula for {metric}: {row['formula']}. Notes: {_fmt(row.get('notes'))}."
        docs.append(_doc("formula", "Formulas", metric, content, {"metric": metric, "source_row": row["_source_row"]}))

    for row in adapter.rows("Terminology"):
        term = row["term"]
        docs.append(_doc("terminology", "Terminology", term, f"{term}: {row['definition']}", {"term": term, "source_row": row["_source_row"]}))

    for row in adapter.rows("Data Sources"):
        key = row["source_object"]
        content = f"{key} is sourced from {row['system']}, refreshed {row['refresh']}, and consumed by {row['consumed_by']}."
        docs.append(_doc("data_source", "Data Sources", key, content, {"source_object": key, "system": row["system"], "refresh": row["refresh"], "source_row": row["_source_row"]}))

    for row in adapter.rows("D365 Table Reference"):
        number = row.get("column_1")
        if not isinstance(number, (int, float)):
            continue
        entity = row["business_entity_our_dataset"]
        table = row["d365_f_o_table_aot_sql"]
        content = (
            f"D365 mapping {int(number)} for {entity}: use {table} in the {row['layer']} layer. "
            f"Primary key: {row['primary_key']}. Related joins: {row['related_to_join_field']}. "
            f"Retrieve {row['key_fields_to_retrieve']}. Notes: {row['module_enum_notes']}. "
            f"Workbook confidence: {row['conf']}."
        )
        docs.append(_doc("d365_table", "D365 Table Reference", f"{int(number)}-{entity}", content, {"business_entity": entity, "d365_table": table, "confidence": row["conf"], "source_row": row["_source_row"]}))

    docs.extend(_d365_field_mapping_docs(list(adapter.rows("D365 Field Mapping"))))

    worked = list(adapter.rows("D365 Worked Example"))
    worked_lines: list[str] = []
    for row in worked:
        values = [str(value) for key, value in row.items() if not key.startswith("_") and value not in (None, "")]
        if values:
            worked_lines.append(" | ".join(values))
    docs.append(_doc("d365_worked_example", "D365 Worked Example", "grc-092-replenishment", "D365 worked integration example for GRC-092.\n" + "\n".join(worked_lines), {"sku_id": "GRC-092", "source_rows": [row["_source_row"] for row in worked]}))

    for row in adapter.rows("ERP Approval Matrix"):
        flow = row["flow"]
        content = f"Approval rule for {flow}: tier 1 is {row['tier_1']}; tier 2 is {row['tier_2']}; tier 3 is {row['tier_3']}."
        docs.append(_doc("approval_rule", "ERP Approval Matrix", flow, content, {"flow": flow, "source_row": row["_source_row"]}))

    for row in adapter.rows("Agentic Prompts"):
        agent = row["agent"]
        content = f"{agent}: role {row['role']}; trigger {row['trigger']}; output {row['output']}; guardrail {row['guardrail']}."
        docs.append(_doc("agent_spec", "Agentic Prompts", agent, content, {"agent": agent, "source_row": row["_source_row"]}))
    return docs


def _d365_field_mapping_docs(rows: list[dict[str, Any]]) -> list[SemanticDocument]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    current_name: str | None = None
    current_rows: list[dict[str, Any]] = []
    for row in rows:
        populated_detail = any(row.get(field) not in (None, "") for field in ("d365_table", "d365_field", "retrieval", "integration_logic_transform_10_0_48", "conf"))
        if not populated_detail:
            if current_name and current_rows:
                groups.append((current_name, current_rows))
            current_name = str(row.get("dataset_column") or f"section-{row['_source_row']}")
            current_rows = []
        elif current_name:
            current_rows.append(row)
    if current_name and current_rows:
        groups.append((current_name, current_rows))

    docs: list[SemanticDocument] = []
    for section, section_rows in groups:
        lines = [f"D365 field mapping for {section}."]
        for row in section_rows:
            lines.append(
                f"{row['dataset_column']}: table {_fmt(row.get('d365_table'))}, field "
                f"{_fmt(row.get('d365_field'))}, retrieval {_fmt(row.get('retrieval'))}; "
                f"logic {_fmt(row.get('integration_logic_transform_10_0_48'))}; "
                f"confidence {_fmt(row.get('conf'))}."
            )
        docs.append(_doc("d365_field_mapping", "D365 Field Mapping", section, "\n".join(lines), {"dataset_section": section, "field_count": len(section_rows), "source_rows": [row["_source_row"] for row in section_rows]}))
    return docs


SAMPLE_COUNTS = {
    "sku": 5,
    "vendor": 1,
    "brand": 1,
    "formula": 1,
    "terminology": 1,
    "d365_field_mapping": 1,
}


def representative_sample(documents: list[SemanticDocument]) -> list[SemanticDocument]:
    selected: list[SemanticDocument] = []
    for doc_type, count in SAMPLE_COUNTS.items():
        matches = [document for document in documents if document.doc_type == doc_type]
        if len(matches) < count:
            raise ValueError(f"Expected at least {count} {doc_type} documents, found {len(matches)}")
        if doc_type == "sku":
            # Exercise joins and naming across distinct legal entities rather
            # than validating five near-identical rows from one SKU prefix.
            distinct: list[SemanticDocument] = []
            seen_entities: set[str] = set()
            for document in matches:
                entity = str(document.metadata.get("legal_entity_id", ""))
                if entity not in seen_entities:
                    distinct.append(document)
                    seen_entities.add(entity)
                if len(distinct) == count:
                    break
            selected.extend(distinct)
        else:
            selected.extend(matches[:count])
    return selected


def write_jsonl(documents: list[SemanticDocument], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for document in documents:
            handle.write(json.dumps(document.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
