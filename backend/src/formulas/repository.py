"""JSON-file persistence for formulas.

Everything else in the backend persists through Postgres. Formulas are a
small, hand-curated reference set seeded from `resources/formula.md`, so they
live in one JSON file that is easy to read, diff and hand-edit.

Writes are atomic (temp file + os.replace) and serialized by a module lock, so
a half-written file is never observable and two concurrent requests cannot
interleave a read-modify-write.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

from pathlib import Path
from typing import Any

from src.common.constants import AppPaths

VERSION = 1

_LOCK = threading.RLock()


def store_path() -> Path:
    """Resolved at call time so tests can point AppPaths at a tmp file."""
    return Path(AppPaths.FORMULA_STORE)


def load() -> list[dict[str, Any]]:
    """Every stored formula, ordered by `number`. Missing file reads as empty."""
    path = store_path()
    with _LOCK:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{path.name} is not valid JSON: {error}"
            ) from error

    formulas = payload.get("formulas") if isinstance(payload, dict) else None
    if not isinstance(formulas, list):
        raise ValueError(
            f"{path.name} must be an object with a 'formulas' list."
        )
    return sorted(formulas, key=lambda item: item.get("number", 0))


def save(formulas: list[dict[str, Any]]) -> None:
    """Replace the whole file. Callers pass the full, already-validated list."""
    path = store_path()
    body = json.dumps(
        {"version": VERSION, "formulas": formulas},
        indent=4,
        ensure_ascii=False,
    )

    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(body + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            # Never leave a stray temp file behind on failure.
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise
