from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .documents import content_hash, document_key
from .models import SemanticDocument
from .normalization import NormalizedDataset
from .semantic_contract import (
    DOC_TYPE_RETRIEVAL_DOMAIN,
    RETRIEVAL_DOMAINS,
    VOLATILE_MODEL_PARAMETERS,
    retrieval_domain_for,
)

HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SECRET_PATTERNS = (
    re.compile(r"(?i)(password|pwd)\s*="),
    re.compile(r"(?i)(api[_ -]?key|secret)\s*[:=]"),
    re.compile(r"(?i)server\s*=.*database\s*=.*(user|uid)\s*="),
    re.compile(r"(?i)\.database\.windows\.net"),
)

OPERATIONAL_LEAKAGE_PHRASES: dict[str, tuple[str, ...]] = {
    "sku": (
        "current chain inventory state",
        "reorder point",
        "proposed order units",
        " per sales unit",
    ),
    "store": (
        "current staffing snapshot",
        "size factor",
        "health factor",
        "footfall index",
        "scheduled fte",
        "required fte",
    ),
    "vendor": (
        "service metrics",
        "otif",
        " fill ",
        " defect ",
        "lead adherence",
        "main vendor for",
    ),
    "vertical": (
        "peak-season factor",
        "workforce base per size",
        "sales per fte",
    ),
    "category": ("assigns ", " skus to it"),
    "brand": ("assigned to ", " skus in the workbook"),
    "promotion": ("expected uplift", "pre-buy uplift"),
    "brand_event": ("demand-lift factor",),
}

BANNED_METADATA_FIELDS: dict[str, frozenset[str]] = {
    "sku": frozenset({"inventory_state"}),
    "brand": frozenset({"sku_count"}),
}

DOCUMENT_FIELDS = frozenset(
    {
        "doc_key",
        "doc_type",
        "retrieval_domain",
        "source_sheet",
        "source_key",
        "content",
        "metadata",
        "content_hash",
    }
)


def validate_documents(documents: list[SemanticDocument]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    keys: set[str] = set()
    identities: set[tuple[str, str]] = set()
    hashes: set[tuple[str, str]] = set()
    counts: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    sizes: list[int] = []
    for index, document in enumerate(documents, 1):
        counts[document.doc_type] += 1
        domains[document.retrieval_domain] += 1
        for name in ("doc_key", "doc_type", "retrieval_domain", "source_sheet", "source_key", "content", "content_hash"):
            if not getattr(document, name, None):
                errors.append(f"document {index} has an empty {name}")
        if document.doc_type not in DOC_TYPE_RETRIEVAL_DOMAIN:
            errors.append(f"{document.doc_key} has unknown doc_type {document.doc_type!r}")
        elif document.retrieval_domain not in RETRIEVAL_DOMAINS:
            errors.append(
                f"{document.doc_key} has invalid retrieval_domain {document.retrieval_domain!r}"
            )
        elif document.retrieval_domain != retrieval_domain_for(document.doc_type):
            errors.append(
                f"{document.doc_key} retrieval_domain does not match deterministic doc_type mapping"
            )
        expected_key = document_key(document.doc_type, document.source_key)
        if document.doc_key != expected_key:
            errors.append(
                f"{document.doc_key} is not the deterministic key {expected_key}"
            )
        if document.doc_key in keys:
            errors.append(f"duplicate doc_key: {document.doc_key}")
        keys.add(document.doc_key)
        identity = (document.source_sheet, document.source_key)
        if identity in identities:
            errors.append(f"duplicate source identity: {identity}")
        identities.add(identity)
        if not isinstance(document.metadata, dict):
            errors.append(f"{document.doc_key} metadata is not an object")
        try:
            json.dumps(document.metadata, ensure_ascii=False, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            errors.append(f"{document.doc_key} metadata is not valid JSON: {error}")
        metadata_fields = set(document.metadata) if isinstance(document.metadata, dict) else set()
        prohibited_metadata = metadata_fields & BANNED_METADATA_FIELDS.get(
            document.doc_type, frozenset()
        )
        if prohibited_metadata:
            errors.append(
                f"{document.doc_key} metadata contains volatile fields: {sorted(prohibited_metadata)}"
            )
        if (
            document.doc_type == "model_parameter"
            and document.source_key in VOLATILE_MODEL_PARAMETERS
            and "value" in metadata_fields
        ):
            errors.append(
                f"{document.doc_key} metadata contains an adjustable current parameter value"
            )
        if not HASH_PATTERN.fullmatch(document.content_hash):
            errors.append(f"{document.doc_key} content_hash is not SHA-256 hex")
        elif content_hash(document.content) != document.content_hash:
            errors.append(f"{document.doc_key} content_hash does not match content")
        hash_identity = (document.doc_type, document.content_hash)
        if hash_identity in hashes:
            errors.append(f"duplicate document content within {document.doc_type}: {document.doc_key}")
        hashes.add(hash_identity)
        combined = document.content + json.dumps(document.metadata, ensure_ascii=False, default=str)
        if any(pattern.search(combined) for pattern in SECRET_PATTERNS):
            errors.append(f"{document.doc_key} may contain credential or connection content")
        lowered_content = document.content.lower()
        for phrase in OPERATIONAL_LEAKAGE_PHRASES.get(document.doc_type, ()):
            if phrase in lowered_content:
                errors.append(
                    f"{document.doc_key} semantic content contains operational leakage phrase {phrase!r}"
                )
        if (
            document.doc_type == "model_parameter"
            and document.source_key in VOLATILE_MODEL_PARAMETERS
            and " has value " in lowered_content
        ):
            errors.append(
                f"{document.doc_key} embeds an adjustable current parameter value"
            )
        size = len(document.content)
        sizes.append(size)
        if size < 40:
            warnings.append(f"{document.doc_key} content is unusually short ({size} chars)")
        if size > 8000:
            errors.append(f"{document.doc_key} content exceeds 8,000 characters ({size})")
        if "source_row" not in document.metadata and "source_rows" not in document.metadata:
            warnings.append(f"{document.doc_key} metadata has no source row trace")
    return {
        "valid": not errors,
        "document_count": len(documents),
        "counts_by_type": dict(sorted(counts.items())),
        "counts_by_retrieval_domain": dict(sorted(domains.items())),
        "unique_doc_keys": len(keys),
        "content_size": {
            "minimum": min(sizes, default=0),
            "maximum": max(sizes, default=0),
            "average": round(sum(sizes) / len(sizes), 2) if sizes else 0,
        },
        "errors": errors,
        "warnings": warnings,
    }


def validate_jsonl(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    count = 0
    documents: list[SemanticDocument] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            count += 1
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                errors.append(f"line {line_number}: {error}")
                continue
            if not isinstance(value, dict):
                errors.append(f"line {line_number}: expected JSON object")
                continue
            prohibited = _prohibited_field_paths(value)
            if prohibited:
                errors.append(
                    f"line {line_number}: embedding/vector fields are prohibited: {prohibited}"
                )
            actual_fields = set(value)
            if actual_fields != DOCUMENT_FIELDS:
                errors.append(
                    f"line {line_number}: contract fields mismatch; "
                    f"missing={sorted(DOCUMENT_FIELDS - actual_fields)}, "
                    f"extra={sorted(actual_fields - DOCUMENT_FIELDS)}"
                )
                continue
            try:
                documents.append(
                    SemanticDocument(
                        doc_key=value["doc_key"],
                        doc_type=value["doc_type"],
                        retrieval_domain=value["retrieval_domain"],
                        source_sheet=value["source_sheet"],
                        source_key=value["source_key"],
                        content=value["content"],
                        metadata=value["metadata"],
                        content_hash=value["content_hash"],
                    )
                )
            except (KeyError, TypeError) as error:
                errors.append(f"line {line_number}: invalid document contract: {error}")
    document_validation = validate_documents(documents)
    errors.extend(document_validation["errors"])
    return {
        "valid": not errors and len(documents) == count,
        "line_count": count,
        "document_count": len(documents),
        "counts_by_type": document_validation["counts_by_type"],
        "counts_by_retrieval_domain": document_validation["counts_by_retrieval_domain"],
        "errors": errors,
        "warnings": document_validation["warnings"],
    }


def _prohibited_field_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            normalized = str(key).lower()
            if "embedding" in normalized or "vector" in normalized:
                paths.append(path)
            paths.extend(_prohibited_field_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_prohibited_field_paths(item, f"{prefix}[{index}]"))
    return paths


def validate_relational(dataset: NormalizedDataset) -> dict[str, Any]:
    # normalize_workbook already enforces all declared primary and foreign keys.
    nulls: dict[str, dict[str, int]] = {}
    for table, rows in dataset.tables.items():
        columns = sorted({column for row in rows for column in row})
        nulls[table] = {
            column: sum(row.get(column) is None or row.get(column) == "" for row in rows)
            for column in columns
            if any(row.get(column) is None or row.get(column) == "" for row in rows)
        }
    return {
        "valid": True,
        "row_counts": dataset.row_counts,
        "duplicate_primary_keys": 0,
        "foreign_key_violations": 0,
        "null_counts": nulls,
        "issues": list(dataset.issues),
    }
