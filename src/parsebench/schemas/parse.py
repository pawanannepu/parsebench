"""ParseResult: one parser's output for one document in one run, ok or failed."""

from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from parsebench.schemas.base import Record
from parsebench.schemas.types import (
    RAW_FORMAT_EXTENSIONS,
    Attempts,
    Count,
    DocId,
    HttpStatus,
    Message,
    ParseErrorKind,
    ParserId,
    RawFormat,
    RelPath,
    RunId,
    Sha256,
    Usd,
)


def raw_parse_path(parser_id: str, doc_id: str, raw_format: RawFormat) -> str:
    """Return the run relative path where a parser's text output for a document lives."""
    return f"raw/parse/{parser_id}/{doc_id}.{RAW_FORMAT_EXTENSIONS[raw_format]}"


class ParseBase(Record):
    """Fields shared by both ParseResult variants, keyed by (run_id, doc_id, parser_id)."""

    run_id: RunId
    doc_id: DocId
    parser_id: ParserId
    latency_ms: Count
    attempts: Attempts


class ParseOk(ParseBase):
    """A successful parse. The text lives at `raw_path` and hashes to `raw_sha256`.

    `cost_usd` is None when the vendor did not report a cost; local parsers write 0.
    """

    status: Literal["ok"]
    raw_path: RelPath
    raw_sha256: Sha256
    raw_format: RawFormat
    cost_usd: Usd | None

    @model_validator(mode="after")
    def _raw_path_follows_layout(self) -> Self:
        if self.raw_path != raw_parse_path(self.parser_id, self.doc_id, self.raw_format):
            raise ValueError("raw_path must be raw/parse/<parser_id>/<doc_id>.<txt|md>")
        return self


class ParseFailed(ParseBase):
    """A failed parse: why it failed, a redacted message, and the HTTP status if any."""

    status: Literal["failed"]
    error_kind: ParseErrorKind
    message: Message
    http_status: HttpStatus | None


ParseResult = Annotated[ParseOk | ParseFailed, Field(discriminator="status")]
"""Either variant, discriminated on `status`."""

PARSE_RESULT: TypeAdapter[ParseOk | ParseFailed] = TypeAdapter(ParseResult)
"""Validates a ParseResult of either variant."""
