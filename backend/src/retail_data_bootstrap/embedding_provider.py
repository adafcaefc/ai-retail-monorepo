from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from .embedding_config import EmbeddingConfig


class EmbeddingProvider(ABC):
    def __init__(self, config: EmbeddingConfig):
        self.config = config

    @property
    def provider_key(self) -> str:
        return self.config.provider_key

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def dimensions(self) -> int:
        return self.config.dimensions

    @property
    def normalization(self) -> bool:
        return self.config.normalize

    @property
    def max_sequence_length(self) -> int:
        return self.config.max_sequence_length

    @abstractmethod
    def embed_documents(
        self, texts: Sequence[str], *, batch_size: int = 16
    ) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def content_token_ids(self, text: str) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def decode_content_tokens(self, token_ids: Sequence[int]) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def special_token_count(self) -> int:
        raise NotImplementedError


class LocalBgeEmbeddingProvider(EmbeddingProvider):
    """Lazy CPU-only Sentence Transformers provider for BGE passage retrieval."""

    def __init__(
        self,
        config: EmbeddingConfig | None = None,
        *,
        model_factory: Callable[..., Any] | None = None,
    ):
        super().__init__(config or EmbeddingConfig.from_env())
        self._model_factory = model_factory
        self._model: Any | None = None
        self._special_token_count: int | None = None

    def _load_model(self):
        if self._model is None:
            factory = self._model_factory
            if factory is None:
                from sentence_transformers import SentenceTransformer

                factory = SentenceTransformer
            self._model = factory(
                self.config.model_name,
                device=self.config.device,
                revision=self.config.model_revision,
                local_files_only=True,
            )
            actual_max = int(self._model.max_seq_length)
            if actual_max != self.config.max_sequence_length:
                raise RuntimeError(
                    f"Embedding model max sequence length mismatch: expected "
                    f"{self.config.max_sequence_length}, got {actual_max}"
                )
            dimension_method = getattr(
                self._model,
                "get_embedding_dimension",
                self._model.get_sentence_embedding_dimension,
            )
            actual_dimensions = int(dimension_method())
            if actual_dimensions != self.config.dimensions:
                raise RuntimeError(
                    f"Embedding dimension mismatch: expected {self.config.dimensions}, "
                    f"got {actual_dimensions}"
                )
        return self._model

    @property
    def tokenizer(self):
        return self._load_model().tokenizer

    def count_tokens(self, text: str) -> int:
        encoded = self.tokenizer(
            text,
            add_special_tokens=True,
            truncation=False,
            return_attention_mask=False,
            return_token_type_ids=False,
            verbose=False,
        )
        return len(encoded["input_ids"])

    def content_token_ids(self, text: str) -> list[int]:
        return list(
            self.tokenizer.encode(
                text,
                add_special_tokens=False,
                truncation=False,
                verbose=False,
            )
        )

    def decode_content_tokens(self, token_ids: Sequence[int]) -> str:
        return str(
            self.tokenizer.decode(
                list(token_ids),
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )
        ).strip()

    @property
    def special_token_count(self) -> int:
        if self._special_token_count is None:
            self._special_token_count = self.count_tokens("")
        return self._special_token_count

    def _validate_text_lengths(self, texts: Sequence[str]) -> None:
        over_limit = []
        for index, text in enumerate(texts):
            count = self.count_tokens(text)
            if count > self.max_sequence_length:
                over_limit.append((index, count))
        if over_limit:
            raise ValueError(
                "Embedding input exceeds the model sequence limit; no truncation is "
                f"allowed: {over_limit[:10]}"
            )

    def _validate_embeddings(
        self, embeddings: Any, *, expected_count: int
    ) -> np.ndarray:
        array = np.asarray(embeddings, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        expected_shape = (expected_count, self.dimensions)
        if array.shape != expected_shape:
            raise RuntimeError(
                f"Embedding output shape mismatch: expected {expected_shape}, got {array.shape}"
            )
        if not np.isfinite(array).all():
            raise RuntimeError("Embedding output contains non-finite values")
        norms = np.linalg.norm(array, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-4):
            raise RuntimeError("Embedding output is not L2 normalized")
        return array

    def embed_documents(
        self, texts: Sequence[str], *, batch_size: int = 16
    ) -> np.ndarray:
        values = list(texts)
        if not values:
            return np.empty((0, self.dimensions), dtype=np.float32)
        self._validate_text_lengths(values)
        embeddings = self._load_model().encode(
            values,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return self._validate_embeddings(embeddings, expected_count=len(values))

    def embed_query(self, text: str) -> np.ndarray:
        query = text.strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        encoded_text = f"{self.config.query_instruction}{query}"
        self._validate_text_lengths([encoded_text])
        embedding = self._load_model().encode(
            encoded_text,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return self._validate_embeddings(embedding, expected_count=1)[0]


def create_embedding_provider(
    config: EmbeddingConfig | None = None,
) -> EmbeddingProvider:
    resolved = config or EmbeddingConfig.from_env()
    if resolved.provider_key == "local_sentence_transformers":
        return LocalBgeEmbeddingProvider(resolved)
    raise ValueError(f"Unsupported embedding provider: {resolved.provider_key}")
