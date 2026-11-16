"""Explicit Arrow schemas for the row records (ParseResult, Answer, Result) and row converters.

Union variants are flattened under `status`. Columns both variants share are
non nullable; columns one variant owns are nullable. On read, `from_arrow_row`
keeps exactly the columns of the variant `status` names (never stripping by
None, since `cost_usd=None` and `http_status=None` are real values), turns
Decimals into fixed point strings, then takes the codec's JSON path.
"""

from collections.abc import Iterable, Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, overload

import pyarrow as pa

from parsebench.errors import SchemaError
from parsebench.schemas.answer import AnswerFailed, AnswerOk
from parsebench.schemas.base import Record
from parsebench.schemas.codec import AnyRecord, kind_of, validate_raw
from parsebench.schemas.parse import ParseFailed, ParseOk
from parsebench.schemas.result import Result
from parsebench.schemas.types import RecordKind
from parsebench.schemas.upgrade import RawRecord

type RowRecord = ParseOk | ParseFailed | AnswerOk | AnswerFailed | Result
"""A record stored as a Parquet row."""

type ArrowValue = str | int | bool | Decimal | None
"""A value in an Arrow ready row dict."""


def _req(name: str, type_: pa.DataType) -> "pa.Field[pa.DataType]":
    return pa.field(name, type_, nullable=False)


def _opt(name: str, type_: pa.DataType) -> "pa.Field[pa.DataType]":
    return pa.field(name, type_, nullable=True)


_STR = pa.string()
_INT = pa.int64()

PARSE_RESULT_ARROW: pa.Schema = pa.schema(
    [
        _req("schema_version", _INT),
        _req("run_id", _STR),
        _req("doc_id", _STR),
        _req("parser_id", _STR),
        _req("latency_ms", _INT),
        _req("attempts", _INT),
        _req("status", _STR),
        _opt("raw_path", _STR),
        _opt("raw_sha256", _STR),
        _opt("raw_format", _STR),
        _opt("cost_usd", pa.decimal128(18, 6)),
        _opt("error_kind", _STR),
        _opt("message", _STR),
        _opt("http_status", _INT),
    ]
)
"""Arrow schema for ParseResult rows (both variants)."""

ANSWER_ARROW: pa.Schema = pa.schema(
    [
        _req("schema_version", _INT),
        _req("run_id", _STR),
        _req("task_id", _STR),
        _req("doc_id", _STR),
        _req("parser_id", _STR),
        _req("latency_ms", _INT),
        _req("attempts", _INT),
        _req("status", _STR),
        _opt("answer_text", _STR),
        _opt("prompt_sha256", _STR),
        _opt("input_sha256", _STR),
        _opt("truncated", pa.bool_()),
        _opt("input_tokens", _INT),
        _opt("output_tokens", _INT),
        _opt("raw_call_path", _STR),
        _opt("raw_call_sha256", _STR),
        _opt("error_kind", _STR),
        _opt("message", _STR),
        _opt("http_status", _INT),
    ]
)
"""Arrow schema for Answer rows (both variants)."""

RESULT_ARROW: pa.Schema = pa.schema(
    [
        _req("schema_version", _INT),
        _req("run_id", _STR),
        _req("task_id", _STR),
        _req("doc_id", _STR),
        _req("parser_id", _STR),
        _req("outcome", _STR),
        _opt("normalized_answer", _STR),
        _req("normalized_gold", _STR),
        _req("scorer_version", _STR),
    ]
)
"""Arrow schema for Result rows."""

ARROW_SCHEMAS: Mapping[RecordKind, pa.Schema] = MappingProxyType(
    {
        RecordKind.PARSE_RESULT: PARSE_RESULT_ARROW,
        RecordKind.ANSWER: ANSWER_ARROW,
        RecordKind.RESULT: RESULT_ARROW,
    }
)
"""Arrow schema of each row record kind."""

_VARIANTS: Mapping[RecordKind, Mapping[str, type[Record]]] = MappingProxyType(
    {
        RecordKind.PARSE_RESULT: MappingProxyType({"ok": ParseOk, "failed": ParseFailed}),
        RecordKind.ANSWER: MappingProxyType({"ok": AnswerOk, "failed": AnswerFailed}),
    }
)


def _schema_for(kind: RecordKind, source: str) -> pa.Schema:
    schema = ARROW_SCHEMAS.get(kind)
    if schema is None:
        raise SchemaError(f"{kind.value} is not stored as Arrow rows", source=source)
    return schema


def to_arrow_row(record: RowRecord) -> dict[str, ArrowValue]:
    """Return an Arrow ready dict with every column of the record's schema.

    The other variant's columns are None, and `cost_usd` is a `Decimal`.
    """
    schema = _schema_for(kind_of(record), "<arrow>")
    dumped = record.model_dump(mode="json")
    row: dict[str, ArrowValue] = {}
    for name in schema.names:
        value = dumped.get(name)
        if name == "cost_usd" and isinstance(value, str):
            row[name] = Decimal(value)
        elif value is None or isinstance(value, str | int | bool):
            row[name] = value
        else:
            raise SchemaError("column value is not a scalar", source="<arrow>", field=name)
    return row


def _columns_for(kind: RecordKind, row: Mapping[str, object], source: str, line: int | None) -> frozenset[str]:
    variants = _VARIANTS.get(kind)
    if variants is None:
        return frozenset(Result.model_fields)
    status = row.get("status")
    model = variants.get(status) if isinstance(status, str) else None
    if model is None:
        raise SchemaError("status must be 'ok' or 'failed'", source=source, line=line, field="status")
    return frozenset(model.model_fields)


def _json_value(value: object, name: str, source: str, line: int | None) -> str | int | bool | None:
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None or isinstance(value, str | int | bool):
        return value
    raise SchemaError("unsupported Arrow value type", source=source, line=line, field=name)


@overload
def from_arrow_row(
    kind: Literal[RecordKind.PARSE_RESULT], row: Mapping[str, object], *, source: str = ..., line: int | None = ...
) -> ParseOk | ParseFailed: ...
@overload
def from_arrow_row(
    kind: Literal[RecordKind.ANSWER], row: Mapping[str, object], *, source: str = ..., line: int | None = ...
) -> AnswerOk | AnswerFailed: ...
@overload
def from_arrow_row(
    kind: Literal[RecordKind.RESULT], row: Mapping[str, object], *, source: str = ..., line: int | None = ...
) -> Result: ...
@overload
def from_arrow_row(
    kind: RecordKind, row: Mapping[str, object], *, source: str = ..., line: int | None = ...
) -> AnyRecord: ...
def from_arrow_row(
    kind: RecordKind, row: Mapping[str, object], *, source: str = "<arrow>", line: int | None = None
) -> AnyRecord:
    """Validate one Arrow row dict as a record of `kind`, through the codec's JSON path."""
    _schema_for(kind, source)
    keep = _columns_for(kind, row, source, line)
    data: RawRecord = {
        name: _json_value(value, name, source, line) for name, value in row.items() if name in keep
    }
    return validate_raw(kind, data, source, line)


def to_arrow_table(kind: RecordKind, records: Iterable[RowRecord]) -> pa.Table:
    """Return the records as a table with the kind's explicit Arrow schema."""
    schema = _schema_for(kind, "<arrow>")
    rows: list[dict[str, ArrowValue]] = []
    for record in records:
        if kind_of(record) is not kind:
            raise TypeError(f"to_arrow_table({kind.value}) got a {kind_of(record).value} record")
        rows.append(to_arrow_row(record))
    try:
        return pa.Table.from_pylist(rows, schema=schema)
    except (pa.ArrowInvalid, pa.ArrowTypeError) as exc:
        raise SchemaError(f"cannot convert to Arrow ({type(exc).__name__})", source="<arrow>") from None


def from_arrow_table(kind: RecordKind, table: pa.Table, source: str = "<arrow>") -> tuple[AnyRecord, ...]:
    """Validate every row of a table as a record of `kind`. `line` in errors is the 1 based row."""
    _schema_for(kind, source)
    try:
        rows = table.to_pylist()
    except (pa.ArrowInvalid, pa.ArrowTypeError) as exc:
        raise SchemaError(f"cannot read Arrow table ({type(exc).__name__})", source=source) from None
    return tuple(from_arrow_row(kind, row, source=source, line=n) for n, row in enumerate(rows, start=1))
