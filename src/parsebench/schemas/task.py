"""Task: one question about one document, with its gold answer."""

from typing import Self

from pydantic import model_validator

from parsebench.schemas.base import Record
from parsebench.schemas.types import AnswerType, DocId, TaskId, Text, task_id_matches_doc


class Task(Record):
    """A question about one document, keyed by `task_id` (`<doc_id>-qNN`).

    `gold` is the canonical answer for its `answer_type` (feature 7 defines the
    canonical forms). `source_ref` says where in the source data the answer lives.
    """

    task_id: TaskId
    doc_id: DocId
    question: Text
    answer_type: AnswerType
    gold: Text
    source_ref: Text

    @model_validator(mode="after")
    def _task_id_belongs_to_doc(self) -> Self:
        if not task_id_matches_doc(self.task_id, self.doc_id):
            raise ValueError("task_id must be '<doc_id>-q' followed by two or more digits")
        return self
