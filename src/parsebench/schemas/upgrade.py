"""Schema versions and the pure upgrade chain that lifts old records to the current version.

Every read runs `upgrade` before validation. An upgrade function takes a raw
JSON dict at version N and returns one at version N+1; the chain stamps the
new `schema_version` after each step. Functions are registered in `UPGRADES`
by `(kind, from_version)` and are never deleted while a published run uses
that version.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from pydantic import BaseModel, JsonValue

from parsebench.errors import SchemaError, UnknownSchemaVersion
from parsebench.schemas.answer import AnswerFailed, AnswerOk
from parsebench.schemas.document import Document
from parsebench.schemas.manifest import RunManifest, SchemaVersions
from parsebench.schemas.parse import ParseFailed, ParseOk
from parsebench.schemas.result import Result
from parsebench.schemas.task import Task
from parsebench.schemas.types import RecordKind

type RawRecord = dict[str, JsonValue]
"""A record as parsed JSON, before validation."""

type UpgradeFn = Callable[[RawRecord], RawRecord]
"""Pure function lifting a raw record from version N to N+1."""


def _version_of(*models: type[BaseModel]) -> int:
    versions = {m.model_fields["schema_version"].default for m in models}
    if len(versions) != 1:
        raise SchemaError("union variants must share one schema_version")
    (version,) = versions
    if not isinstance(version, int):
        raise SchemaError("schema_version default must be an int")
    return version


CURRENT_VERSIONS: Mapping[RecordKind, int] = MappingProxyType(
    {
        RecordKind.DOCUMENT: _version_of(Document),
        RecordKind.TASK: _version_of(Task),
        RecordKind.PARSE_RESULT: _version_of(ParseOk, ParseFailed),
        RecordKind.ANSWER: _version_of(AnswerOk, AnswerFailed),
        RecordKind.RESULT: _version_of(Result),
        RecordKind.RUN_MANIFEST: _version_of(RunManifest),
    }
)
"""Current schema version of each record kind, read from the models."""

UPGRADES: Mapping[tuple[RecordKind, int], UpgradeFn] = MappingProxyType({})
"""Registered upgrade functions by (kind, from_version). Empty while every record is at v1."""


def current_schema_versions() -> SchemaVersions:
    """Return `CURRENT_VERSIONS` as the manifest's `schema_versions` field."""
    return SchemaVersions(**{kind.value: version for kind, version in CURRENT_VERSIONS.items()})


def upgrade(
    kind: RecordKind,
    data: RawRecord,
    *,
    registry: Mapping[tuple[RecordKind, int], UpgradeFn] = UPGRADES,
    current: Mapping[RecordKind, int] = CURRENT_VERSIONS,
) -> RawRecord:
    """Return `data` lifted to the current version of `kind`, without mutating it.

    Raises `SchemaError` when `schema_version` is missing or not an integer of
    at least 1, and `UnknownSchemaVersion` when it is newer than the code knows
    or a step in the chain is missing.
    """
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SchemaError("must be an integer of at least 1", field="schema_version")
    target = current[kind]
    if version > target:
        raise UnknownSchemaVersion(
            f"{kind.value} schema_version {version} is newer than this code knows ({target})",
            field="schema_version",
        )
    lifted = dict(data)
    for step in range(version, target):
        fn = registry.get((kind, step))
        if fn is None:
            raise UnknownSchemaVersion(
                f"no upgrade registered for {kind.value} v{step} to v{step + 1}",
                field="schema_version",
            )
        lifted = {**fn(dict(lifted)), "schema_version": step + 1}
    return lifted
