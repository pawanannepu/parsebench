"""Pure cross record checks. Each raises `IntegrityError` listing the offending IDs.

A failed check is a broken invariant, not an expected failure, so these raise
instead of returning a bool. They gather every problem before raising, so one
run shows the whole picture.
"""

from collections import Counter
from collections.abc import Iterable, Sequence

from parsebench.errors import IntegrityError
from parsebench.schemas.answer import AnswerFailed, AnswerOk
from parsebench.schemas.canonical import sha256_hex
from parsebench.schemas.document import Document
from parsebench.schemas.manifest import RunManifest
from parsebench.schemas.parse import ParseFailed, ParseOk
from parsebench.schemas.result import Result
from parsebench.schemas.task import Task
from parsebench.schemas.types import FAILED_OUTCOMES, Outcome, Sha256


def _raise_if(problems: Sequence[str], message: str) -> None:
    if problems:
        raise IntegrityError(message, ids=tuple(problems))


def _duplicates[K](keys: Iterable[K]) -> list[K]:
    return sorted((k for k, n in Counter(keys).items() if n > 1), key=str)


def _pair(*parts: str) -> str:
    return "/".join(parts)


def check_task_set(docs: Sequence[Document], tasks: Sequence[Task]) -> None:
    """Check IDs are unique and every Task points at an existing Document."""
    doc_ids = {d.doc_id for d in docs}
    problems = [
        *(f"duplicate doc_id {d}" for d in _duplicates(d.doc_id for d in docs)),
        *(f"duplicate task_id {t}" for t in _duplicates(t.task_id for t in tasks)),
        *(f"task {t.task_id} has unknown doc_id {t.doc_id}" for t in tasks if t.doc_id not in doc_ids),
    ]
    _raise_if(problems, "task set is inconsistent")


def _expected_outcomes(parse: ParseOk | ParseFailed | None, answer: AnswerOk | AnswerFailed | None) -> frozenset[Outcome]:
    match parse, answer:
        case ParseFailed(), None:
            return frozenset({Outcome.PARSE_FAILED})
        case ParseOk(), AnswerFailed():
            return frozenset({Outcome.ANSWER_FAILED})
        case ParseOk(), AnswerOk():
            return frozenset({Outcome.CORRECT, Outcome.INCORRECT})
        case _:
            return frozenset()


def check_result_consistency(
    manifest: RunManifest,
    tasks: Sequence[Task],
    parses: Sequence[ParseOk | ParseFailed],
    answers: Sequence[AnswerOk | AnswerFailed],
    results: Sequence[Result],
) -> None:
    """Check one run's rows agree with each other, the task set, and the manifest."""
    run_id = manifest.run_id
    parser_ids = {p.parser_id for p in manifest.parsers}
    task_docs = {t.task_id: t.doc_id for t in tasks}
    rows: tuple[ParseOk | ParseFailed | AnswerOk | AnswerFailed | Result, ...] = (*parses, *answers, *results)
    problems: list[str] = []

    for row in rows:
        ident = _pair(row.doc_id if isinstance(row, ParseOk | ParseFailed) else row.task_id, row.parser_id)
        if row.run_id != run_id:
            problems.append(f"{ident} has run_id {row.run_id}, manifest has {run_id}")
        if row.parser_id not in parser_ids:
            problems.append(f"{ident} has parser_id {row.parser_id} not in the manifest")

    problems += [f"two ParseResults for {_pair(*k)}" for k in _duplicates((p.doc_id, p.parser_id) for p in parses)]
    problems += [f"two Answers for {_pair(*k)}" for k in _duplicates((a.task_id, a.parser_id) for a in answers)]

    parse_by = {(p.doc_id, p.parser_id): p for p in parses}
    answer_by = {(a.task_id, a.parser_id): a for a in answers}

    for row in (*answers, *results):
        ident = _pair(row.task_id, row.parser_id)
        expected_doc = task_docs.get(row.task_id)
        if expected_doc is None:
            problems.append(f"{ident} has unknown task_id")
        elif row.doc_id != expected_doc:
            problems.append(f"{ident} has doc_id {row.doc_id}, its task has {expected_doc}")

    for answer in answers:
        if not isinstance(parse_by.get((answer.doc_id, answer.parser_id)), ParseOk):
            problems.append(f"answer {_pair(answer.task_id, answer.parser_id)} has no ok ParseResult")

    for result in results:
        ident = _pair(result.task_id, result.parser_id)
        parse = parse_by.get((result.doc_id, result.parser_id))
        answer = answer_by.get((result.task_id, result.parser_id))
        if result.outcome not in _expected_outcomes(parse, answer):
            problems.append(f"result {ident} outcome {result.outcome.value} disagrees with its parse and answer")
        if (result.normalized_answer is None) != (result.outcome in FAILED_OUTCOMES):
            problems.append(f"result {ident} normalized_answer presence disagrees with its outcome")

    _raise_if(problems, "run records are inconsistent")


def check_run_complete(manifest: RunManifest, tasks: Sequence[Task], results: Sequence[Result]) -> None:
    """Check there is exactly one Result per (task, parser) and none for unknown pairs."""
    expected = {(t.task_id, p.parser_id) for t in tasks for p in manifest.parsers}
    counts = Counter((r.task_id, r.parser_id) for r in results)
    problems = [
        *(f"missing result {_pair(*k)}" for k in sorted(expected - counts.keys())),
        *(f"duplicate result {_pair(*k)}" for k in sorted(k for k, n in counts.items() if n > 1)),
        *(f"unknown result {_pair(*k)}" for k in sorted(counts.keys() - expected)),
    ]
    _raise_if(problems, "run is incomplete")


def verify_raw(path_bytes: bytes, expected: Sha256) -> None:
    """Check bytes the caller read from a raw file hash to the sha256 its record names."""
    actual = sha256_hex(path_bytes)
    if actual != expected:
        raise IntegrityError("raw file bytes do not match their sha256", ids=(expected,))
