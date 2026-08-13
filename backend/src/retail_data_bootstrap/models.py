from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticDocument:
    doc_key: str
    doc_type: str
    retrieval_domain: str
    source_sheet: str
    source_key: str
    content: str
    metadata: dict[str, Any]
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SheetSpec:
    classification: str
    reason: str
    orientation: str
    header_row: int
    candidate_key_columns: tuple[tuple[str, ...], ...] = ()
