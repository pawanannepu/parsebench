"""Constrained field types and enums shared by every record.

Each type validates its own shape (patterns, ranges, UTC, fixed point money),
so a record can only hold well formed values. Validator messages never repeat
the input value.
"""

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, Field, PlainSerializer

INT64_MAX = 2**63 - 1
"""Largest value an Arrow `int64` column holds."""

MESSAGE_MAX_CHARS = 2000
"""Cap on an error `message`, so vendor error bodies stay short."""

_USD_QUANTUM = Decimal("0.000001")


def _check_rel_path(value: str) -> str:
    if any(segment in {".", ".."} for segment in value.split("/")):
        raise ValueError("path segments may not be '.' or '..'")
    return value


def _check_run_id_date(value: str) -> str:
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError("run_id must start with a real date") from None
    return value


def _check_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("datetime must be in UTC (offset zero)")
    return value.astimezone(UTC)


def _quantize_usd(value: Decimal) -> Decimal:
    return value.quantize(_USD_QUANTUM)


def _check_trimmed(value: str) -> str:
    if value != value.strip():
        raise ValueError("text may not have leading or trailing whitespace")
    return value


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
"""Lowercase hex sha256 digest."""

DocId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)]
"""Document ID, lowercase words joined by single hyphens."""

TaskId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-q[0-9]{2,}$", max_length=80)]
"""Task ID, `<doc_id>-q<NN>`. Task also checks the prefix equals its doc_id."""

ParserId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")]
"""Parser ID such as `pymupdf` or `docling`."""

RunId = Annotated[
    str,
    Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{8}$"),
    AfterValidator(_check_run_id_date),
]
"""Run ID, `YYYY-MM-DD-<8 hex>`, with a real date."""

SemVer = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
"""`MAJOR.MINOR.PATCH` version string."""

RelPath = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"),
    AfterValidator(_check_rel_path),
]
"""POSIX path relative to a run folder, with no `.` or `..` segment."""

UtcDatetime = Annotated[AwareDatetime, AfterValidator(_check_utc)]
"""Timezone aware datetime whose offset is zero, serialized ending in `Z`."""

Usd = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=6),
    AfterValidator(_quantize_usd),
    PlainSerializer(lambda d: format(d, "f"), return_type=str, when_used="json"),
]
"""US dollars, exactly 6 decimal places, serialized as a fixed point string."""

HttpUrlStr = Annotated[str, Field(pattern=r"^https?://\S+$")]
"""HTTP(S) URL kept exactly as written, so no normalization touches hashed bytes."""

GitRevision = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
"""Full 40 character git commit SHA."""

Count = Annotated[int, Field(ge=0, le=INT64_MAX)]
"""Non negative count or millisecond duration that fits Arrow `int64`."""

Attempts = Annotated[int, Field(ge=1, le=INT64_MAX)]
"""Number of tries, at least one."""

HttpStatus = Annotated[int, Field(ge=100, le=599)]
"""HTTP status code."""

Text = Annotated[str, Field(min_length=1), AfterValidator(_check_trimmed)]
"""Non empty text with no leading or trailing whitespace (rejected, never stripped)."""

Name = Annotated[str, Field(min_length=1)]
"""Short non empty label such as a package or provider name."""

Message = Annotated[str, Field(max_length=MESSAGE_MAX_CHARS)]
"""Redacted error message, at most 2000 characters."""


class RecordKind(StrEnum):
    """Names the six record types in the codec, upgrade, and Arrow APIs."""

    DOCUMENT = "document"
    TASK = "task"
    PARSE_RESULT = "parse_result"
    ANSWER = "answer"
    RESULT = "result"
    RUN_MANIFEST = "run_manifest"


class DocType(StrEnum):
    """Kind of document. Release 1 has invoices only."""

    INVOICE = "invoice"


class AnswerType(StrEnum):
    """How a Task's gold answer is normalized and compared (feature 7)."""

    NUMBER = "number"
    CURRENCY = "currency"
    DATE = "date"
    TEXT = "text"


class RawFormat(StrEnum):
    """Format of a parser's stored text output."""

    TEXT = "text"
    MARKDOWN = "markdown"


RAW_FORMAT_EXTENSIONS: Mapping[RawFormat, str] = MappingProxyType(
    {RawFormat.TEXT: "txt", RawFormat.MARKDOWN: "md"}
)
"""File extension for each raw format (read only)."""


class TruncationKind(StrEnum):
    """How parser text is cut before it reaches the answering model."""

    HEAD_CHARS = "head_chars"


class ParseErrorKind(StrEnum):
    """Why a parse failed."""

    TIMEOUT = "timeout"
    PARSER_ERROR = "parser_error"
    VENDOR_HTTP = "vendor_http"
    CRASH = "crash"


class AnswerErrorKind(StrEnum):
    """Why an answering call failed."""

    TIMEOUT = "timeout"
    PROVIDER_HTTP = "provider_http"
    TRANSPORT = "transport"
    MALFORMED_RESPONSE = "malformed_response"


class Outcome(StrEnum):
    """Final grade of one (task, parser) pair."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARSE_FAILED = "parse_failed"
    ANSWER_FAILED = "answer_failed"


FAILED_OUTCOMES = frozenset({Outcome.PARSE_FAILED, Outcome.ANSWER_FAILED})
"""Outcomes with no answer to normalize."""


def task_id_matches_doc(task_id: str, doc_id: str) -> bool:
    """Return whether `task_id` is exactly `<doc_id>-q` plus two or more digits."""
    return re.fullmatch(rf"{re.escape(doc_id)}-q[0-9]{{2,}}", task_id) is not None
