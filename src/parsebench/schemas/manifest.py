"""RunManifest: everything needed to reproduce one run, and nothing secret.

`settings_snapshot` is an allowlist: it skips every `SecretStr` setting, and
`SettingEntry` rejects any secret setting name outright, so a secret can never
reach a published manifest.
"""

from collections.abc import Sequence
from pathlib import PurePath
from typing import Annotated, Any, Self, get_args

from pydantic import AfterValidator, Field, SecretStr, model_validator

from parsebench.schemas.base import Frozen, Record
from parsebench.schemas.types import (
    GitRevision,
    Name,
    ParserId,
    RunId,
    SemVer,
    Sha256,
    TruncationKind,
    UtcDatetime,
)
from parsebench.settings import Settings


def _is_secret_annotation(annotation: Any) -> bool:
    return annotation is SecretStr or SecretStr in get_args(annotation)


SECRET_SETTING_NAMES: frozenset[str] = frozenset(
    name for name, field in Settings.model_fields.items() if _is_secret_annotation(field.annotation)
)
"""Settings fields typed `SecretStr` (or `SecretStr | None`). Never written to a manifest."""

ENVIRONMENT_SETTING_NAMES: frozenset[str] = frozenset({"threads"})
"""Settings recorded under `environment` instead of `settings`."""


def _not_secret(name: str) -> str:
    if name in SECRET_SETTING_NAMES:
        raise ValueError("secret settings may not appear in a manifest")
    return name


def _sorted_unique(keys: Sequence[str], what: str) -> None:
    if list(keys) != sorted(set(keys)):
        raise ValueError(f"{what} must be sorted and unique")


class TaskSetRef(Frozen):
    """Which frozen task set a run used, by folder name and content hash."""

    version: Annotated[str, Field(pattern=r"^(dev|v[0-9]+\.[0-9]+)$")]
    sha256: Sha256


class TruncationRule(Frozen):
    """How parser text was cut before answering. `limit` is in the unit `kind` sets."""

    kind: TruncationKind
    limit: Annotated[int, Field(ge=1)]


class AnsweringConfig(Frozen):
    """The one model, prompt, and truncation every parser was answered with."""

    provider: Name
    model: Name
    temperature: Annotated[float, Field(ge=0)]
    prompt_sha256: Sha256
    truncation: TruncationRule


class ModelRevision(Frozen):
    """A pinned model weight download: Hugging Face repo plus commit SHA."""

    repo: Name
    revision: GitRevision


class ParserInfo(Frozen):
    """One parser's self report: package, version (PEP 440), extra, and pinned models."""

    parser_id: ParserId
    package: Name
    package_version: Name
    extra: Name | None
    model_revisions: tuple[ModelRevision, ...]

    @model_validator(mode="after")
    def _revisions_sorted(self) -> Self:
        _sorted_unique([m.repo for m in self.model_revisions], "model_revisions (by repo)")
        return self


class ToolVersion(Frozen):
    """A system tool a parser shells out to, and its version."""

    name: Name
    version: Name


class Environment(Frozen):
    """Machine and install the run happened on."""

    python_version: Name
    os: Name
    cpu: str
    threads: Annotated[int, Field(ge=1)]
    uv_lock_sha256: Sha256 | None
    """None when installed without a lock file."""
    torch_version: Name | None
    system_tools: tuple[ToolVersion, ...]

    @model_validator(mode="after")
    def _tools_sorted(self) -> Self:
        _sorted_unique([t.name for t in self.system_tools], "system_tools (by name)")
        return self


class SettingEntry(Frozen):
    """One non secret setting: its field name (not the env alias) and its value as text."""

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$"), AfterValidator(_not_secret)]
    value: str


class SchemaVersions(Frozen):
    """The schema version of every record type this run wrote."""

    document: Annotated[int, Field(ge=1)]
    task: Annotated[int, Field(ge=1)]
    parse_result: Annotated[int, Field(ge=1)]
    answer: Annotated[int, Field(ge=1)]
    result: Annotated[int, Field(ge=1)]
    run_manifest: Annotated[int, Field(ge=1)]


class RunManifest(Record):
    """Everything needed to reproduce a run, keyed by `run_id`. Holds no secrets.

    `run_id`'s date must equal `created_at`'s UTC date. Every tuple is sorted
    and unique by its key, so equal manifests always give equal bytes.
    """

    run_id: RunId
    created_at: UtcDatetime
    seed: Annotated[int, Field(ge=0)]
    task_set: TaskSetRef
    scorer_version: SemVer
    answering: AnsweringConfig
    parsers: tuple[ParserInfo, ...]
    environment: Environment
    settings: tuple[SettingEntry, ...]
    concurrency: Annotated[int, Field(ge=1)]
    schema_versions: SchemaVersions

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.run_id[:10] != self.created_at.date().isoformat():
            raise ValueError("run_id date must equal created_at's UTC date")
        _sorted_unique([p.parser_id for p in self.parsers], "parsers (by parser_id)")
        _sorted_unique([s.name for s in self.settings], "settings (by name)")
        return self


def _setting_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, str):
        return value
    raise TypeError(f"settings_snapshot has no rule for {type(value).__name__} settings")


def settings_snapshot(settings: Settings) -> tuple[SettingEntry, ...]:
    """Return the non secret settings as sorted entries, values as text.

    Paths are written as given (never resolved, so a home folder never leaks),
    None becomes `""`, and `threads` is left out because it lives in
    `environment`. A setting of any other type raises `TypeError`, so this
    function gets updated when a new setting type appears.
    """
    skipped = SECRET_SETTING_NAMES | ENVIRONMENT_SETTING_NAMES
    return tuple(
        SettingEntry(name=name, value=_setting_value(getattr(settings, name)))
        for name in sorted(type(settings).model_fields)
        if name not in skipped
    )
