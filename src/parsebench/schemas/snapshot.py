"""Committed JSON Schema snapshots: a shape change cannot ship without a version bump.

Each record's current version has a file `json/<kind>.v<N>.json`. A test
compares the live schema to it, and CI rejects edits to existing snapshot
files. `write_snapshots` only creates missing files, so after bumping a
version you run `python -m parsebench.schemas.snapshot` to add the new one.
This module holds the package's only I/O, and it is run by hand.
"""

import json
from pathlib import Path

from pydantic import JsonValue

from parsebench.schemas.answer import ANSWER
from parsebench.schemas.document import Document
from parsebench.schemas.manifest import RunManifest
from parsebench.schemas.parse import PARSE_RESULT
from parsebench.schemas.result import Result
from parsebench.schemas.task import Task
from parsebench.schemas.types import RecordKind
from parsebench.schemas.upgrade import CURRENT_VERSIONS

SNAPSHOT_DIR = Path(__file__).parent / "json"
"""Where committed snapshots live."""


def live_schema(kind: RecordKind) -> dict[str, JsonValue]:
    """Return the JSON Schema (validation mode) the code currently produces for `kind`."""
    match kind:
        case RecordKind.DOCUMENT:
            return Document.model_json_schema(mode="validation")
        case RecordKind.TASK:
            return Task.model_json_schema(mode="validation")
        case RecordKind.PARSE_RESULT:
            return PARSE_RESULT.json_schema(mode="validation")
        case RecordKind.ANSWER:
            return ANSWER.json_schema(mode="validation")
        case RecordKind.RESULT:
            return Result.model_json_schema(mode="validation")
        case RecordKind.RUN_MANIFEST:
            return RunManifest.model_json_schema(mode="validation")


def snapshot_name(kind: RecordKind, version: int) -> str:
    """Return the snapshot file name for a kind at a version, such as `task.v1.json`."""
    return f"{kind.value}.v{version}.json"


def snapshot_text(kind: RecordKind) -> str:
    """Return the snapshot file text for `kind` at its current version (sorted keys, indented)."""
    return json.dumps(live_schema(kind), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_snapshots(directory: Path = SNAPSHOT_DIR) -> tuple[Path, ...]:
    """Create any missing current version snapshot and return the paths written.

    An existing file is never overwritten. If it differs from the live schema,
    this raises `FileExistsError`: bump the version instead of editing a snapshot.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for kind, version in CURRENT_VERSIONS.items():
        path = directory / snapshot_name(kind, version)
        text = snapshot_text(kind)
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise FileExistsError(f"{path.name} exists and differs; bump {kind.value}'s schema_version")
            continue
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return tuple(written)


if __name__ == "__main__":
    for written_path in write_snapshots():
        print(f"wrote {written_path}")
