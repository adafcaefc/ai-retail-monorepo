from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from functools import lru_cache

import pytest

from src.retail_data_bootstrap.classification import (
    SHEET_SPECS,
    classification_counts,
    validate_sheet_specs,
)
from src.retail_data_bootstrap.database import ingest_structured, inspect_catalog
from src.retail_data_bootstrap.documents import (
    build_documents,
    content_hash,
    document_key,
    representative_sample,
    write_jsonl,
)
from src.retail_data_bootstrap.models import SemanticDocument
from src.retail_data_bootstrap.normalization import normalize_workbook
from src.retail_data_bootstrap.paths import (
    load_azure_sql_connection_string,
    resolve_workbook_path,
)
from src.retail_data_bootstrap.source import ExcelSourceAdapter, normalize_column_name
from src.retail_data_bootstrap.semantic_contract import (
    DOC_TYPE_RETRIEVAL_DOMAIN,
    RETRIEVAL_DOMAINS,
    VOLATILE_MODEL_PARAMETERS,
    retrieval_domain_for,
)
from src.retail_data_bootstrap.validation import validate_documents, validate_jsonl


EXPECTED_DOCUMENT_COUNTS = {
    "agent_spec": 9,
    "approval_rule": 4,
    "brand": 12,
    "brand_event": 23,
    "category": 160,
    "d365_field_mapping": 29,
    "d365_table": 33,
    "d365_worked_example": 1,
    "data_source": 10,
    "formula": 19,
    "model_parameter": 12,
    "promotion": 48,
    "sku": 800,
    "store": 160,
    "terminology": 13,
    "vendor": 8,
    "vertical": 8,
    "workbook_overview": 1,
}

EXPECTED_SAMPLE_KEYS = {
    "sku:dgt-001",
    "sku:elc-001",
    "sku:fsh-001",
    "sku:gmr-001",
    "sku:grc-001",
    "vendor:v0001",
    "brand:altura",
    "formula:ads-per-store",
    "terminology:ads",
    "d365-field-mapping:a1-demand-forecasting-per-vertical-aggregated-from-engine-store-forecastsales",
}


@lru_cache(maxsize=1)
def _dataset():
    return normalize_workbook(resolve_workbook_path())


@lru_cache(maxsize=1)
def _documents():
    return build_documents(resolve_workbook_path())


def test_workbook_loading_and_every_sheet_is_classified():
    names = ExcelSourceAdapter(resolve_workbook_path()).sheet_names()
    assert len(names) == 49
    assert set(names) == set(SHEET_SPECS)
    validate_sheet_specs(names)
    assert sum(classification_counts().values()) == 49


def test_sheet_classification_is_strict():
    with pytest.raises(ValueError, match="missing"):
        validate_sheet_specs([name for name in SHEET_SPECS if name != "Stores"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SKU ID", "sku_id"),
        ("Σ store size", "store_size"),
        ("Margin %", "margin"),
        ("123 value", "column_123_value"),
    ],
)
def test_column_key_normalization(raw, expected):
    assert normalize_column_name(raw) == expected


def test_normalized_keys_and_joins_are_validated():
    dataset = _dataset()
    assert dataset.row_counts["Sku"] == 800
    assert dataset.row_counts["StoreSkuSnapshot"] == 16000
    category_ids = {row["category_id"] for row in dataset.tables["Category"]}
    vendor_ids = {row["vendor_account"] for row in dataset.tables["Vendor"]}
    assert all(row["category_id"] in category_ids for row in dataset.tables["Sku"])
    assert all(row["vendor_account"] in vendor_ids for row in dataset.tables["Sku"])
    assert "aggregate TOTAL row" in dataset.issues[0]
    assert isinstance(dataset.tables["TradeAgreement"][0]["valid_from"], date)
    assert isinstance(dataset.tables["Promotion"][0]["valid_to"], date)


def test_document_key_and_hash_are_deterministic():
    assert document_key("SKU", "GRC-001") == "sku:grc-001"
    assert content_hash("same content\n") == content_hash("same content")
    assert content_hash("same content") != content_hash("different content")


def test_retrieval_domain_contract_covers_every_document_type():
    assert set(DOC_TYPE_RETRIEVAL_DOMAIN) == set(EXPECTED_DOCUMENT_COUNTS)
    assert set(DOC_TYPE_RETRIEVAL_DOMAIN.values()) == RETRIEVAL_DOMAINS
    for document in _documents():
        assert document.retrieval_domain == retrieval_domain_for(document.doc_type)
        assert "retrieval_domain" not in document.metadata


def test_semantic_content_joins_verified_sources():
    sku = next(document for document in _documents() if document.doc_key == "sku:grc-001")
    assert "SKU GRC-001 is Fruit 1" in sku.content
    assert "Aurora" not in sku.content  # GRC-001 is designated to Vendor E, not Vendor A.
    assert "Everest Wholesale" in sku.content
    assert sku.metadata["category_id"] == "GRC-C01"
    assert "ENGINE_STORE" not in sku.metadata["source_sheets"]
    assert "ENGINE" not in sku.metadata["source_sheets"]
    assert "inventory_state" not in sku.metadata


def test_stable_business_characteristics_remain_in_entity_content():
    documents = {document.doc_key: document for document in _documents()}
    sku = documents["sku:grc-001"].content
    assert "Fruit 1" in sku
    assert "perishable" in sku
    assert "Brava" in sku
    assert "Everest Wholesale" in sku
    assert "sells in Bottle" in sku
    assert "bought in Crate with pack factor 12" in sku
    assert "lead time is 2 days" in sku
    assert "designated supplier agreement" in sku
    vendor = documents["vendor:v0001"].content
    assert "Net 30" in vendor
    assert "FOB" in vendor
    assert "MOQ 78 units" in vendor


def test_volatile_operational_values_are_excluded_from_entity_content():
    documents = {document.doc_key: document for document in _documents()}
    sku = documents["sku:grc-001"]
    for text in (
        "Current chain inventory state",
        "position 1176",
        "reorder point 1491",
        "proposed order units 2302",
        "14300 IDR per sales unit",
    ):
        assert text not in sku.content
    store = documents["store:s001"].content
    for text in ("1.2236", "1.0061", "1.1221", "37 FTE", "38 required FTE"):
        assert text not in store
    vendor = documents["vendor:v0001"].content
    for text in ("OTIF", "97.4%", "fill", "defect", "lead adherence", "116 SKUs"):
        assert text not in vendor
    assert "67 SKUs" not in documents["brand:altura"].content
    assert "assigns 5 SKUs" not in documents["category:dgt-c01"].content
    assert "expected uplift" not in documents["promotion:prm-0001"].content
    assert "44%" not in documents["promotion:prm-0001"].content
    assert "demand-lift" not in documents["brand-event:s004-season-launch"].content
    assert "25%" not in documents["brand-event:s004-season-launch"].content
    vertical = documents["vertical:dgt"].content
    for text in ("peak-season factor", "workforce base", "sales per FTE", "1.55", "11000000"):
        assert text not in vertical


def test_adjustable_model_parameter_values_are_not_embedded_or_metadata():
    parameter_documents = {
        document.source_key: document
        for document in _documents()
        if document.doc_type == "model_parameter"
    }
    assert VOLATILE_MODEL_PARAMETERS <= set(parameter_documents)
    for parameter in VOLATILE_MODEL_PARAMETERS:
        document = parameter_documents[parameter]
        assert " has value " not in document.content
        assert "value" not in document.metadata
    fixed = parameter_documents["Full-time h/wk"]
    assert "configured value 40" in fixed.content
    assert fixed.metadata["value"] == 40


def test_content_hash_is_independent_of_metadata_and_changes_with_content():
    original = next(document for document in _documents() if document.doc_key == "sku:grc-001")
    metadata_only_change = replace(
        original,
        metadata={**original.metadata, "operational_note": "changed outside semantic content"},
    )
    assert metadata_only_change.content_hash == original.content_hash
    assert content_hash(metadata_only_change.content) == original.content_hash

    changed_content = original.content + " Semantic meaning changed."
    assert content_hash(changed_content) != original.content_hash


def test_document_generation_is_fully_deterministic():
    regenerated = build_documents(resolve_workbook_path())
    assert [document.to_dict() for document in regenerated] == [
        document.to_dict() for document in _documents()
    ]


def test_representative_sample_has_ten_documents_and_five_verticals():
    sample = representative_sample(_documents())
    assert len(sample) == 10
    assert {document.doc_key for document in sample} == EXPECTED_SAMPLE_KEYS
    sku_entities = {
        document.metadata["legal_entity_id"]
        for document in sample
        if document.doc_type == "sku"
    }
    assert len(sku_entities) == 5
    assert validate_documents(sample)["valid"] is True


def test_full_corpus_count_and_validation_reconcile():
    result = validate_documents(_documents())
    assert result["valid"] is True
    assert result["document_count"] == 1350
    assert result["counts_by_type"] == EXPECTED_DOCUMENT_COUNTS
    assert sum(result["counts_by_retrieval_domain"].values()) == 1350


def test_duplicate_documents_are_rejected():
    first = _documents()[0]
    duplicate = SemanticDocument(
        doc_key=first.doc_key,
        doc_type=first.doc_type,
        retrieval_domain=first.retrieval_domain,
        source_sheet=first.source_sheet,
        source_key=first.source_key,
        content=first.content,
        metadata=first.metadata,
        content_hash=first.content_hash,
    )
    result = validate_documents([first, duplicate])
    assert result["valid"] is False
    assert any("duplicate doc_key" in error for error in result["errors"])


def test_metadata_is_json_serializable():
    for document in _documents():
        json.dumps(document.metadata, ensure_ascii=False, allow_nan=False, sort_keys=True)


def test_jsonl_contract_has_no_embedding_or_vector_fields(tmp_path):
    output = tmp_path / "documents.jsonl"
    write_jsonl(_documents(), output)
    result = validate_jsonl(output)
    assert result["valid"] is True
    assert result["line_count"] == 1350
    for line in output.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        assert "retrieval_domain" in value
        serialized_keys = json.dumps(list(value), ensure_ascii=False).lower()
        assert "embedding" not in serialized_keys
        assert "vector" not in serialized_keys


def test_validator_rejects_wrong_domain_and_known_operational_leakage():
    sku = next(document for document in _documents() if document.doc_key == "sku:grc-001")
    wrong_domain = replace(sku, retrieval_domain="integration")
    wrong_result = validate_documents([wrong_domain])
    assert wrong_result["valid"] is False
    assert any("deterministic doc_type mapping" in error for error in wrong_result["errors"])

    leaked_content = sku.content + " Current chain inventory state is Low."
    leaked = replace(sku, content=leaked_content, content_hash=content_hash(leaked_content))
    leaked_result = validate_documents([leaked])
    assert leaked_result["valid"] is False
    assert any("operational leakage" in error for error in leaked_result["errors"])


def test_connection_configuration_loads_without_exposing_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_SQL_CONNECTIONSTRING", raising=False)
    env_file = tmp_path / ".env"
    value = "test-only-connection-configuration"
    env_file.write_text(f"AZURE_SQL_CONNECTIONSTRING={value}\n", encoding="utf-8")
    loaded = load_azure_sql_connection_string(env_file)
    assert loaded == value
    with pytest.raises(RuntimeError) as error:
        monkeypatch.delenv("AZURE_SQL_CONNECTIONSTRING", raising=False)
        load_azure_sql_connection_string(tmp_path / "missing.env")
    assert value not in str(error.value)


def test_dry_run_never_opens_a_database_connection(monkeypatch):
    def fail_connection():
        raise AssertionError("dry-run attempted a live connection")

    monkeypatch.setattr("src.retail_data_bootstrap.database.open_connection", fail_connection)
    result = ingest_structured(_dataset(), dry_run=True)
    assert result["dry_run"] is True
    assert result["database_row_counts"] is None


@pytest.mark.azure_sql
def test_live_azure_sql_catalog_when_explicitly_enabled(monkeypatch):
    import os

    if os.getenv("RUN_AZURE_SQL_INTEGRATION") != "1":
        pytest.skip("Set RUN_AZURE_SQL_INTEGRATION=1 to run the live Azure SQL test")
    catalog = inspect_catalog()
    assert "tables" in catalog
