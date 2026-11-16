"""Answer: the answering model's reply to one task on one parser's text, ok or failed."""

from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from parsebench.schemas.base import Record
from parsebench.schemas.types import (
    AnswerErrorKind,
    Attempts,
    Count,
    DocId,
    HttpStatus,
    Message,
    ParserId,
    RelPath,
    RunId,
    Sha256,
    TaskId,
)


def raw_answer_path(parser_id: str, task_id: str) -> str:
    """Return the run relative path of the archived answering call for a task."""
    return f"raw/answer/{parser_id}/{task_id}.json"


class AnswerBase(Record):
    """Fields shared by both Answer variants, keyed by (run_id, task_id, parser_id).

    `latency_ms` is the call time, or the time to failure.
    """

    run_id: RunId
    task_id: TaskId
    doc_id: DocId
    parser_id: ParserId
    latency_ms: Count
    attempts: Attempts


class AnswerOk(AnswerBase):
    """A model reply. The raw request and response are archived at `raw_call_path`.

    `prompt_sha256` hashes the prompt template; `input_sha256` hashes the
    truncated text actually sent. `answer_text` may be empty (graded incorrect).
    """

    status: Literal["ok"]
    answer_text: str
    prompt_sha256: Sha256
    input_sha256: Sha256
    truncated: bool
    input_tokens: Count
    output_tokens: Count
    raw_call_path: RelPath
    raw_call_sha256: Sha256

    @model_validator(mode="after")
    def _raw_call_path_follows_layout(self) -> Self:
        if self.raw_call_path != raw_answer_path(self.parser_id, self.task_id):
            raise ValueError("raw_call_path must be raw/answer/<parser_id>/<task_id>.json")
        return self


class AnswerFailed(AnswerBase):
    """A failed answering call: why it failed, a redacted message, and the HTTP status if any."""

    status: Literal["failed"]
    error_kind: AnswerErrorKind
    message: Message
    http_status: HttpStatus | None


Answer = Annotated[AnswerOk | AnswerFailed, Field(discriminator="status")]
"""Either variant, discriminated on `status`."""

ANSWER: TypeAdapter[AnswerOk | AnswerFailed] = TypeAdapter(Answer)
"""Validates an Answer of either variant."""
