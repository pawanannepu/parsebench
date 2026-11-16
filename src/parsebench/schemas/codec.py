"""Read and write records as JSON: the one validation path.

Every read parses text to a dict (rejecting duplicate keys, NaN, a BOM, blank
lines, and `\\r`), runs `upgrade`, then validates the re-encoded JSON in strict
mode. Pydantic's `ValidationError` becomes a `SchemaError` naming the source,
line, and field, never the input value. Writing gives one canonical line per
record, sorted by ID in codepoint order.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Literal, NoReturn, cast, overload

from pydantic import JsonValue, ValidationError

from parsebench.errors import SchemaError
from parsebench.schemas.answer import ANSWER, AnswerFailed, AnswerOk
from parsebench.schemas.canonical import canonical_json
from parsebench.schemas.document import Document
from parsebench.schemas.manifest import RunManifest
from parsebench.schemas.parse import PARSE_RESULT, ParseFailed, ParseOk
from parsebench.schemas.result import Result
from parsebench.schemas.task import Task
from parsebench.schemas.types import RecordKind
from parsebench.schemas.upgrade import CURRENT_VERSIONS, RawRecord, upgrade

type AnyRecord = Document | Task | ParseOk | ParseFailed | AnswerOk | AnswerFailed | Result | RunManifest
"""Any of the six records (union variants listed separately)."""

_BOM = b"\xef\xbb\xbf"
_UNION_KINDS = frozenset({RecordKind.PARSE_RESULT, RecordKind.ANSWER})
_UNION_TAGS = frozenset({"ok", "failed"})
_TAG_ERRORS = frozenset({"union_tag_not_found", "union_tag_invalid"})

_VALIDATORS: Mapping[RecordKind, Callable[[str], AnyRecord]] = MappingProxyType(
    {
        RecordKind.DOCUMENT: Document.model_validate_json,
        RecordKind.TASK: Task.model_validate_json,
        RecordKind.PARSE_RESULT: PARSE_RESULT.validate_json,
        RecordKind.ANSWER: ANSWER.validate_json,
        RecordKind.RESULT: Result.model_validate_json,
        RecordKind.RUN_MANIFEST: RunManifest.model_validate_json,
    }
)


class _DuplicateKey(Exception):
    def __init__(self, key: str) -> None:
        self.key = key


class _BadConstant(Exception):
    pass


def kind_of(record: AnyRecord) -> RecordKind:
    """Return the record kind of a record instance."""
    match record:
        case Document():
            return RecordKind.DOCUMENT
        case Task():
            return RecordKind.TASK
        case ParseOk() | ParseFailed():
            return RecordKind.PARSE_RESULT
        case AnswerOk() | AnswerFailed():
            return RecordKind.ANSWER
        case Result():
            return RecordKind.RESULT
        case RunManifest():
            return RecordKind.RUN_MANIFEST


def record_key(record: AnyRecord) -> tuple[str, ...]:
    """Return the record's identity: its ID, or (run_id, doc or task ID, parser_id) for rows."""
    match record:
        case Document():
            return (record.doc_id,)
        case Task():
            return (record.task_id,)
        case ParseOk() | ParseFailed():
            return (record.run_id, record.doc_id, record.parser_id)
        case AnswerOk() | AnswerFailed() | Result():
            return (record.run_id, record.task_id, record.parser_id)
        case RunManifest():
            return (record.run_id,)


def dump_jsonl(records: Iterable[AnyRecord]) -> bytes:
    """Return canonical JSON lines, one per record, sorted by ID, each ending in `\\n`.

    All records must be the same kind. No records gives empty bytes.
    """
    items = tuple(records)
    if len({kind_of(r) for r in items}) > 1:
        raise TypeError("dump_jsonl takes records of one kind only")
    ordered = sorted(items, key=record_key)
    return b"".join(canonical_json(r) + b"\n" for r in ordered)


def _no_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    seen: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey(key)
        seen[key] = value
    return seen


def _reject_constant(_name: str) -> NoReturn:
    raise _BadConstant


def _schema_error(err: ValidationError, kind: RecordKind, source: str, line: int | None) -> SchemaError:
    errors = err.errors(include_input=False, include_url=False)
    first = errors[0]
    loc = [str(part) for part in first["loc"]]
    if kind in _UNION_KINDS and loc and loc[0] in _UNION_TAGS:
        loc = loc[1:]
    if first["type"] in _TAG_ERRORS:
        ctx = first.get("ctx") or {}
        loc = [*loc, str(ctx.get("discriminator", "status")).strip("'")]
    message = first["msg"]
    if len(errors) > 1:
        message = f"{message} (and {len(errors) - 1} more errors)"
    return SchemaError(message, source=source, line=line, field=".".join(loc) or None)


def _load_object(text: str, source: str, line: int | None) -> RawRecord:
    try:
        parsed: object = json.loads(
            text, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant
        )
    except _DuplicateKey as dup:
        raise SchemaError("duplicate key", source=source, line=line, field=dup.key) from None
    except _BadConstant:
        raise SchemaError("NaN and Infinity are not allowed", source=source, line=line) from None
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"invalid JSON: {exc.msg} (column {exc.colno})", source=source, line=line
        ) from None
    if not isinstance(parsed, dict):
        raise SchemaError("a record must be a JSON object", source=source, line=line)
    return cast(RawRecord, parsed)


def validate_raw(kind: RecordKind, data: RawRecord, source: str, line: int | None = None) -> AnyRecord:
    """Upgrade a parsed JSON dict, then validate it strictly as a record of `kind`.

    This is the single validation path every reader (JSON lines, JSON, Arrow,
    `build`) goes through. Raises `SchemaError` or `UnknownSchemaVersion`.
    """
    try:
        current = upgrade(kind, data)
    except SchemaError as exc:
        raise type(exc)(exc.message, source=source, line=line, field=exc.field) from None
    try:
        return _VALIDATORS[kind](json.dumps(current, ensure_ascii=False, allow_nan=False))
    except ValidationError as err:
        raise _schema_error(err, kind, source, line) from None


def _decode(data: bytes, source: str) -> str:
    if data.startswith(_BOM):
        raise SchemaError("a UTF-8 BOM is not allowed", source=source, line=1)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise SchemaError("not valid UTF-8", source=source) from None


@overload
def parse_jsonl(data: bytes, kind: Literal[RecordKind.DOCUMENT], source: str) -> tuple[Document, ...]: ...
@overload
def parse_jsonl(data: bytes, kind: Literal[RecordKind.TASK], source: str) -> tuple[Task, ...]: ...
@overload
def parse_jsonl(
    data: bytes, kind: Literal[RecordKind.PARSE_RESULT], source: str
) -> tuple[ParseOk | ParseFailed, ...]: ...
@overload
def parse_jsonl(
    data: bytes, kind: Literal[RecordKind.ANSWER], source: str
) -> tuple[AnswerOk | AnswerFailed, ...]: ...
@overload
def parse_jsonl(data: bytes, kind: Literal[RecordKind.RESULT], source: str) -> tuple[Result, ...]: ...
@overload
def parse_jsonl(data: bytes, kind: Literal[RecordKind.RUN_MANIFEST], source: str) -> tuple[RunManifest, ...]: ...
@overload
def parse_jsonl(data: bytes, kind: RecordKind, source: str) -> tuple[AnyRecord, ...]: ...
def parse_jsonl(data: bytes, kind: RecordKind, source: str) -> tuple[AnyRecord, ...]:
    """Validate JSON lines bytes into records of `kind`.

    Lines must end in `\\n` (no `\\r`, no blank lines, a final newline). Raises
    `SchemaError` (with `source`, 1 based `line`, and `field`) or
    `UnknownSchemaVersion`.
    """
    text = _decode(data, source)
    if not text:
        return ()
    if "\r" in text:
        line = text[: text.index("\r")].count("\n") + 1
        raise SchemaError("only \\n line endings are allowed", source=source, line=line)
    if not text.endswith("\n"):
        raise SchemaError("missing final newline", source=source, line=text.count("\n") + 1)
    records: list[AnyRecord] = []
    for number, line_text in enumerate(text[:-1].split("\n"), start=1):
        if not line_text:
            raise SchemaError("blank lines are not allowed", source=source, line=number)
        records.append(validate_raw(kind, _load_object(line_text, source, number), source, number))
    return tuple(records)


@overload
def parse_json(data: bytes, kind: Literal[RecordKind.DOCUMENT], source: str) -> Document: ...
@overload
def parse_json(data: bytes, kind: Literal[RecordKind.TASK], source: str) -> Task: ...
@overload
def parse_json(data: bytes, kind: Literal[RecordKind.PARSE_RESULT], source: str) -> ParseOk | ParseFailed: ...
@overload
def parse_json(data: bytes, kind: Literal[RecordKind.ANSWER], source: str) -> AnswerOk | AnswerFailed: ...
@overload
def parse_json(data: bytes, kind: Literal[RecordKind.RESULT], source: str) -> Result: ...
@overload
def parse_json(data: bytes, kind: Literal[RecordKind.RUN_MANIFEST], source: str) -> RunManifest: ...
@overload
def parse_json(data: bytes, kind: RecordKind, source: str) -> AnyRecord: ...
def parse_json(data: bytes, kind: RecordKind, source: str) -> AnyRecord:
    """Validate one JSON document (such as `manifest.json`) into a record of `kind`."""
    return validate_raw(kind, _load_object(_decode(data, source), source, None), source, None)


@overload
def build(kind: Literal[RecordKind.DOCUMENT], data: RawRecord) -> Document: ...
@overload
def build(kind: Literal[RecordKind.TASK], data: RawRecord) -> Task: ...
@overload
def build(kind: Literal[RecordKind.PARSE_RESULT], data: RawRecord) -> ParseOk | ParseFailed: ...
@overload
def build(kind: Literal[RecordKind.ANSWER], data: RawRecord) -> AnswerOk | AnswerFailed: ...
@overload
def build(kind: Literal[RecordKind.RESULT], data: RawRecord) -> Result: ...
@overload
def build(kind: Literal[RecordKind.RUN_MANIFEST], data: RawRecord) -> RunManifest: ...
@overload
def build(kind: RecordKind, data: RawRecord) -> AnyRecord: ...
def build(kind: RecordKind, data: RawRecord) -> AnyRecord:
    """Validate a plain dict (strings for enums and dates) through the JSON path.

    A missing `schema_version` means the current version, so builders can omit it.
    """
    stamped: RawRecord = {"schema_version": CURRENT_VERSIONS[kind], **data}
    return validate_raw(kind, stamped, "<build>", None)

