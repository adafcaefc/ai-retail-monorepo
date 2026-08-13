from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .documents import canonical_content, content_hash
from .embedding_config import EmbeddingConfig
from .embedding_provider import EmbeddingProvider
from .models import SemanticDocument


@dataclass(frozen=True)
class SemanticChunk:
    doc_key: str
    chunk_index: int
    chunk_key: str
    content: str
    chunk_hash: str
    token_count: int


def _sentence_units(text: str) -> list[str]:
    units = [
        value.strip()
        for value in re.split(r"(?<=[.!?;])\s+", text.strip())
        if value.strip()
    ]
    return units or [text.strip()]


def _logical_units(
    text: str,
    provider: EmbeddingProvider,
    target_tokens: int,
) -> list[str]:
    lines = [line.strip() for line in re.split(r"\n+", text) if line.strip()]
    units: list[str] = []
    for line in lines:
        if provider.count_tokens(line) <= target_tokens:
            units.append(line)
            continue
        sentences = _sentence_units(line)
        if len(sentences) == 1:
            units.append(line)
            continue
        current: list[str] = []
        for sentence in sentences:
            candidate = " ".join([*current, sentence])
            if current and provider.count_tokens(candidate) > target_tokens:
                units.append(" ".join(current))
                current = [sentence]
            else:
                current.append(sentence)
        if current:
            units.append(" ".join(current))
    return units or [text]


def _token_windows(
    text: str,
    provider: EmbeddingProvider,
    *,
    target_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    token_ids = provider.content_token_ids(text)
    content_capacity = target_tokens - provider.special_token_count
    if content_capacity <= 0:
        raise ValueError("Chunk target leaves no room for content tokens")
    if len(token_ids) <= content_capacity:
        return [text]
    step = content_capacity - min(overlap_tokens, content_capacity - 1)
    windows: list[str] = []
    start = 0
    while start < len(token_ids):
        decoded = provider.decode_content_tokens(token_ids[start : start + content_capacity])
        value = canonical_content(decoded)
        if not value:
            raise ValueError("Tokenizer produced an empty chunk while splitting content")
        windows.append(value)
        if start + content_capacity >= len(token_ids):
            break
        start += step
    return windows


def _trailing_overlap(
    text: str,
    provider: EmbeddingProvider,
    *,
    maximum_tokens: int,
) -> str:
    if maximum_tokens <= 0:
        return ""
    token_ids = provider.content_token_ids(text)
    if not token_ids:
        return ""
    return canonical_content(
        provider.decode_content_tokens(token_ids[-maximum_tokens:])
    )


def _pack_units(
    units: Sequence[str],
    provider: EmbeddingProvider,
    config: EmbeddingConfig,
) -> list[str]:
    expanded: list[str] = []
    for unit in units:
        expanded.extend(
            _token_windows(
                unit,
                provider,
                target_tokens=config.chunk_target_tokens,
                overlap_tokens=config.chunk_overlap_tokens,
            )
        )

    chunks: list[str] = []
    current = ""
    for unit in expanded:
        candidate = canonical_content(f"{current}\n{unit}" if current else unit)
        if not current or provider.count_tokens(candidate) <= config.chunk_target_tokens:
            current = candidate
            continue

        chunks.append(current)
        unit_count = provider.count_tokens(unit)
        available_total = config.chunk_target_tokens - unit_count
        overlap_size = min(config.chunk_overlap_tokens, max(0, available_total))
        overlap = _trailing_overlap(
            current, provider, maximum_tokens=overlap_size
        )
        candidate = canonical_content(f"{overlap}\n{unit}" if overlap else unit)
        while overlap_size > 0 and provider.count_tokens(candidate) > config.chunk_target_tokens:
            overlap_size -= 1
            overlap = _trailing_overlap(
                current, provider, maximum_tokens=overlap_size
            )
            candidate = canonical_content(f"{overlap}\n{unit}" if overlap else unit)
        if provider.count_tokens(candidate) > config.chunk_target_tokens:
            raise ValueError("Unable to construct a token-safe chunk")
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_document(
    document: SemanticDocument,
    provider: EmbeddingProvider,
    config: EmbeddingConfig | None = None,
) -> list[SemanticChunk]:
    resolved = config or provider.config
    text = canonical_content(document.content)
    original_count = provider.count_tokens(text)
    if original_count <= resolved.max_sequence_length:
        chunk_texts = [text]
    else:
        units = _logical_units(text, provider, resolved.chunk_target_tokens)
        chunk_texts = _pack_units(units, provider, resolved)
        if len(chunk_texts) < 2:
            raise ValueError(
                f"Oversized document {document.doc_key} did not produce multiple chunks"
            )

    chunks: list[SemanticChunk] = []
    for index, chunk_text in enumerate(chunk_texts):
        token_count = provider.count_tokens(chunk_text)
        if token_count > resolved.max_sequence_length:
            raise ValueError(
                f"Chunk {document.doc_key}#{index:03d} has {token_count} tokens; "
                f"maximum is {resolved.max_sequence_length}"
            )
        chunks.append(
            SemanticChunk(
                doc_key=document.doc_key,
                chunk_index=index,
                chunk_key=f"{document.doc_key}#{index:03d}",
                content=chunk_text,
                chunk_hash=content_hash(chunk_text),
                token_count=token_count,
            )
        )
    return chunks


def chunk_documents(
    documents: Sequence[SemanticDocument],
    provider: EmbeddingProvider,
    config: EmbeddingConfig | None = None,
) -> list[SemanticChunk]:
    chunks: list[SemanticChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, provider, config))
    return chunks


def chunk_statistics(chunks: Sequence[SemanticChunk]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.doc_key] = counts.get(chunk.doc_key, 0) + 1
    multi = {key: value for key, value in counts.items() if value > 1}
    return {
        "document_count": len(counts),
        "chunk_count": len(chunks),
        "single_chunk_document_count": sum(value == 1 for value in counts.values()),
        "multi_chunk_document_count": len(multi),
        "multi_chunk_documents": dict(sorted(multi.items())),
        "maximum_chunk_token_count": max(
            (chunk.token_count for chunk in chunks), default=0
        ),
    }
