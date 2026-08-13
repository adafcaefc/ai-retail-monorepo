from __future__ import annotations

import json
import math
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .chunking import SemanticChunk, chunk_documents, chunk_statistics
from .database import open_connection
from .documents import canonical_content, content_hash
from .embedding_config import (
    FROZEN_CORPUS_DOCUMENT_COUNT,
    EmbeddingConfig,
    EmbeddingProfileStatus,
    validate_profile_transition,
)
from .embedding_provider import EmbeddingProvider
from .models import SemanticDocument
from .semantic_contract import DOC_TYPE_RETRIEVAL_DOMAIN, RETRIEVAL_DOMAINS
from .validation import validate_jsonl


AI_TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "EmbeddingProfile": frozenset(
        {
            "embedding_profile_id",
            "profile_key",
            "provider",
            "model_name",
            "model_revision",
            "dimensions",
            "normalization",
            "max_sequence_length",
            "document_instruction",
            "query_instruction",
            "chunk_target_tokens",
            "chunk_overlap_tokens",
            "configuration_json",
            "status",
            "created_at",
            "activated_at",
            "retired_at",
        }
    ),
    "RetailDocument": frozenset(
        {
            "document_id",
            "doc_key",
            "doc_type",
            "retrieval_domain",
            "source_sheet",
            "source_key",
            "content",
            "metadata_json",
            "content_hash",
            "is_active",
            "created_at",
            "updated_at",
        }
    ),
    "RetailChunk": frozenset(
        {
            "chunk_id",
            "document_id",
            "chunk_index",
            "chunk_key",
            "content",
            "chunk_hash",
            "token_count",
            "created_at",
            "updated_at",
        }
    ),
    "RetailEmbedding": frozenset(
        {
            "embedding_profile_id",
            "chunk_id",
            "embedding",
            "embedded_chunk_hash",
            "embedded_at",
        }
    ),
}


@dataclass(frozen=True)
class SyncPlan:
    document_inserts: tuple[str, ...]
    document_updates: tuple[str, ...]
    document_noops: tuple[str, ...]
    document_inactivations: tuple[str, ...]
    chunk_inserts: tuple[str, ...]
    chunk_updates: tuple[str, ...]
    chunk_noops: tuple[str, ...]
    chunk_removals: tuple[str, ...]
    embeddings_required: int
    embeddings_generated: int
    embeddings_updated: int
    embeddings_reused: int

    def summary(self) -> dict[str, Any]:
        return {
            "documents": {
                "inserts": len(self.document_inserts),
                "updates": len(self.document_updates),
                "noops": len(self.document_noops),
                "inactivations": len(self.document_inactivations),
            },
            "chunks": {
                "inserts": len(self.chunk_inserts),
                "updates": len(self.chunk_updates),
                "noops": len(self.chunk_noops),
                "removals": len(self.chunk_removals),
            },
            "expected_embedding_work": {
                "required": self.embeddings_required,
                "generated": self.embeddings_generated,
                "updated": self.embeddings_updated,
                "reused": self.embeddings_reused,
            },
        }


def _canonical_metadata(value: dict[str, Any] | str) -> str:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("Semantic document metadata must be a JSON object")
    return json.dumps(
        parsed, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def load_semantic_documents(path: Path) -> list[SemanticDocument]:
    validation = validate_jsonl(path)
    if not validation["valid"]:
        raise ValueError(
            "Frozen semantic JSONL failed validation: "
            + "; ".join(validation["errors"][:10])
        )
    documents: list[SemanticDocument] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            value = json.loads(line)
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
    return documents


def inspect_ai_catalog(connection=None) -> dict[str, Any]:
    owned = connection is None
    connection = connection or open_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT t.name, c.name, ty.name, c.max_length, c.is_nullable, c.column_id
            FROM sys.tables AS t
            JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            JOIN sys.columns AS c ON c.object_id = t.object_id
            JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
            WHERE s.name = N'ai'
            ORDER BY t.name, c.column_id;
            """
        )
        tables: dict[str, list[dict[str, Any]]] = {}
        for row in cursor.fetchall():
            tables.setdefault(str(row[0]), []).append(
                {
                    "name": str(row[1]),
                    "type": str(row[2]),
                    "max_length": int(row[3]),
                    "nullable": bool(row[4]),
                }
            )
        cursor.execute(
            "SELECT CASE WHEN SCHEMA_ID(N'ai') IS NULL THEN 0 ELSE 1 END;"
        )
        return {"schema_exists": bool(cursor.fetchone()[0]), "tables": tables}
    finally:
        if owned:
            connection.close()


def validate_ai_catalog(catalog: dict[str, Any], *, require_all: bool) -> None:
    conflicts: list[str] = []
    for table, columns in catalog["tables"].items():
        if table not in AI_TABLE_COLUMNS:
            continue
        actual = {column["name"] for column in columns}
        expected = AI_TABLE_COLUMNS[table]
        if actual != expected:
            conflicts.append(
                f"ai.{table}: expected columns {sorted(expected)}, found {sorted(actual)}"
            )
        if table == "RetailEmbedding":
            vector_column = next(
                (column for column in columns if column["name"] == "embedding"), None
            )
            if not vector_column or vector_column["type"].lower() != "vector":
                conflicts.append("ai.RetailEmbedding.embedding is not a native VECTOR")
    if require_all:
        missing = sorted(set(AI_TABLE_COLUMNS) - set(catalog["tables"]))
        if missing:
            conflicts.append(f"missing expected ai tables: {missing}")
    if conflicts:
        raise RuntimeError(
            "Existing Azure SQL ai objects conflict with Phase 5; no changes were made:\n"
            + "\n".join(conflicts)
        )


def apply_ai_migration(path: Path) -> dict[str, Any]:
    connection = open_connection()
    try:
        before = inspect_ai_catalog(connection)
        validate_ai_catalog(before, require_all=False)
        batches = [
            batch.strip()
            for batch in re.split(
                r"^\s*GO\s*$",
                path.read_text(encoding="utf-8"),
                flags=re.IGNORECASE | re.MULTILINE,
            )
            if batch.strip()
        ]
        cursor = connection.cursor()
        try:
            for batch in batches:
                cursor.execute(batch)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        after = inspect_ai_catalog(connection)
        validate_ai_catalog(after, require_all=True)
        return {"before": before, "after": after, "batch_count": len(batches)}
    finally:
        connection.close()


def _profile_row(cursor, profile_key: str) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT embedding_profile_id, profile_key, provider, model_name,
               model_revision, dimensions, normalization, max_sequence_length,
               document_instruction, query_instruction, chunk_target_tokens,
               chunk_overlap_tokens, configuration_json, status, created_at,
               activated_at, retired_at
        FROM ai.EmbeddingProfile
        WHERE profile_key = ?;
        """,
        (profile_key,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    names = (
        "embedding_profile_id",
        "profile_key",
        "provider",
        "model_name",
        "model_revision",
        "dimensions",
        "normalization",
        "max_sequence_length",
        "document_instruction",
        "query_instruction",
        "chunk_target_tokens",
        "chunk_overlap_tokens",
        "configuration_json",
        "status",
        "created_at",
        "activated_at",
        "retired_at",
    )
    result = dict(zip(names, row))
    result["embedding_profile_id"] = int(result["embedding_profile_id"])
    result["dimensions"] = int(result["dimensions"])
    result["normalization"] = bool(result["normalization"])
    result["max_sequence_length"] = int(result["max_sequence_length"])
    result["chunk_target_tokens"] = int(result["chunk_target_tokens"])
    result["chunk_overlap_tokens"] = int(result["chunk_overlap_tokens"])
    return result


def _profile_expected(config: EmbeddingConfig) -> dict[str, Any]:
    return {
        "profile_key": config.profile_key,
        "provider": config.provider_key,
        "model_name": config.model_name,
        "model_revision": config.model_revision,
        "dimensions": config.dimensions,
        "normalization": config.normalize,
        "max_sequence_length": config.max_sequence_length,
        "document_instruction": config.document_instruction,
        "query_instruction": config.query_instruction,
        "chunk_target_tokens": config.chunk_target_tokens,
        "chunk_overlap_tokens": config.chunk_overlap_tokens,
        "configuration_json": config.configuration_json(),
    }


def assert_profile_matches(profile: dict[str, Any], config: EmbeddingConfig) -> None:
    expected = _profile_expected(config)
    mismatches: dict[str, dict[str, Any]] = {}
    for name, value in expected.items():
        actual = profile.get(name)
        if name == "configuration_json":
            actual = json.dumps(
                json.loads(actual), sort_keys=True, separators=(",", ":")
            )
        if actual != value:
            mismatches[name] = {"expected": value, "actual": actual}
    if mismatches:
        raise RuntimeError(
            f"Embedding profile {config.profile_key!r} does not match configured provider: "
            f"{mismatches}"
        )


def register_embedding_profile(
    config: EmbeddingConfig, *, connection=None
) -> dict[str, Any]:
    owned = connection is None
    connection = connection or open_connection()
    try:
        validate_ai_catalog(inspect_ai_catalog(connection), require_all=True)
        cursor = connection.cursor()
        existing = _profile_row(cursor, config.profile_key)
        if existing:
            assert_profile_matches(existing, config)
            return {"created": False, "profile": existing}
        expected = _profile_expected(config)
        cursor.execute(
            """
            INSERT INTO ai.EmbeddingProfile (
                profile_key, provider, model_name, model_revision, dimensions,
                normalization, max_sequence_length, document_instruction,
                query_instruction, chunk_target_tokens, chunk_overlap_tokens,
                configuration_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, N'BUILDING');
            """,
            (
                expected["profile_key"],
                expected["provider"],
                expected["model_name"],
                expected["model_revision"],
                expected["dimensions"],
                int(expected["normalization"]),
                expected["max_sequence_length"],
                expected["document_instruction"],
                expected["query_instruction"],
                expected["chunk_target_tokens"],
                expected["chunk_overlap_tokens"],
                expected["configuration_json"],
            ),
        )
        connection.commit()
        created = _profile_row(connection.cursor(), config.profile_key)
        return {"created": True, "profile": created}
    except Exception:
        if owned:
            connection.rollback()
        raise
    finally:
        if owned:
            connection.close()


def _load_sync_state(connection, profile_key: str) -> dict[str, Any]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT document_id, doc_key, doc_type, retrieval_domain, source_sheet,
               source_key, content, metadata_json, content_hash, is_active
        FROM ai.RetailDocument;
        """
    )
    documents: dict[str, dict[str, Any]] = {}
    for row in cursor.fetchall():
        documents[str(row[1])] = {
            "document_id": int(row[0]),
            "doc_key": str(row[1]),
            "doc_type": str(row[2]),
            "retrieval_domain": str(row[3]),
            "source_sheet": str(row[4]),
            "source_key": str(row[5]),
            "content": str(row[6]),
            "metadata_json": str(row[7]),
            "content_hash": str(row[8]),
            "is_active": bool(row[9]),
        }
    cursor.execute(
        """
        SELECT c.chunk_id, d.doc_key, c.chunk_index, c.chunk_key, c.content,
               c.chunk_hash, c.token_count
        FROM ai.RetailChunk AS c
        JOIN ai.RetailDocument AS d ON d.document_id = c.document_id;
        """
    )
    chunks: dict[str, dict[str, Any]] = {}
    for row in cursor.fetchall():
        chunks[str(row[3])] = {
            "chunk_id": int(row[0]),
            "doc_key": str(row[1]),
            "chunk_index": int(row[2]),
            "chunk_key": str(row[3]),
            "content": str(row[4]),
            "chunk_hash": str(row[5]),
            "token_count": int(row[6]),
        }
    profile = _profile_row(cursor, profile_key)
    embeddings: dict[str, str] = {}
    if profile:
        cursor.execute(
            """
            SELECT c.chunk_key, e.embedded_chunk_hash
            FROM ai.RetailEmbedding AS e
            JOIN ai.RetailChunk AS c ON c.chunk_id = e.chunk_id
            WHERE e.embedding_profile_id = ?;
            """,
            (profile["embedding_profile_id"],),
        )
        embeddings = {str(row[0]): str(row[1]) for row in cursor.fetchall()}
    return {
        "documents": documents,
        "chunks": chunks,
        "embeddings": embeddings,
        "profile": profile,
    }


def _document_signature(document: SemanticDocument) -> tuple[Any, ...]:
    return (
        document.doc_type,
        document.retrieval_domain,
        document.source_sheet,
        document.source_key,
        document.content,
        _canonical_metadata(document.metadata),
        document.content_hash,
        True,
    )


def _stored_document_signature(document: dict[str, Any]) -> tuple[Any, ...]:
    return (
        document["doc_type"],
        document["retrieval_domain"],
        document["source_sheet"],
        document["source_key"],
        document["content"],
        _canonical_metadata(document["metadata_json"]),
        document["content_hash"],
        document["is_active"],
    )


def calculate_sync_plan(
    documents: Sequence[SemanticDocument],
    chunks: Sequence[SemanticChunk],
    state: dict[str, Any],
) -> SyncPlan:
    existing_documents = state["documents"]
    existing_chunks = state["chunks"]
    existing_embeddings = state["embeddings"]
    incoming_documents = {document.doc_key: document for document in documents}
    incoming_chunks = {chunk.chunk_key: chunk for chunk in chunks}

    document_inserts: list[str] = []
    document_updates: list[str] = []
    document_noops: list[str] = []
    for key, document in incoming_documents.items():
        existing = existing_documents.get(key)
        if not existing:
            document_inserts.append(key)
        elif _document_signature(document) != _stored_document_signature(existing):
            document_updates.append(key)
        else:
            document_noops.append(key)
    document_inactivations = sorted(
        key
        for key, document in existing_documents.items()
        if document["is_active"] and key not in incoming_documents
    )

    chunk_inserts: list[str] = []
    chunk_updates: list[str] = []
    chunk_noops: list[str] = []
    for key, chunk in incoming_chunks.items():
        existing = existing_chunks.get(key)
        if not existing:
            chunk_inserts.append(key)
        else:
            current = (
                existing["doc_key"],
                existing["chunk_index"],
                existing["content"],
                existing["chunk_hash"],
                existing["token_count"],
            )
            proposed = (
                chunk.doc_key,
                chunk.chunk_index,
                chunk.content,
                chunk.chunk_hash,
                chunk.token_count,
            )
            (chunk_noops if current == proposed else chunk_updates).append(key)
    incoming_doc_keys = set(incoming_documents)
    chunk_removals = sorted(
        key
        for key, chunk in existing_chunks.items()
        if chunk["doc_key"] in incoming_doc_keys and key not in incoming_chunks
    )

    generated = 0
    updated = 0
    reused = 0
    for key, chunk in incoming_chunks.items():
        embedded_hash = existing_embeddings.get(key)
        if embedded_hash is None:
            generated += 1
        elif embedded_hash != chunk.chunk_hash:
            updated += 1
        else:
            reused += 1
    return SyncPlan(
        document_inserts=tuple(sorted(document_inserts)),
        document_updates=tuple(sorted(document_updates)),
        document_noops=tuple(sorted(document_noops)),
        document_inactivations=tuple(document_inactivations),
        chunk_inserts=tuple(sorted(chunk_inserts)),
        chunk_updates=tuple(sorted(chunk_updates)),
        chunk_noops=tuple(sorted(chunk_noops)),
        chunk_removals=tuple(chunk_removals),
        embeddings_required=generated + updated,
        embeddings_generated=generated,
        embeddings_updated=updated,
        embeddings_reused=reused,
    )


def _apply_sync_plan(
    connection,
    documents: Sequence[SemanticDocument],
    chunks: Sequence[SemanticChunk],
    plan: SyncPlan,
) -> None:
    document_map = {document.doc_key: document for document in documents}
    chunk_map = {chunk.chunk_key: chunk for chunk in chunks}
    cursor = connection.cursor()
    try:
        for key in plan.document_inserts:
            document = document_map[key]
            cursor.execute(
                """
                INSERT INTO ai.RetailDocument (
                    doc_key, doc_type, retrieval_domain, source_sheet, source_key,
                    content, metadata_json, content_hash, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
                """,
                (
                    document.doc_key,
                    document.doc_type,
                    document.retrieval_domain,
                    document.source_sheet,
                    document.source_key,
                    document.content,
                    _canonical_metadata(document.metadata),
                    document.content_hash,
                ),
            )
        for key in plan.document_updates:
            document = document_map[key]
            cursor.execute(
                """
                UPDATE ai.RetailDocument
                SET doc_type = ?, retrieval_domain = ?, source_sheet = ?,
                    source_key = ?, content = ?, metadata_json = ?, content_hash = ?,
                    is_active = 1, updated_at = SYSUTCDATETIME()
                WHERE doc_key = ?;
                """,
                (
                    document.doc_type,
                    document.retrieval_domain,
                    document.source_sheet,
                    document.source_key,
                    document.content,
                    _canonical_metadata(document.metadata),
                    document.content_hash,
                    document.doc_key,
                ),
            )
        for key in plan.document_inactivations:
            cursor.execute(
                """
                UPDATE ai.RetailDocument
                SET is_active = 0, updated_at = SYSUTCDATETIME()
                WHERE doc_key = ? AND is_active = 1;
                """,
                (key,),
            )

        cursor.execute(
            "SELECT document_id, doc_key FROM ai.RetailDocument WHERE is_active = 1;"
        )
        document_ids = {str(row[1]): int(row[0]) for row in cursor.fetchall()}
        for key in plan.chunk_inserts:
            chunk = chunk_map[key]
            cursor.execute(
                """
                INSERT INTO ai.RetailChunk (
                    document_id, chunk_index, chunk_key, content, chunk_hash, token_count
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    document_ids[chunk.doc_key],
                    chunk.chunk_index,
                    chunk.chunk_key,
                    chunk.content,
                    chunk.chunk_hash,
                    chunk.token_count,
                ),
            )
        for key in plan.chunk_updates:
            chunk = chunk_map[key]
            cursor.execute(
                """
                UPDATE ai.RetailChunk
                SET document_id = ?, chunk_index = ?, content = ?, chunk_hash = ?,
                    token_count = ?, updated_at = SYSUTCDATETIME()
                WHERE chunk_key = ?;
                """,
                (
                    document_ids[chunk.doc_key],
                    chunk.chunk_index,
                    chunk.content,
                    chunk.chunk_hash,
                    chunk.token_count,
                    chunk.chunk_key,
                ),
            )
        for key in plan.chunk_removals:
            cursor.execute("DELETE FROM ai.RetailChunk WHERE chunk_key = ?;", (key,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def sync_vector_documents(
    path: Path,
    provider: EmbeddingProvider,
    config: EmbeddingConfig,
    *,
    dry_run: bool,
    connection=None,
) -> dict[str, Any]:
    documents = load_semantic_documents(path)
    chunks = chunk_documents(documents, provider, config)
    owned = connection is None
    connection = connection or open_connection()
    try:
        validate_ai_catalog(inspect_ai_catalog(connection), require_all=True)
        state = _load_sync_state(connection, config.profile_key)
        if state["profile"]:
            assert_profile_matches(state["profile"], config)
        plan = calculate_sync_plan(documents, chunks, state)
        started = time.perf_counter()
        if not dry_run:
            _apply_sync_plan(connection, documents, chunks, plan)
        database_seconds = time.perf_counter() - started
        return {
            "dry_run": dry_run,
            "source": str(path),
            "profile_key": config.profile_key,
            **plan.summary(),
            "chunking": chunk_statistics(chunks),
            "database_seconds": round(database_seconds, 4),
        }
    finally:
        if owned:
            connection.close()


def _embedding_work(connection, profile: dict[str, Any]) -> dict[str, Any]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT c.chunk_id, c.chunk_key, c.content, c.chunk_hash,
               e.embedded_chunk_hash
        FROM ai.RetailChunk AS c
        JOIN ai.RetailDocument AS d ON d.document_id = c.document_id
        LEFT JOIN ai.RetailEmbedding AS e
          ON e.chunk_id = c.chunk_id AND e.embedding_profile_id = ?
        WHERE d.is_active = 1
        ORDER BY c.chunk_id;
        """,
        (profile["embedding_profile_id"],),
    )
    required: list[dict[str, Any]] = []
    reused = 0
    generated = 0
    updated = 0
    for row in cursor.fetchall():
        item = {
            "chunk_id": int(row[0]),
            "chunk_key": str(row[1]),
            "content": str(row[2]),
            "chunk_hash": str(row[3]),
            "embedded_chunk_hash": str(row[4]) if row[4] is not None else None,
        }
        if item["embedded_chunk_hash"] == item["chunk_hash"]:
            reused += 1
        else:
            generated += item["embedded_chunk_hash"] is None
            updated += item["embedded_chunk_hash"] is not None
            required.append(item)
    return {
        "required": required,
        "generated": generated,
        "updated": updated,
        "reused": reused,
    }


def _vector_json(vector: np.ndarray, dimensions: int) -> str:
    values = np.asarray(vector, dtype=np.float32)
    if values.shape != (dimensions,):
        raise ValueError(
            f"Vector shape must be ({dimensions},), received {values.shape}"
        )
    if not np.isfinite(values).all():
        raise ValueError("Vector contains non-finite values")
    norm = float(np.linalg.norm(values))
    if not math.isclose(norm, 1.0, abs_tol=1e-4):
        raise ValueError(f"Vector is not normalized; norm={norm}")
    return json.dumps(values.tolist(), separators=(",", ":"), allow_nan=False)


def embed_required_chunks(
    provider: EmbeddingProvider,
    config: EmbeddingConfig,
    *,
    batch_size: int = 16,
    connection=None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    owned = connection is None
    connection = connection or open_connection()
    try:
        profile = _profile_row(connection.cursor(), config.profile_key)
        if not profile:
            raise RuntimeError(
                f"Embedding profile {config.profile_key!r} is not registered"
            )
        assert_profile_matches(profile, config)
        work = _embedding_work(connection, profile)
        required = work["required"]
        inference_seconds = 0.0
        database_seconds = 0.0
        completed = 0
        for start in range(0, len(required), batch_size):
            batch = required[start : start + batch_size]
            inference_started = time.perf_counter()
            vectors = provider.embed_documents(
                [item["content"] for item in batch], batch_size=batch_size
            )
            inference_seconds += time.perf_counter() - inference_started
            database_started = time.perf_counter()
            cursor = connection.cursor()
            try:
                for item, vector in zip(batch, vectors, strict=True):
                    cursor.execute(
                        """
                        MERGE ai.RetailEmbedding WITH (HOLDLOCK) AS target
                        USING (
                            SELECT CAST(? AS BIGINT) AS embedding_profile_id,
                                   CAST(? AS BIGINT) AS chunk_id,
                                   CAST(? AS VECTOR(384)) AS embedding,
                                   CAST(? AS CHAR(64)) AS embedded_chunk_hash
                        ) AS source
                        ON target.embedding_profile_id = source.embedding_profile_id
                           AND target.chunk_id = source.chunk_id
                        WHEN MATCHED THEN UPDATE SET
                            embedding = source.embedding,
                            embedded_chunk_hash = source.embedded_chunk_hash,
                            embedded_at = SYSUTCDATETIME()
                        WHEN NOT MATCHED THEN INSERT (
                            embedding_profile_id, chunk_id, embedding,
                            embedded_chunk_hash
                        ) VALUES (
                            source.embedding_profile_id, source.chunk_id,
                            source.embedding, source.embedded_chunk_hash
                        );
                        """,
                        (
                            profile["embedding_profile_id"],
                            item["chunk_id"],
                            _vector_json(vector, config.dimensions),
                            item["chunk_hash"],
                        ),
                    )
                connection.commit()
                completed += len(batch)
            except Exception:
                connection.rollback()
                raise
            finally:
                database_seconds += time.perf_counter() - database_started
        return {
            "profile_key": config.profile_key,
            "embeddings_required": len(required),
            "embeddings_generated": int(work["generated"]),
            "embeddings_updated": int(work["updated"]),
            "embeddings_reused": int(work["reused"]),
            "embeddings_completed": completed,
            "failures": 0,
            "inference_seconds": round(inference_seconds, 4),
            "database_seconds": round(database_seconds, 4),
            "total_seconds": round(inference_seconds + database_seconds, 4),
        }
    finally:
        if owned:
            connection.close()


def _parse_vector(value: Any) -> list[float]:
    if isinstance(value, str):
        parsed = json.loads(value)
    elif isinstance(value, (bytes, bytearray)):
        parsed = json.loads(value.decode("utf-8"))
    else:
        parsed = list(value)
    return [float(item) for item in parsed]


def validate_vector_layer(
    path: Path,
    provider: EmbeddingProvider,
    config: EmbeddingConfig,
    *,
    connection=None,
) -> dict[str, Any]:
    documents = load_semantic_documents(path)
    chunks = chunk_documents(documents, provider, config)
    expected_documents = {document.doc_key: document for document in documents}
    expected_chunks = {chunk.chunk_key: chunk for chunk in chunks}
    owned = connection is None
    connection = connection or open_connection()
    errors: list[str] = []
    try:
        profile = _profile_row(connection.cursor(), config.profile_key)
        if not profile:
            raise RuntimeError(
                f"Embedding profile {config.profile_key!r} is not registered"
            )
        try:
            assert_profile_matches(profile, config)
        except RuntimeError as error:
            errors.append(str(error))
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT document_id, doc_key, doc_type, retrieval_domain, source_sheet,
                   source_key, content, metadata_json, content_hash, is_active
            FROM ai.RetailDocument;
            """
        )
        stored_documents = {
            str(row[1]): {
                "document_id": int(row[0]),
                "doc_type": str(row[2]),
                "retrieval_domain": str(row[3]),
                "source_sheet": str(row[4]),
                "source_key": str(row[5]),
                "content": str(row[6]),
                "metadata_json": str(row[7]),
                "content_hash": str(row[8]),
                "is_active": bool(row[9]),
            }
            for row in cursor.fetchall()
        }
        active_keys = {
            key for key, value in stored_documents.items() if value["is_active"]
        }
        if active_keys != set(expected_documents):
            errors.append(
                "active document keys do not match source corpus: "
                f"missing={len(set(expected_documents) - active_keys)}, "
                f"extra={len(active_keys - set(expected_documents))}"
            )
        document_hash_mismatches = 0
        document_contract_mismatches = 0
        for key, expected in expected_documents.items():
            actual = stored_documents.get(key)
            if not actual:
                continue
            if actual["content_hash"] != content_hash(actual["content"]):
                document_hash_mismatches += 1
            actual_signature = (
                actual["doc_type"],
                actual["retrieval_domain"],
                actual["source_sheet"],
                actual["source_key"],
                actual["content"],
                _canonical_metadata(actual["metadata_json"]),
                actual["content_hash"],
                actual["is_active"],
            )
            if actual_signature != _document_signature(expected):
                document_contract_mismatches += 1
        if document_hash_mismatches:
            errors.append(f"document hash mismatches: {document_hash_mismatches}")
        if document_contract_mismatches:
            errors.append(
                f"document contract mismatches: {document_contract_mismatches}"
            )

        cursor.execute(
            """
            SELECT c.chunk_id, d.doc_key, c.chunk_index, c.chunk_key, c.content,
                   c.chunk_hash, c.token_count
            FROM ai.RetailChunk AS c
            JOIN ai.RetailDocument AS d ON d.document_id = c.document_id
            WHERE d.is_active = 1;
            """
        )
        stored_chunks = {
            str(row[3]): {
                "chunk_id": int(row[0]),
                "doc_key": str(row[1]),
                "chunk_index": int(row[2]),
                "content": str(row[4]),
                "chunk_hash": str(row[5]),
                "token_count": int(row[6]),
            }
            for row in cursor.fetchall()
        }
        missing_chunks = set(expected_chunks) - set(stored_chunks)
        extra_chunks = set(stored_chunks) - set(expected_chunks)
        chunk_hash_mismatches = 0
        chunk_contract_mismatches = 0
        over_limit_chunks = 0
        for key, actual in stored_chunks.items():
            if actual["chunk_hash"] != content_hash(actual["content"]):
                chunk_hash_mismatches += 1
            if actual["token_count"] > config.max_sequence_length:
                over_limit_chunks += 1
            expected = expected_chunks.get(key)
            if expected and (
                actual["doc_key"],
                actual["chunk_index"],
                actual["content"],
                actual["chunk_hash"],
                actual["token_count"],
            ) != (
                expected.doc_key,
                expected.chunk_index,
                expected.content,
                expected.chunk_hash,
                expected.token_count,
            ):
                chunk_contract_mismatches += 1
        if missing_chunks or extra_chunks:
            errors.append(
                f"chunk key mismatch: missing={len(missing_chunks)}, extra={len(extra_chunks)}"
            )
        if chunk_hash_mismatches:
            errors.append(f"chunk hash mismatches: {chunk_hash_mismatches}")
        if chunk_contract_mismatches:
            errors.append(f"chunk contract mismatches: {chunk_contract_mismatches}")
        if over_limit_chunks:
            errors.append(f"over-limit chunks: {over_limit_chunks}")

        cursor.execute(
            """
            SELECT c.chunk_key, c.chunk_hash, e.embedded_chunk_hash,
                   CAST(e.embedding AS NVARCHAR(MAX))
            FROM ai.RetailChunk AS c
            JOIN ai.RetailDocument AS d ON d.document_id = c.document_id
            LEFT JOIN ai.RetailEmbedding AS e
              ON e.chunk_id = c.chunk_id AND e.embedding_profile_id = ?
            WHERE d.is_active = 1;
            """,
            (profile["embedding_profile_id"],),
        )
        missing_embeddings = 0
        stale_hash_mismatches = 0
        wrong_dimension_vectors = 0
        non_normalized_vectors = 0
        persisted_embeddings = 0
        for row in cursor.fetchall():
            if row[2] is None or row[3] is None:
                missing_embeddings += 1
                continue
            persisted_embeddings += 1
            if str(row[1]) != str(row[2]):
                stale_hash_mismatches += 1
            vector = np.asarray(_parse_vector(row[3]), dtype=np.float32)
            if vector.shape != (config.dimensions,):
                wrong_dimension_vectors += 1
            elif not math.isclose(
                float(np.linalg.norm(vector)), 1.0, abs_tol=1e-4
            ):
                non_normalized_vectors += 1
        cursor.execute(
            """
            SELECT COUNT_BIG(*)
            FROM ai.RetailEmbedding AS e
            JOIN ai.RetailChunk AS c ON c.chunk_id = e.chunk_id
            JOIN ai.RetailDocument AS d ON d.document_id = c.document_id
            WHERE d.is_active = 1 AND e.embedding_profile_id <> ?;
            """,
            (profile["embedding_profile_id"],),
        )
        other_profile_embedding_count = int(cursor.fetchone()[0])
        if missing_embeddings:
            errors.append(f"missing embeddings: {missing_embeddings}")
        if stale_hash_mismatches:
            errors.append(f"stale embedding hashes: {stale_hash_mismatches}")
        if wrong_dimension_vectors:
            errors.append(f"wrong-dimension vectors: {wrong_dimension_vectors}")
        if non_normalized_vectors:
            errors.append(f"non-normalized vectors: {non_normalized_vectors}")

        stats = chunk_statistics(chunks)
        return {
            "valid": not errors,
            "semantic_documents": {
                "expected": len(documents),
                "persisted_active": len(active_keys),
                "content_hash_mismatches": document_hash_mismatches,
                "contract_mismatches": document_contract_mismatches,
            },
            "chunks": {
                **stats,
                "persisted": len(stored_chunks),
                "missing": len(missing_chunks),
                "extra": len(extra_chunks),
                "hash_mismatches": chunk_hash_mismatches,
                "contract_mismatches": chunk_contract_mismatches,
                "over_limit": over_limit_chunks,
            },
            "embedding_profile": {
                "profile_key": profile["profile_key"],
                "provider": profile["provider"],
                "model_name": profile["model_name"],
                "model_revision": profile["model_revision"],
                "dimensions": profile["dimensions"],
                "normalization": profile["normalization"],
                "status": profile["status"],
            },
            "embeddings": {
                "expected": len(chunks),
                "persisted": persisted_embeddings,
                "missing": missing_embeddings,
                "stale_hash_mismatches": stale_hash_mismatches,
                "wrong_dimension_vectors": wrong_dimension_vectors,
                "non_normalized_vectors": non_normalized_vectors,
                "other_profile_embedding_count": other_profile_embedding_count,
                "wrong_profile_vectors_in_search": 0,
            },
            "errors": errors,
        }
    finally:
        if owned:
            connection.close()


def activate_embedding_profile(
    path: Path,
    provider: EmbeddingProvider,
    config: EmbeddingConfig,
    *,
    connection=None,
) -> dict[str, Any]:
    documents = load_semantic_documents(path)
    if len(documents) != FROZEN_CORPUS_DOCUMENT_COUNT:
        raise RuntimeError(
            "Refusing to activate a partial profile: expected frozen corpus count "
            f"{FROZEN_CORPUS_DOCUMENT_COUNT}, got {len(documents)}"
        )
    owned = connection is None
    connection = connection or open_connection()
    try:
        validation = validate_vector_layer(
            path, provider, config, connection=connection
        )
        if not validation["valid"]:
            raise RuntimeError(
                "Refusing to activate an incomplete embedding profile: "
                + "; ".join(validation["errors"])
            )
        cursor = connection.cursor()
        profile = _profile_row(cursor, config.profile_key)
        if profile["status"] == EmbeddingProfileStatus.ACTIVE.value:
            return {"changed": False, "profile": profile, "validation": validation}
        validate_profile_transition(
            profile["status"], EmbeddingProfileStatus.ACTIVE
        )
        try:
            cursor.execute(
                """
                UPDATE ai.EmbeddingProfile
                SET status = N'RETIRED', retired_at = SYSUTCDATETIME()
                WHERE status = N'ACTIVE' AND embedding_profile_id <> ?;
                """,
                (profile["embedding_profile_id"],),
            )
            cursor.execute(
                """
                UPDATE ai.EmbeddingProfile
                SET status = N'ACTIVE', activated_at = SYSUTCDATETIME(),
                    retired_at = NULL
                WHERE embedding_profile_id = ? AND status = N'BUILDING';
                """,
                (profile["embedding_profile_id"],),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        activated = _profile_row(connection.cursor(), config.profile_key)
        return {"changed": True, "profile": activated, "validation": validation}
    finally:
        if owned:
            connection.close()


def rank_parent_results(
    candidates: Sequence[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = str(candidate["doc_key"])
        distance = float(candidate["cosine_distance"])
        if key not in best or distance < float(best[key]["cosine_distance"]):
            best[key] = dict(candidate)
    ordered = sorted(
        best.values(),
        key=lambda item: (float(item["cosine_distance"]), str(item["doc_key"])),
    )[:top_k]
    results: list[dict[str, Any]] = []
    for rank, item in enumerate(ordered, 1):
        item["rank"] = rank
        item["cosine_distance"] = round(float(item["cosine_distance"]), 8)
        item["cosine_similarity"] = round(
            1.0 - float(item["cosine_distance"]), 8
        )
        results.append(item)
    return results


def semantic_search(
    query: str,
    provider: EmbeddingProvider,
    config: EmbeddingConfig,
    *,
    top_k: int = 5,
    retrieval_domain: str | None = None,
    doc_type: str | None = None,
    allow_building: bool = False,
    connection=None,
) -> dict[str, Any]:
    if not 1 <= top_k <= 100:
        raise ValueError("top_k must be between 1 and 100")
    if retrieval_domain and retrieval_domain not in RETRIEVAL_DOMAINS:
        raise ValueError(f"Unknown retrieval domain: {retrieval_domain}")
    if doc_type and doc_type not in DOC_TYPE_RETRIEVAL_DOMAIN:
        raise ValueError(f"Unknown document type: {doc_type}")
    if doc_type and retrieval_domain:
        expected_domain = DOC_TYPE_RETRIEVAL_DOMAIN[doc_type]
        if expected_domain != retrieval_domain:
            raise ValueError(
                f"Document type {doc_type!r} belongs to {expected_domain!r}, not "
                f"{retrieval_domain!r}"
            )
    owned = connection is None
    connection = connection or open_connection()
    try:
        cursor = connection.cursor()
        if allow_building:
            cursor.execute(
                """
                SELECT embedding_profile_id, profile_key, provider, model_name,
                       model_revision, dimensions, normalization, max_sequence_length,
                       document_instruction, query_instruction, chunk_target_tokens,
                       chunk_overlap_tokens, configuration_json, status, created_at,
                       activated_at, retired_at
                FROM ai.EmbeddingProfile
                WHERE profile_key = ? AND status IN (N'BUILDING', N'ACTIVE');
                """,
                (config.profile_key,),
            )
        else:
            cursor.execute(
                """
            SELECT embedding_profile_id, profile_key, provider, model_name,
                   model_revision, dimensions, normalization, max_sequence_length,
                   document_instruction, query_instruction, chunk_target_tokens,
                   chunk_overlap_tokens, configuration_json, status, created_at,
                   activated_at, retired_at
            FROM ai.EmbeddingProfile
            WHERE status = N'ACTIVE';
                """
            )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(
                "No searchable embedding profile is available"
                if allow_building
                else "No ACTIVE embedding profile is available"
            )
        names = (
            "embedding_profile_id", "profile_key", "provider", "model_name",
            "model_revision", "dimensions", "normalization", "max_sequence_length",
            "document_instruction", "query_instruction", "chunk_target_tokens",
            "chunk_overlap_tokens", "configuration_json", "status", "created_at",
            "activated_at", "retired_at",
        )
        profile = dict(zip(names, row))
        for name in (
            "embedding_profile_id", "dimensions", "max_sequence_length",
            "chunk_target_tokens", "chunk_overlap_tokens",
        ):
            profile[name] = int(profile[name])
        profile["normalization"] = bool(profile["normalization"])
        assert_profile_matches(profile, config)
        query_vector = provider.embed_query(query)
        query_json = _vector_json(query_vector, config.dimensions)
        candidate_limit = min(max(top_k * 10, 50), 1000)
        clauses = [
            "e.embedding_profile_id = ?",
            "d.is_active = 1",
            "e.embedded_chunk_hash = c.chunk_hash",
        ]
        params: list[Any] = [
            query_json,
            profile["embedding_profile_id"],
        ]
        if retrieval_domain:
            clauses.append("d.retrieval_domain = ?")
            params.append(retrieval_domain)
        if doc_type:
            clauses.append("d.doc_type = ?")
            params.append(doc_type)
        cursor.execute(
            f"""
            SELECT TOP ({candidate_limit})
                   VECTOR_DISTANCE(
                       'cosine', e.embedding, CAST(? AS VECTOR(384))
                   ) AS cosine_distance,
                   d.doc_key, d.doc_type, d.retrieval_domain, d.source_key,
                   c.chunk_index, c.chunk_key, c.content
            FROM ai.RetailEmbedding AS e
            JOIN ai.RetailChunk AS c ON c.chunk_id = e.chunk_id
            JOIN ai.RetailDocument AS d ON d.document_id = c.document_id
            WHERE {' AND '.join(clauses)}
            ORDER BY cosine_distance ASC;
            """,
            tuple(params),
        )
        candidates = []
        for row in cursor.fetchall():
            content = str(row[7])
            candidates.append(
                {
                    "cosine_distance": float(row[0]),
                    "doc_key": str(row[1]),
                    "doc_type": str(row[2]),
                    "retrieval_domain": str(row[3]),
                    "source_key": str(row[4]),
                    "matched_chunk_index": int(row[5]),
                    "matched_chunk_key": str(row[6]),
                    "matched_chunk_text": content,
                    "excerpt": content[:300] + ("..." if len(content) > 300 else ""),
                }
            )
        results = rank_parent_results(candidates, top_k)
        return {
            "query": query,
            "profile_key": profile["profile_key"],
            "metric": "cosine_distance",
            "lower_is_better": True,
            "filters": {
                "retrieval_domain": retrieval_domain,
                "doc_type": doc_type,
            },
            "top_k": top_k,
            "result_count": len(results),
            "results": results,
        }
    finally:
        if owned:
            connection.close()
