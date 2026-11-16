"""Result: the graded outcome of one task on one parser in one run."""

from typing import Self

from pydantic import model_validator

from parsebench.schemas.base import Record
from parsebench.schemas.types import FAILED_OUTCOMES, DocId, Outcome, ParserId, RunId, SemVer, TaskId


class Result(Record):
    """Graded outcome keyed by (run_id, task_id, parser_id).

    `normalized_answer` is None exactly when the outcome is `parse_failed` or
    `answer_failed`. `normalized_gold` is always filled, since the normalizer
    runs on gold even for failed rows.
    """

    run_id: RunId
    task_id: TaskId
    doc_id: DocId
    parser_id: ParserId
    outcome: Outcome
    normalized_answer: str | None
    normalized_gold: str
    scorer_version: SemVer

    @model_validator(mode="after")
    def _answer_presence_matches_outcome(self) -> Self:
        if (self.normalized_answer is None) != (self.outcome in FAILED_OUTCOMES):
            raise ValueError("normalized_answer must be None exactly when the outcome is a failure")
        return self
