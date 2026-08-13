from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.retail_data_bootstrap.chunking import chunk_document
from src.retail_data_bootstrap.documents import content_hash
from src.retail_data_bootstrap.embedding_config import (
    DEFAULT_QUERY_INSTRUCTION,
    EmbeddingConfig,
    EmbeddingProfileStatus,
    validate_profile_transition,
)
from src.retail_data_bootstrap.embedding_provider import (
    EmbeddingProvider,
    LocalBgeEmbeddingProvider,
)
from src.retail_data_bootstrap.models import SemanticDocument
from src.retail_data_bootstrap.vector_store import (
    calculate_sync_plan,
    inspect_ai_catalog,
    rank_parent_results,
    semantic_search,
    sync_vector_documents,
)


class FakeTokenizer:
    def __init__(self):
        self._word_to_id: dict[str, int] = {}
        self._id_to_word: dict[int, str] = {}
        self.calls: list[dict[str, object]] = []

    def _ids(self, text: str) -> list[int]:
        values = []
        for word in text.split():
            if word not in self._word_to_id:
                identifier = len(self._word_to_id) + 1000
                self._word_to_id[word] = identifier
                self._id_to_word[identifier] = word
            values.append(self._word_to_id[word])
        return values

    def __call__(self, text, **kwargs):
        self.calls.append(dict(kwargs))
        values = self._ids(text)
        if kwargs.get("add_special_tokens", True):
            values = [101, *values, 102]
        return {"input_ids": values}

    def encode(self, text, *, add_special_tokens, truncation, **kwargs):
        self.calls.append(
            {
                "add_special_tokens": add_special_tokens,
                "truncation": truncation,
            }
        )
        values = self._ids(text)
        return [101, *values, 102] if add_special_tokens else values

    def decode(self, token_ids, **kwargs):
        return " ".join(self._id_to_word[value] for value in token_ids)


class FakeModel:
    def __init__(self, dimensions=384):
        self.max_seq_length = 512
        self.tokenizer = FakeTokenizer()
        self.dimensions = dimensions
        self.encoded: list[object] = []

    def get_sentence_embedding_dimension(self):
        return self.dimensions

    def encode(self, texts, **kwargs):
        self.encoded.append(texts)
        count = len(texts) if isinstance(texts, list) else 1
        result = np.zeros((count, self.dimensions), dtype=np.float32)
        result[:, 0] = 1.0
        return result if isinstance(texts, list) else result[0]


class WhitespaceProvider(EmbeddingProvider):
    def __init__(self, config=None):
        super().__init__(config or EmbeddingConfig())
        self.tokenizer = FakeTokenizer()
        self.document_calls = 0
        self.query_calls = 0

    def count_tokens(self, text):
        return len(self.tokenizer._ids(text)) + 2

    def content_token_ids(self, text):
        return self.tokenizer._ids(text)

    def decode_content_tokens(self, token_ids):
        return self.tokenizer.decode(token_ids)

    @property
    def special_token_count(self):
        return 2

    def embed_documents(self, texts, *, batch_size=16):
        self.document_calls += 1
        result = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        result[:, 0] = 1.0
        return result

    def embed_query(self, text):
        self.query_calls += 1
        result = np.zeros(self.dimensions, dtype=np.float32)
        result[0] = 1.0
        return result


def _document(content: str, *, metadata=None) -> SemanticDocument:
    return SemanticDocument(
        doc_key="sku:test-1",
        doc_type="sku",
        retrieval_domain="business_entity",
        source_sheet="SKU_Master",
        source_key="TEST-1",
        content=content,
        metadata=metadata or {"source_row": 2},
        content_hash=content_hash(content),
    )


def _state(document=None, chunk=None, embedded_hash=None):
    documents = {}
    chunks = {}
    embeddings = {}
    if document:
        documents[document.doc_key] = {
            "document_id": 1,
            "doc_key": document.doc_key,
            "doc_type": document.doc_type,
            "retrieval_domain": document.retrieval_domain,
            "source_sheet": document.source_sheet,
            "source_key": document.source_key,
            "content": document.content,
            "metadata_json": json.dumps(document.metadata),
            "content_hash": document.content_hash,
            "is_active": True,
        }
    if chunk:
        chunks[chunk.chunk_key] = {
            "chunk_id": 1,
            "doc_key": chunk.doc_key,
            "chunk_index": chunk.chunk_index,
            "chunk_key": chunk.chunk_key,
            "content": chunk.content,
            "chunk_hash": chunk.chunk_hash,
            "token_count": chunk.token_count,
        }
        if embedded_hash is not None:
            embeddings[chunk.chunk_key] = embedded_hash
    return {
        "documents": documents,
        "chunks": chunks,
        "embeddings": embeddings,
        "profile": None,
    }


def test_embedding_configuration_and_profile_lifecycle(monkeypatch):
    monkeypatch.setenv("RETAIL_EMBEDDING_DIMENSIONS", "384")
    monkeypatch.setenv("RETAIL_EMBEDDING_NORMALIZE", "true")
    config = EmbeddingConfig.from_env()
    assert config.profile_key == "local-bge-small-en-v1.5-384-v1"
    assert config.chunk_target_tokens == 384
    assert json.loads(config.configuration_json())["chunker_version"].endswith("v1")
    validate_profile_transition("BUILDING", "ACTIVE")
    validate_profile_transition("ACTIVE", "RETIRED")
    with pytest.raises(ValueError, match="Invalid"):
        validate_profile_transition("RETIRED", "ACTIVE")
    with pytest.raises(ValueError, match="384"):
        replace(config, dimensions=1536)
    with pytest.raises(ValueError, match="CPU-only"):
        replace(config, device="cuda")


def test_local_provider_separates_document_and_query_encoding_and_normalizes():
    model = FakeModel()
    factory_calls = []

    def factory(*args, **kwargs):
        factory_calls.append((args, kwargs))
        return model

    provider = LocalBgeEmbeddingProvider(model_factory=factory)
    documents = provider.embed_documents(["plain document"])
    query = provider.embed_query("short query")
    assert model.encoded[0] == ["plain document"]
    assert model.encoded[1] == DEFAULT_QUERY_INSTRUCTION + "short query"
    assert not model.encoded[0][0].startswith(DEFAULT_QUERY_INSTRUCTION)
    assert documents.shape == (1, 384)
    assert query.shape == (384,)
    assert np.linalg.norm(documents[0]) == pytest.approx(1.0)
    assert np.linalg.norm(query) == pytest.approx(1.0)
    assert factory_calls[0][1]["device"] == "cpu"
    assert factory_calls[0][1]["local_files_only"] is True


def test_provider_enforces_dimensions_and_never_tokenizes_with_truncation():
    provider = LocalBgeEmbeddingProvider(model_factory=lambda *a, **k: FakeModel(12))
    with pytest.raises(RuntimeError, match="dimension mismatch"):
        provider.embed_documents(["document"])

    model = FakeModel()
    provider = LocalBgeEmbeddingProvider(model_factory=lambda *a, **k: model)
    assert provider.count_tokens("one two") == 4
    assert model.tokenizer.calls[-1]["truncation"] is False


def test_normal_document_is_one_full_chunk_even_above_target():
    provider = WhitespaceProvider()
    text = " ".join(f"w{i}" for i in range(400))
    chunks = chunk_document(_document(text), provider)
    assert len(chunks) == 1
    assert chunks[0].content == text
    assert chunks[0].token_count == 402


def test_oversized_chunking_is_deterministic_overlapping_and_safe():
    provider = WhitespaceProvider()
    text = " ".join(f"w{i}" for i in range(900))
    document = _document(text)
    first = chunk_document(document, provider)
    second = chunk_document(document, provider)
    assert len(first) > 1
    assert first == second
    assert all(chunk.token_count <= 512 for chunk in first)
    assert all(chunk.chunk_hash == content_hash(chunk.content) for chunk in first)
    assert [chunk.chunk_key for chunk in first] == [
        f"sku:test-1#{index:03d}" for index in range(len(first))
    ]
    first_ids = provider.content_token_ids(first[0].content)
    second_ids = provider.content_token_ids(first[1].content)
    assert first_ids[-48:] == second_ids[:48]


def test_sync_plan_inserts_new_documents_chunks_and_embeddings():
    provider = WhitespaceProvider()
    document = _document("stable semantic text")
    chunk = chunk_document(document, provider)[0]
    plan = calculate_sync_plan([document], [chunk], _state())
    assert plan.document_inserts == (document.doc_key,)
    assert plan.chunk_inserts == (chunk.chunk_key,)
    assert plan.embeddings_generated == 1
    assert plan.embeddings_required == 1


def test_metadata_only_change_reuses_embedding():
    provider = WhitespaceProvider()
    original = _document("stable semantic text")
    chunk = chunk_document(original, provider)[0]
    changed = replace(original, metadata={"source_row": 99})
    plan = calculate_sync_plan(
        [changed], [chunk], _state(original, chunk, chunk.chunk_hash)
    )
    assert plan.document_updates == (original.doc_key,)
    assert plan.chunk_noops == (chunk.chunk_key,)
    assert plan.embeddings_required == 0
    assert plan.embeddings_reused == 1


def test_changed_chunk_requires_update_and_new_profile_requires_all():
    provider = WhitespaceProvider()
    original = _document("old semantic text")
    old_chunk = chunk_document(original, provider)[0]
    changed = _document("new semantic meaning")
    new_chunk = chunk_document(changed, provider)[0]
    plan = calculate_sync_plan(
        [changed], [new_chunk], _state(original, old_chunk, old_chunk.chunk_hash)
    )
    assert plan.chunk_updates == (new_chunk.chunk_key,)
    assert plan.embeddings_updated == 1
    assert plan.embeddings_required == 1

    new_profile_state = _state(original, old_chunk, None)
    new_profile_plan = calculate_sync_plan(
        [original], [old_chunk], new_profile_state
    )
    assert new_profile_plan.embeddings_generated == 1
    assert new_profile_plan.embeddings_reused == 0


def test_unchanged_rerun_is_all_noop_and_reuse():
    provider = WhitespaceProvider()
    document = _document("stable semantic text")
    chunk = chunk_document(document, provider)[0]
    plan = calculate_sync_plan(
        [document], [chunk], _state(document, chunk, chunk.chunk_hash)
    )
    assert plan.document_noops == (document.doc_key,)
    assert plan.chunk_noops == (chunk.chunk_key,)
    assert plan.embeddings_required == 0
    assert plan.embeddings_reused == 1


def test_sync_plan_inactivates_missing_documents_and_removes_stale_chunk_set():
    provider = WhitespaceProvider()
    document = _document("stable semantic text")
    chunk = chunk_document(document, provider)[0]
    stale_key = f"{document.doc_key}#001"
    state = _state(document, chunk, chunk.chunk_hash)
    state["chunks"][stale_key] = {
        "chunk_id": 2,
        "doc_key": document.doc_key,
        "chunk_index": 1,
        "chunk_key": stale_key,
        "content": "stale chunk",
        "chunk_hash": content_hash("stale chunk"),
        "token_count": 4,
    }
    plan = calculate_sync_plan([document], [chunk], state)
    assert plan.chunk_removals == (stale_key,)

    missing_plan = calculate_sync_plan([], [], state)
    assert missing_plan.document_inactivations == (document.doc_key,)
    # Missing-source documents are retained with their derived children until prune.
    assert missing_plan.chunk_removals == ()


def test_dry_run_never_applies_database_writes(tmp_path, monkeypatch):
    document = _document("stable semantic text")
    source = tmp_path / "documents.jsonl"
    source.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
    )

    class Connection:
        def close(self):
            pass

    monkeypatch.setattr(
        "src.retail_data_bootstrap.vector_store.inspect_ai_catalog",
        lambda connection: {"schema_exists": True, "tables": {}},
    )
    monkeypatch.setattr(
        "src.retail_data_bootstrap.vector_store.validate_ai_catalog",
        lambda catalog, require_all: None,
    )
    monkeypatch.setattr(
        "src.retail_data_bootstrap.vector_store._load_sync_state",
        lambda connection, profile_key: _state(),
    )

    def fail_apply(*args, **kwargs):
        raise AssertionError("dry run attempted database writes")

    monkeypatch.setattr(
        "src.retail_data_bootstrap.vector_store._apply_sync_plan", fail_apply
    )
    result = sync_vector_documents(
        source,
        WhitespaceProvider(),
        EmbeddingConfig(),
        dry_run=True,
        connection=Connection(),
    )
    assert result["dry_run"] is True
    assert result["documents"]["inserts"] == 1


def test_parent_deduplication_and_search_ordering():
    candidates = [
        {"doc_key": "a", "cosine_distance": 0.3},
        {"doc_key": "a", "cosine_distance": 0.1},
        {"doc_key": "b", "cosine_distance": 0.2},
    ]
    results = rank_parent_results(candidates, 5)
    assert [result["doc_key"] for result in results] == ["a", "b"]
    assert results[0]["cosine_distance"] == 0.1
    assert results[0]["cosine_similarity"] == 0.9


class SearchCursor:
    def __init__(self, config):
        self.config = config
        self.rows = []
        self.search_sql = ""
        self.search_params = ()

    def execute(self, sql, params=()):
        if "WHERE status = N'ACTIVE'" in sql or "WHERE profile_key = ?" in sql:
            self.rows = [
                (
                    7,
                    self.config.profile_key,
                    self.config.provider_key,
                    self.config.model_name,
                    self.config.model_revision,
                    self.config.dimensions,
                    1,
                    self.config.max_sequence_length,
                    self.config.document_instruction,
                    self.config.query_instruction,
                    self.config.chunk_target_tokens,
                    self.config.chunk_overlap_tokens,
                    self.config.configuration_json(),
                    "ACTIVE",
                    None,
                    None,
                    None,
                )
            ]
        elif "SELECT TOP" in sql:
            self.search_sql = sql
            self.search_params = params
            self.rows = [
                (0.1, "sku:a", "sku", "business_entity", "A", 0, "sku:a#000", "a"),
                (0.2, "sku:a", "sku", "business_entity", "A", 1, "sku:a#001", "a2"),
                (0.3, "sku:b", "sku", "business_entity", "B", 0, "sku:b#000", "b"),
            ]
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class SearchConnection:
    def __init__(self, config):
        self.search_cursor = SearchCursor(config)

    def cursor(self):
        return self.search_cursor

    def close(self):
        pass


def test_search_applies_domain_type_profile_isolation_and_parent_deduplication():
    config = EmbeddingConfig()
    provider = WhitespaceProvider(config)
    connection = SearchConnection(config)
    result = semantic_search(
        "fruit",
        provider,
        config,
        top_k=5,
        retrieval_domain="business_entity",
        doc_type="sku",
        connection=connection,
    )
    sql = connection.search_cursor.search_sql
    params = connection.search_cursor.search_params
    assert "e.embedding_profile_id = ?" in sql
    assert "d.retrieval_domain = ?" in sql
    assert "d.doc_type = ?" in sql
    assert params[1:] == (7, "business_entity", "sku")
    assert [item["doc_key"] for item in result["results"]] == ["sku:a", "sku:b"]
    assert result["metric"] == "cosine_distance"


def test_search_filter_validation_happens_before_database_access():
    provider = WhitespaceProvider()
    with pytest.raises(ValueError, match="Unknown retrieval"):
        semantic_search("query", provider, provider.config, retrieval_domain="wrong")
    with pytest.raises(ValueError, match="belongs"):
        semantic_search(
            "query",
            provider,
            provider.config,
            retrieval_domain="integration",
            doc_type="sku",
        )


@pytest.mark.local_embedding
def test_real_local_bge_provider_when_explicitly_enabled():
    if os.getenv("RUN_LOCAL_EMBEDDING_INTEGRATION") != "1":
        pytest.skip("Set RUN_LOCAL_EMBEDDING_INTEGRATION=1 to load the real BGE model")
    provider = LocalBgeEmbeddingProvider()
    documents = provider.embed_documents(["A perishable fruit product."])
    query = provider.embed_query("Which product is fruit?")
    assert documents.shape == (1, 384)
    assert query.shape == (384,)
    assert float(documents[0] @ query) > 0


@pytest.mark.azure_sql
def test_live_ai_catalog_when_explicitly_enabled():
    if os.getenv("RUN_AZURE_SQL_INTEGRATION") != "1":
        pytest.skip("Set RUN_AZURE_SQL_INTEGRATION=1 to run the live Azure SQL test")
    catalog = inspect_ai_catalog()
    assert set(catalog["tables"]) == {
        "EmbeddingProfile",
        "RetailDocument",
        "RetailChunk",
        "RetailEmbedding",
    }
