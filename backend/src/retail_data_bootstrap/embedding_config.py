from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


DEFAULT_PROVIDER_KEY = "local_sentence_transformers"
DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
DEFAULT_PROFILE_KEY = "local-bge-small-en-v1.5-384-v1"
DEFAULT_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
FROZEN_CORPUS_DOCUMENT_COUNT = 1350


class EmbeddingProfileStatus(StrEnum):
    BUILDING = "BUILDING"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


ALLOWED_PROFILE_TRANSITIONS = {
    EmbeddingProfileStatus.BUILDING: {
        EmbeddingProfileStatus.ACTIVE,
        EmbeddingProfileStatus.RETIRED,
    },
    EmbeddingProfileStatus.ACTIVE: {EmbeddingProfileStatus.RETIRED},
    EmbeddingProfileStatus.RETIRED: set(),
}


def validate_profile_transition(
    current: EmbeddingProfileStatus | str,
    target: EmbeddingProfileStatus | str,
) -> None:
    current_status = EmbeddingProfileStatus(current)
    target_status = EmbeddingProfileStatus(target)
    if current_status == target_status:
        return
    if target_status not in ALLOWED_PROFILE_TRANSITIONS[current_status]:
        raise ValueError(
            f"Invalid embedding-profile transition: {current_status.value} -> "
            f"{target_status.value}"
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


@dataclass(frozen=True)
class EmbeddingConfig:
    profile_key: str = DEFAULT_PROFILE_KEY
    provider_key: str = DEFAULT_PROVIDER_KEY
    model_name: str = DEFAULT_MODEL_NAME
    model_revision: str = DEFAULT_MODEL_REVISION
    dimensions: int = 384
    normalize: bool = True
    device: str = "cpu"
    max_sequence_length: int = 512
    document_instruction: str = ""
    query_instruction: str = DEFAULT_QUERY_INSTRUCTION
    chunk_target_tokens: int = 384
    chunk_overlap_tokens: int = 48

    def __post_init__(self) -> None:
        for name in ("profile_key", "provider_key", "model_name", "model_revision"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")
        if self.provider_key != DEFAULT_PROVIDER_KEY:
            raise ValueError(
                f"Unsupported Phase 5 embedding provider: {self.provider_key!r}"
            )
        if self.dimensions != 384:
            raise ValueError("Phase 5 Azure SQL storage requires exactly 384 dimensions")
        if not self.normalize:
            raise ValueError("Phase 5 requires normalized document and query embeddings")
        if self.device.lower() != "cpu":
            raise ValueError("Phase 5 local embedding inference is CPU-only")
        if self.max_sequence_length != 512:
            raise ValueError("BAAI/bge-small-en-v1.5 must use its 512-token limit")
        if self.document_instruction:
            raise ValueError("Stored document/chunk text must not receive an instruction prefix")
        if self.query_instruction != DEFAULT_QUERY_INSTRUCTION:
            raise ValueError("The Phase 5 BGE short-query instruction is frozen")
        if not 0 <= self.chunk_overlap_tokens < self.chunk_target_tokens:
            raise ValueError("chunk overlap must be non-negative and smaller than target")
        if self.chunk_target_tokens > self.max_sequence_length:
            raise ValueError("chunk target cannot exceed the model sequence length")

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            profile_key=os.getenv(
                "RETAIL_EMBEDDING_PROFILE_KEY", DEFAULT_PROFILE_KEY
            ).strip(),
            provider_key=os.getenv(
                "RETAIL_EMBEDDING_PROVIDER", DEFAULT_PROVIDER_KEY
            ).strip(),
            model_name=os.getenv(
                "RETAIL_EMBEDDING_MODEL", DEFAULT_MODEL_NAME
            ).strip(),
            model_revision=os.getenv(
                "RETAIL_EMBEDDING_MODEL_REVISION", DEFAULT_MODEL_REVISION
            ).strip(),
            dimensions=_env_int("RETAIL_EMBEDDING_DIMENSIONS", 384),
            normalize=_env_bool("RETAIL_EMBEDDING_NORMALIZE", True),
            device=os.getenv("RETAIL_EMBEDDING_DEVICE", "cpu").strip(),
            max_sequence_length=_env_int(
                "RETAIL_EMBEDDING_MAX_SEQUENCE_LENGTH", 512
            ),
            document_instruction="",
            query_instruction=DEFAULT_QUERY_INSTRUCTION,
            chunk_target_tokens=_env_int(
                "RETAIL_EMBEDDING_CHUNK_TARGET_TOKENS", 384
            ),
            chunk_overlap_tokens=_env_int(
                "RETAIL_EMBEDDING_CHUNK_OVERLAP_TOKENS", 48
            ),
        )

    def configuration(self) -> dict[str, Any]:
        value = asdict(self)
        value["configuration_version"] = 1
        value["chunker_version"] = "logical-boundary-token-overlap-v1"
        return value

    def configuration_json(self) -> str:
        return json.dumps(
            self.configuration(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

