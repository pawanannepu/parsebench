"""Canonical JSON and hashing: equal records always give identical bytes.

Keys are sorted, separators are compact, text is UTF-8 with no escaping or
Unicode normalization. Money is fixed point with 6 places and datetimes end
in `Z` (both set by the field types).
"""

import hashlib
import json

from pydantic import BaseModel

from parsebench.schemas.types import Sha256


def canonical_json(record: BaseModel) -> bytes:
    """Return the record as sorted key, compact, UTF-8 JSON bytes."""
    return json.dumps(
        record.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> Sha256:
    """Return the lowercase hex sha256 of `data`."""
    return hashlib.sha256(data).hexdigest()


def task_set_sha256(documents_bytes: bytes, tasks_bytes: bytes) -> Sha256:
    """Hash a task set from the stored bytes of `documents.jsonl` and `tasks.jsonl`.

    Hashing the stored bytes (written once, never rewritten) means a later
    schema or Pydantic upgrade can never change a task set's hash.
    """
    combined = sha256_hex(documents_bytes) + "\n" + sha256_hex(tasks_bytes)
    return sha256_hex(combined.encode("utf-8"))
