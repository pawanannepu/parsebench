"""Core schemas (spec 0002): strict records, codec, integrity, versioning, and Arrow."""

import json
import random
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest
from pydantic import JsonValue, ValidationError

from parsebench.errors import IntegrityError, SchemaError, UnknownSchemaVersion
from parsebench.schemas import (
    CURRENT_VERSIONS,
    AnswerErrorKind,
    AnswerFailed,
    AnsweringConfig,
    AnswerOk,
    AnswerType,
    DocType,
    Document,
    Environment,
    Knobs,
    Outcome,
    ParseErrorKind,
    ParseFailed,
    ParseOk,
    ParserInfo,
    RawFormat,
    RecordKind,
    Result,
    RunManifest,
    SettingEntry,
    SyntheticOrigin,
    Task,
    TaskSetRef,
    TruncationKind,
    TruncationRule,
    build,
    canonical_json,
    check_result_consistency,
    check_run_complete,
    check_task_set,
    current_schema_versions,
    dump_jsonl,
    from_arrow_table,
    parse_json,
    parse_jsonl,
    settings_snapshot,
    sha256_hex,
    task_set_sha256,
    to_arrow_table,
    upgrade,
    verify_raw,
)
from parsebench.errors import ParseBenchError
from parsebench.schemas import (
    ANSWER_ARROW,
    ARROW_SCHEMAS,
    PARSE_RESULT_ARROW,
    RESULT_ARROW,
    SECRET_SETTING_NAMES,
    ModelRevision,
    RealOrigin,
    ToolVersion,
    from_arrow_row,
    kind_of,
    raw_answer_path,
    raw_parse_path,
    record_key,
    to_arrow_row,
)
from parsebench.schemas.snapshot import SNAPSHOT_DIR, live_schema, snapshot_name, snapshot_text, write_snapshots
from parsebench.settings import Settings

RUN = "2026-11-16-0123abcd"
H = "a" * 64
DOC = "inv-0001"
RAW_TEXT = b"Invoice INV-1\nTotal: 120.50 USD\n"
RAW_CALL = b'{"request": {}, "response": {"answer": "120.50"}}'


def make_doc(doc_id: str = DOC) -> Document:
    return Document(
        doc_id=doc_id,
        sha256=H,
        doc_type=DocType.INVOICE,
        pages=1,
        knobs=Knobs(tables=True),
        provenance=SyntheticOrigin(
            origin="synthetic", generator="invoice", generator_version="1.0.0", seed=0, source_data_sha256=H
        ),
    )


def make_task(n: int, gold: str, doc_id: str = DOC) -> Task:
    return Task(
        task_id=f"{doc_id}-q{n:02d}",
        doc_id=doc_id,
        question=f"Question {n}?",
        answer_type=AnswerType.TEXT,
        gold=gold,
        source_ref=f"fields.q{n}",
    )


def make_parse_ok(parser_id: str = "pymupdf", cost: Decimal | None = Decimal("0")) -> ParseOk:
    return ParseOk(
        run_id=RUN,
        doc_id=DOC,
        parser_id=parser_id,
        latency_ms=12,
        attempts=1,
        status="ok",
        raw_path=f"raw/parse/{parser_id}/{DOC}.txt",
        raw_sha256=sha256_hex(RAW_TEXT),
        raw_format=RawFormat.TEXT,
        cost_usd=cost,
    )


def make_parse_failed(parser_id: str = "docling", http_status: int | None = None) -> ParseFailed:
    return ParseFailed(
        run_id=RUN,
        doc_id=DOC,
        parser_id=parser_id,
        latency_ms=30000,
        attempts=2,
        status="failed",
        error_kind=ParseErrorKind.TIMEOUT,
        message="timed out",
        http_status=http_status,
    )


def make_answer_ok(task: Task, text: str, parser_id: str = "pymupdf") -> AnswerOk:
    return AnswerOk(
        run_id=RUN,
        task_id=task.task_id,
        doc_id=task.doc_id,
        parser_id=parser_id,
        latency_ms=800,
        attempts=1,
        status="ok",
        answer_text=text,
        prompt_sha256=H,
        input_sha256=sha256_hex(RAW_TEXT),
        truncated=False,
        input_tokens=50,
        output_tokens=4,
        raw_call_path=f"raw/answer/{parser_id}/{task.task_id}.json",
        raw_call_sha256=sha256_hex(RAW_CALL),
    )


def make_manifest(parser_ids: tuple[str, ...] = ("pymupdf",)) -> RunManifest:
    return RunManifest(
        run_id=RUN,
        created_at=datetime(2026, 11, 16, 9, 30, tzinfo=UTC),
        seed=0,
        task_set=TaskSetRef(version="dev", sha256=H),
        scorer_version="1.0.0",
        answering=AnsweringConfig(
            provider="stub",
            model="stub-1",
            temperature=0.0,
            prompt_sha256=H,
            truncation=TruncationRule(kind=TruncationKind.HEAD_CHARS, limit=20000),
        ),
        parsers=tuple(
            ParserInfo(parser_id=p, package=p, package_version="1.0.0", extra=p, model_revisions=())
            for p in sorted(parser_ids)
        ),
        environment=Environment(
            python_version="3.12.13",
            os="macOS-15-arm64",
            cpu="arm64",
            threads=4,
            uv_lock_sha256=H,
            torch_version=None,
            system_tools=(),
        ),
        settings=(SettingEntry(name="cache_dir", value=".cache/parsebench"),),
        concurrency=1,
        schema_versions=current_schema_versions(),
    )


def stub_grade(
    task: Task, parse: ParseOk | ParseFailed, answer: AnswerOk | AnswerFailed | None
) -> Result:
    """Stand in grader: case insensitive exact match."""
    gold = task.gold.lower()
    base = {"run_id": parse.run_id, "task_id": task.task_id, "doc_id": task.doc_id, "parser_id": parse.parser_id}
    if isinstance(parse, ParseFailed):
        outcome, normalized = Outcome.PARSE_FAILED, None
    elif not isinstance(answer, AnswerOk):
        outcome, normalized = Outcome.ANSWER_FAILED, None
    else:
        normalized = answer.answer_text.strip().lower()
        outcome = Outcome.CORRECT if normalized == gold else Outcome.INCORRECT
    return Result(
        **base, outcome=outcome, normalized_answer=normalized, normalized_gold=gold, scorer_version="1.0.0"
    )


# AC-1, AC-5, AC-7, AC-8: the happy path end to end, plus the regrade from stored records.
def test_happy_path_validates_round_trips_and_regrades() -> None:
    doc = make_doc()
    tasks = (make_task(1, "120.50"), make_task(2, "ACME"))
    parse = make_parse_ok()
    answers = (make_answer_ok(tasks[0], "120.50"), make_answer_ok(tasks[1], "Globex"))
    results = tuple(stub_grade(t, parse, a) for t, a in zip(tasks, answers, strict=True))
    manifest = make_manifest()
    assert [r.outcome for r in results] == [Outcome.CORRECT, Outcome.INCORRECT]

    check_task_set((doc,), tasks)
    check_result_consistency(manifest, tasks, (parse,), answers, results)
    check_run_complete(manifest, tasks, results)

    # Store everything as files, then rebuild from the stored bytes alone.
    stored = {
        "documents.jsonl": dump_jsonl((doc,)),
        "tasks.jsonl": dump_jsonl(tasks),
        "parses.jsonl": dump_jsonl((parse,)),
        "answers.jsonl": dump_jsonl(answers),
        "manifest.json": canonical_json(manifest),
        parse.raw_path: RAW_TEXT,
    }
    s_tasks = parse_jsonl(stored["tasks.jsonl"], RecordKind.TASK, "tasks.jsonl")
    (s_parse,) = parse_jsonl(stored["parses.jsonl"], RecordKind.PARSE_RESULT, "parses.jsonl")
    s_answers = parse_jsonl(stored["answers.jsonl"], RecordKind.ANSWER, "answers.jsonl")
    assert parse_json(stored["manifest.json"], RecordKind.RUN_MANIFEST, "manifest.json") == manifest
    assert isinstance(s_parse, ParseOk)
    verify_raw(stored[s_parse.raw_path], s_parse.raw_sha256)

    answer_by_task = {a.task_id: a for a in s_answers}
    rebuilt = tuple(stub_grade(t, s_parse, answer_by_task[t.task_id]) for t in s_tasks)
    assert rebuilt == results


# AC-3, AC-5, AC-8: a failed parse yields parse_failed results with no answer.
def test_failed_parse_and_integrity_failures() -> None:
    tasks = (make_task(1, "120.50"),)
    failed = make_parse_failed(parser_id="pymupdf")
    good = stub_grade(tasks[0], failed, None)
    assert good.outcome is Outcome.PARSE_FAILED and good.normalized_answer is None
    manifest = make_manifest()
    check_result_consistency(manifest, tasks, (failed,), (), (good,))

    lying = good.model_copy(update={"outcome": Outcome.CORRECT, "normalized_answer": "120.50"})
    with pytest.raises(IntegrityError) as exc:
        check_result_consistency(manifest, tasks, (failed,), (), (lying,))
    assert any("inv-0001-q01" in i for i in exc.value.ids)

    flipped = bytes([RAW_TEXT[0] ^ 1]) + RAW_TEXT[1:]
    with pytest.raises(IntegrityError):
        verify_raw(flipped, sha256_hex(RAW_TEXT))


def test_cross_record_checks_name_offending_ids() -> None:
    with pytest.raises(IntegrityError) as exc:
        check_task_set((make_doc(), make_doc()), (make_task(1, "x", doc_id="inv-0002"),))
    assert any("duplicate doc_id inv-0001" in i for i in exc.value.ids)
    assert any("unknown doc_id inv-0002" in i for i in exc.value.ids)

    manifest = make_manifest()
    task = make_task(1, "x")
    other_run = make_parse_ok().model_copy(update={"run_id": "2026-11-15-ffffffff"})
    unknown_parser = make_parse_ok(parser_id="marker")
    orphan_answer = make_answer_ok(task, "x", parser_id="marker")
    with pytest.raises(IntegrityError) as exc:
        check_result_consistency(manifest, (task,), (other_run, unknown_parser), (orphan_answer,), ())
    joined = " ".join(exc.value.ids)
    assert "run_id 2026-11-15-ffffffff" in joined
    assert "parser_id marker not in the manifest" in joined

    with pytest.raises(IntegrityError) as exc:
        check_run_complete(make_manifest(("docling", "pymupdf")), (task,), (stub_grade(task, make_parse_failed("docling"), None),) * 2)
    joined = " ".join(exc.value.ids)
    assert "missing result inv-0001-q01/pymupdf" in joined
    assert "duplicate result inv-0001-q01/docling" in joined


# AC-3: the two shapes cannot mix.
def test_union_variants_cannot_mix() -> None:
    ok = make_parse_ok().model_dump()
    with pytest.raises(ValidationError):
        ParseOk.model_validate({**ok, "error_kind": ParseErrorKind.CRASH})
    failed = make_parse_failed().model_dump()
    with pytest.raises(ValidationError):
        ParseFailed.model_validate({**failed, "raw_path": "raw/parse/docling/inv-0001.txt"})
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.PARSE_RESULT, {**json.loads(canonical_json(make_parse_ok())), "status": "maybe"})
    assert exc.value.field == "status"


def _line(record_json: bytes, **changes: JsonValue) -> bytes:
    data = json.loads(record_json)
    data.update(changes)
    return json.dumps(data).encode() + b"\n"


MALFORMED: list[tuple[str, RecordKind, Callable[[], bytes], str]] = [
    ("int as string", RecordKind.DOCUMENT, lambda: _line(canonical_json(make_doc()), pages="12"), "pages"),
    ("unknown field", RecordKind.TASK, lambda: _line(canonical_json(make_task(1, "x")), bogus=1), "bogus"),
    ("uppercase sha", RecordKind.DOCUMENT, lambda: _line(canonical_json(make_doc()), sha256="A" * 64), "sha256"),
    ("dotdot path", RecordKind.PARSE_RESULT, lambda: _line(canonical_json(make_parse_ok()), raw_path="raw/parse/../x.txt"), "raw_path"),
    ("negative cost", RecordKind.PARSE_RESULT, lambda: _line(canonical_json(make_parse_ok()), cost_usd="-1"), "cost_usd"),
    ("naive datetime", RecordKind.RUN_MANIFEST, lambda: _line(canonical_json(make_manifest()), created_at="2026-11-16T09:30:00"), "created_at"),
    ("missing field", RecordKind.TASK, lambda: _line(canonical_json(make_task(1, "x")), gold=None), "gold"),
    ("negative latency", RecordKind.ANSWER, lambda: _line(canonical_json(make_answer_ok(make_task(1, "x"), "x")), latency_ms=-1), "latency_ms"),
]


# AC-1: malformed input names the field and line, never the value.
@pytest.mark.parametrize(("name", "kind", "payload", "field"), MALFORMED, ids=[m[0] for m in MALFORMED])
def test_malformed_input_is_rejected_with_field_and_line(
    name: str, kind: RecordKind, payload: Callable[[], bytes], field: str
) -> None:
    good_first = {
        RecordKind.DOCUMENT: dump_jsonl((make_doc("inv-0000"),)),
        RecordKind.TASK: dump_jsonl((make_task(9, "y"),)),
    }.get(kind, b"")
    data = good_first + payload()
    with pytest.raises(SchemaError) as exc:
        parse_jsonl(data, kind, "fixture.jsonl")
    assert exc.value.field == field, name
    assert exc.value.source == "fixture.jsonl"
    assert exc.value.line == (2 if good_first else 1)


def test_codec_rejects_duplicate_keys_nan_bom_and_blank_lines() -> None:
    line = canonical_json(make_task(1, "x"))
    with pytest.raises(SchemaError, match="duplicate key"):
        parse_jsonl(line[:-1] + b',"gold":"y"}\n', RecordKind.TASK, "t")
    with pytest.raises(SchemaError, match="NaN"):
        parse_jsonl(_line(canonical_json(make_manifest()))[:-2] + b',"x":NaN}\n', RecordKind.RUN_MANIFEST, "m")
    with pytest.raises(SchemaError, match="BOM"):
        parse_jsonl(b"\xef\xbb\xbf" + line + b"\n", RecordKind.TASK, "t")
    with pytest.raises(SchemaError, match="blank"):
        parse_jsonl(line + b"\n\n" + line + b"\n", RecordKind.TASK, "t")
    with pytest.raises(SchemaError, match="line endings"):
        parse_jsonl(line + b"\r\n", RecordKind.TASK, "t")


def test_errors_never_echo_input_values() -> None:
    leak = "LEAKME-7f3a9c"
    bad = _line(canonical_json(make_task(1, "x")), question=f" {leak} ")
    with pytest.raises(SchemaError) as exc:
        parse_jsonl(bad, RecordKind.TASK, "t")
    assert leak not in str(exc.value)
    with pytest.raises(ValidationError) as verr:
        Task.model_validate({**make_task(1, "x").model_dump(), "question": f" {leak} "})
    assert leak not in str(verr.value)


def test_records_are_frozen() -> None:
    task = make_task(1, "x")
    with pytest.raises(ValidationError):
        task.gold = "y"  # type: ignore[misc]


def test_task_id_must_match_doc_id() -> None:
    with pytest.raises(ValidationError):
        Task(
            task_id="inv-0002-q01",
            doc_id=DOC,
            question="Q?",
            answer_type=AnswerType.TEXT,
            gold="x",
            source_ref="r",
        )


# AC-2: versions newer than the code fail, older ones run the chain.
def test_upgrade_chain_and_unknown_versions() -> None:
    raw = json.loads(canonical_json(make_task(1, "x")))
    with pytest.raises(UnknownSchemaVersion):
        upgrade(RecordKind.TASK, {**raw, "schema_version": 2})
    for bad in (None, True, "1", 0):
        with pytest.raises(SchemaError):
            upgrade(RecordKind.TASK, {**raw, "schema_version": bad})

    def v1_to_v2(d: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return {**d, "note": "v2"}

    def v2_to_v3(d: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return {**d, "note": f"{d['note']}+v3"}

    registry = {(RecordKind.TASK, 1): v1_to_v2, (RecordKind.TASK, 2): v2_to_v3}
    current = {**CURRENT_VERSIONS, RecordKind.TASK: 3}
    lifted = upgrade(RecordKind.TASK, raw, registry=registry, current=current)
    assert lifted["schema_version"] == 3 and lifted["note"] == "v2+v3"
    assert raw["schema_version"] == 1  # input untouched

    with pytest.raises(UnknownSchemaVersion, match="v2 to v3"):
        upgrade(RecordKind.TASK, raw, registry={(RecordKind.TASK, 1): v1_to_v2}, current=current)


# AC-4: no secret name or value reaches a manifest.
def test_manifest_holds_no_secrets(isolated_settings_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_value = "sk-test-DISTINCTIVE-answer-key-0123456789"
    token_value = "hf_DISTINCTIVE_token_value_9876543210"
    monkeypatch.setenv("PARSEBENCH_ANSWER_API_KEY", key_value)
    monkeypatch.setenv("HF_TOKEN", token_value)
    snapshot = settings_snapshot(Settings())
    assert [e.name for e in snapshot] == ["cache_dir", "runs_dir"]

    manifest = make_manifest().model_copy(update={"settings": snapshot})
    text = canonical_json(manifest).decode()
    for forbidden in (key_value, token_value, "answer_api_key", "hf_token"):
        assert forbidden not in text
    with pytest.raises(ValidationError):
        SettingEntry(name="hf_token", value="x")


def test_manifest_cross_field_rules() -> None:
    raw = json.loads(canonical_json(make_manifest()))
    with pytest.raises(SchemaError, match="run_id date"):
        build(RecordKind.RUN_MANIFEST, {**raw, "created_at": "2026-11-17T00:00:00Z"})
    unsorted = [{"name": "runs_dir", "value": "runs"}, {"name": "cache_dir", "value": "c"}]
    with pytest.raises(SchemaError, match="sorted"):
        build(RecordKind.RUN_MANIFEST, {**raw, "settings": unsorted})
    assert "Z" == build(RecordKind.RUN_MANIFEST, {**raw, "created_at": "2026-11-16T09:30:00+00:00"}).model_dump(
        mode="json"
    )["created_at"][-1]


# AC-6: canonical bytes are stable.
def test_canonical_json_is_deterministic() -> None:
    a = make_task(1, "x")
    b = Task(source_ref="fields.q1", gold="x", answer_type=AnswerType.TEXT, question="Question 1?", doc_id=DOC, task_id=f"{DOC}-q01")
    assert canonical_json(a) == canonical_json(b)

    tasks = [make_task(n, "x") for n in range(1, 12)]
    shuffled = tasks[:]
    random.Random(0).shuffle(shuffled)
    assert dump_jsonl(tasks) == dump_jsonl(shuffled)
    docs_bytes = dump_jsonl((make_doc(),))
    assert task_set_sha256(docs_bytes, dump_jsonl(tasks)) == task_set_sha256(docs_bytes, dump_jsonl(shuffled))

    raw = json.loads(canonical_json(make_parse_ok()))
    costs = {canonical_json(build(RecordKind.PARSE_RESULT, {**raw, "cost_usd": c})) for c in ("0", 0, 0.0, "0.000000")}
    assert len(costs) == 1
    assert b'"cost_usd":"0.000000"' in costs.pop()


# AC-7: JSON and Arrow round trips, both variants, Decimal and None cost.
def test_json_round_trips() -> None:
    task = make_task(1, "x")
    records = (
        make_doc(),
        task,
        make_parse_ok(),
        make_parse_failed(),
        make_answer_ok(task, "x"),
        stub_grade(task, make_parse_failed(), None),
        make_manifest(),
    )
    kinds = (
        RecordKind.DOCUMENT,
        RecordKind.TASK,
        RecordKind.PARSE_RESULT,
        RecordKind.PARSE_RESULT,
        RecordKind.ANSWER,
        RecordKind.RESULT,
        RecordKind.RUN_MANIFEST,
    )
    for record, kind in zip(records, kinds, strict=True):
        assert parse_json(canonical_json(record), kind, "x") == record


def test_arrow_round_trips() -> None:
    task = make_task(1, "x")
    parses = (
        make_parse_ok(cost=Decimal("0.012345")),
        make_parse_ok(parser_id="llamaparse", cost=None),
        make_parse_failed(http_status=503),
        make_parse_failed(parser_id="marker", http_status=None),
    )
    answer_failed = AnswerFailed(
        run_id=RUN,
        task_id=task.task_id,
        doc_id=DOC,
        parser_id="docling",
        latency_ms=5,
        attempts=3,
        status="failed",
        error_kind=AnswerErrorKind.PROVIDER_HTTP,
        message="429",
        http_status=429,
    )
    answers = (make_answer_ok(task, ""), answer_failed)
    results = (stub_grade(task, parses[0], answers[0]), stub_grade(task, parses[2], None))
    cases: list[tuple[RecordKind, tuple[ParseOk | ParseFailed | AnswerOk | AnswerFailed | Result, ...]]] = [
        (RecordKind.PARSE_RESULT, parses),
        (RecordKind.ANSWER, answers),
        (RecordKind.RESULT, results),
    ]
    for kind, records in cases:
        table = to_arrow_table(kind, records)
        assert table.schema.field("schema_version").nullable is False
        assert from_arrow_table(kind, table) == records
    assert to_arrow_table(RecordKind.PARSE_RESULT, parses).schema.field("cost_usd").type == pa.decimal128(18, 6)


def test_arrow_row_with_bad_status_names_status() -> None:
    table = to_arrow_table(RecordKind.PARSE_RESULT, (make_parse_ok(),))
    rows: list[Mapping[str, object]] = [{**table.to_pylist()[0], "status": "weird"}]
    bad = pa.Table.from_pylist(rows)
    with pytest.raises(SchemaError) as exc:
        from_arrow_table(RecordKind.PARSE_RESULT, bad, source="p.parquet")
    assert exc.value.field == "status" and exc.value.line == 1


# AC-9: live JSON Schemas match the committed snapshots.
@pytest.mark.parametrize("kind", list(RecordKind))
def test_json_schema_matches_committed_snapshot(kind: RecordKind) -> None:
    path = SNAPSHOT_DIR / snapshot_name(kind, CURRENT_VERSIONS[kind])
    assert path.exists(), f"missing snapshot {path.name}: run python -m parsebench.schemas.snapshot"
    assert path.read_text(encoding="utf-8") == snapshot_text(kind), (
        f"{kind.value} changed shape: bump its schema_version, add an upgrade, write a new snapshot"
    )


# ---------------------------------------------------------------------------
# Per module edges (added by /test core schemas)
# ---------------------------------------------------------------------------


def _raw(record: object) -> dict[str, JsonValue]:
    assert isinstance(record, (Document, Task, ParseOk, ParseFailed, AnswerOk, AnswerFailed, Result, RunManifest))
    return json.loads(canonical_json(record))


# errors.py


def test_schema_error_formats_source_line_and_field() -> None:
    err = SchemaError("bad value", source="tasks.jsonl", line=3, field="gold")
    assert str(err) == "tasks.jsonl:3: gold: bad value"
    assert (err.source, err.line, err.field, err.message) == ("tasks.jsonl", 3, "gold", "bad value")


def test_schema_error_with_no_location_is_just_the_message() -> None:
    assert str(SchemaError("bad")) == "bad"


def test_integrity_error_lists_ids_after_the_message() -> None:
    err = IntegrityError("run is incomplete", ids=("a/x", "b/y"))
    assert str(err) == "run is incomplete: a/x, b/y"
    assert err.ids == ("a/x", "b/y")


def test_error_hierarchy_lets_callers_catch_one_base() -> None:
    assert issubclass(UnknownSchemaVersion, SchemaError)
    assert issubclass(IntegrityError, SchemaError)
    assert issubclass(SchemaError, ParseBenchError)


# types.py, through the records that use each type


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"latency_ms": 2**63}, "latency_ms"),
        ({"attempts": 0}, "attempts"),
        ({"run_id": "2026-13-01-0123abcd"}, "run_id"),
        ({"run_id": "2026-11-16-0123ABCD"}, "run_id"),
        ({"parser_id": "PyMuPDF"}, "parser_id"),
        ({"raw_path": "/raw/parse/pymupdf/inv-0001.txt"}, "raw_path"),
        ({"raw_path": "raw/parse/pymupdf/./inv-0001.txt"}, "raw_path"),
        ({"raw_path": "raw\\parse\\pymupdf\\inv-0001.txt"}, "raw_path"),
        ({"cost_usd": "1000000000000"}, "cost_usd"),
        ({"cost_usd": "0.0000001"}, "cost_usd"),
        ({"cost_usd": "abc"}, "cost_usd"),
        ({"raw_format": "pdf"}, "raw_format"),
    ],
)
def test_parse_ok_rejects_out_of_range_values(changes: dict[str, JsonValue], field: str) -> None:
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.PARSE_RESULT, {**_raw(make_parse_ok()), **changes})
    assert exc.value.field == field


def test_int64_max_latency_is_accepted() -> None:
    record = build(RecordKind.PARSE_RESULT, {**_raw(make_parse_ok()), "latency_ms": 2**63 - 1})
    assert record.latency_ms == 2**63 - 1


def test_usd_is_rounded_to_six_places_and_written_fixed_point() -> None:
    record = build(RecordKind.PARSE_RESULT, {**_raw(make_parse_ok()), "cost_usd": "1.5"})
    assert isinstance(record, ParseOk)
    assert record.cost_usd == Decimal("1.500000")
    assert str(record.cost_usd) == "1.500000"
    assert b'"cost_usd":"1.500000"' in canonical_json(record)


def test_usd_largest_value_fits() -> None:
    record = build(RecordKind.PARSE_RESULT, {**_raw(make_parse_ok()), "cost_usd": "999999999999.999999"})
    assert isinstance(record, ParseOk) and record.cost_usd == Decimal("999999999999.999999")


@pytest.mark.parametrize(("status", "ok"), [(99, False), (100, True), (599, True), (600, False)])
def test_http_status_must_be_a_real_status_code(status: int, ok: bool) -> None:
    data = {**_raw(make_parse_failed()), "http_status": status}
    if ok:
        assert build(RecordKind.PARSE_RESULT, data).model_dump()["http_status"] == status
    else:
        with pytest.raises(SchemaError, match="http_status"):
            build(RecordKind.PARSE_RESULT, data)


def test_message_is_capped_at_2000_characters() -> None:
    base = _raw(make_parse_failed())
    assert build(RecordKind.PARSE_RESULT, {**base, "message": "x" * 2000})
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.PARSE_RESULT, {**base, "message": "x" * 2001})
    assert exc.value.field == "message"


@pytest.mark.parametrize(
    ("field", "value"),
    [("gold", ""), ("gold", "x "), ("question", "\tWhat?"), ("source_ref", "")],
)
def test_task_text_must_be_non_empty_and_trimmed(field: str, value: str) -> None:
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.TASK, {**_raw(make_task(1, "x")), field: value})
    assert exc.value.field == field


def test_task_text_may_contain_inner_whitespace_and_unicode() -> None:
    task = build(RecordKind.TASK, {**_raw(make_task(1, "x")), "question": "Total\nfor Café ✓?"})
    assert task.question == "Total\nfor Café ✓?"


@pytest.mark.parametrize("task_id", ["inv-0001-q1", "inv-0001-q", "inv-0001-x01", "inv-00012-q01"])
def test_task_id_shape_and_prefix_are_enforced(task_id: str) -> None:
    with pytest.raises(SchemaError):
        build(RecordKind.TASK, {**_raw(make_task(1, "x")), "task_id": task_id})


def test_task_id_with_three_digit_question_number_is_valid() -> None:
    assert build(RecordKind.TASK, {**_raw(make_task(1, "x")), "task_id": "inv-0001-q100"}).task_id == "inv-0001-q100"


# document.py


def _real_doc(**provenance: JsonValue) -> dict[str, JsonValue]:
    origin: dict[str, JsonValue] = {
        "origin": "real",
        "source_url": "https://example.org/invoices/1.pdf?x=1",
        "license": "CC-BY-4.0",
        "retrieved_on": "2026-10-01",
        **provenance,
    }
    return {**_raw(make_doc()), "provenance": origin}


def test_real_origin_document_is_valid() -> None:
    doc = build(RecordKind.DOCUMENT, _real_doc())
    assert isinstance(doc.provenance, RealOrigin)
    assert doc.provenance.source_url == "https://example.org/invoices/1.pdf?x=1"


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"source_url": "ftp://example.org/a.pdf"}, "provenance.real.source_url"),
        ({"source_url": "https://example.org/a b.pdf"}, "provenance.real.source_url"),
        ({"license": ""}, "provenance.real.license"),
        ({"retrieved_on": "2026-02-30"}, "provenance.real.retrieved_on"),
    ],
)
def test_real_origin_rejects_bad_fields(changes: dict[str, JsonValue], field: str) -> None:
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.DOCUMENT, _real_doc(**changes))
    assert exc.value.field == field


def test_synthetic_origin_rejects_a_real_only_field() -> None:
    raw = _raw(make_doc())
    provenance = raw["provenance"]
    assert isinstance(provenance, dict)
    with pytest.raises(SchemaError):
        build(RecordKind.DOCUMENT, {**raw, "provenance": {**provenance, "license": "MIT"}})


def test_knobs_reject_non_bool_values() -> None:
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.DOCUMENT, {**_raw(make_doc()), "knobs": {"tables": 1}})
    assert exc.value.field == "knobs.tables"


# parse.py and answer.py


def test_raw_paths_follow_the_run_folder_layout() -> None:
    assert raw_parse_path("pymupdf", DOC, RawFormat.TEXT) == "raw/parse/pymupdf/inv-0001.txt"
    assert raw_parse_path("docling", DOC, RawFormat.MARKDOWN) == "raw/parse/docling/inv-0001.md"
    assert raw_answer_path("pymupdf", "inv-0001-q01") == "raw/answer/pymupdf/inv-0001-q01.json"


def test_parse_ok_raw_path_must_match_its_own_parser_and_doc() -> None:
    with pytest.raises(SchemaError, match="raw_path must be"):
        build(RecordKind.PARSE_RESULT, {**_raw(make_parse_ok()), "raw_path": "raw/parse/docling/inv-0001.txt"})


def test_answer_ok_raw_call_path_must_match_its_task() -> None:
    raw = _raw(make_answer_ok(make_task(1, "x"), "x"))
    with pytest.raises(SchemaError, match="raw_call_path must be"):
        build(RecordKind.ANSWER, {**raw, "raw_call_path": "raw/answer/pymupdf/inv-0001-q02.json"})


def test_answer_ok_allows_empty_answer_text() -> None:
    raw = _raw(make_answer_ok(make_task(1, "x"), "x"))
    answer = build(RecordKind.ANSWER, {**raw, "answer_text": ""})
    assert isinstance(answer, AnswerOk) and answer.answer_text == ""


def test_answer_failed_rejects_an_unknown_error_kind() -> None:
    raw = {**_raw(make_answer_ok(make_task(1, "x"), "x"))}
    failed: dict[str, JsonValue] = {
        k: raw[k] for k in ("schema_version", "run_id", "task_id", "doc_id", "parser_id", "latency_ms", "attempts")
    }
    failed |= {"status": "failed", "message": "", "http_status": None}
    assert isinstance(build(RecordKind.ANSWER, {**failed, "error_kind": "transport"}), AnswerFailed)
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.ANSWER, {**failed, "error_kind": "rate_limited"})
    assert exc.value.field == "error_kind"


# result.py


@pytest.mark.parametrize(
    ("outcome", "normalized", "ok"),
    [
        ("correct", "x", True),
        ("incorrect", "", True),
        ("parse_failed", None, True),
        ("answer_failed", None, True),
        ("correct", None, False),
        ("answer_failed", "x", False),
    ],
)
def test_normalized_answer_is_none_exactly_for_failures(outcome: str, normalized: str | None, ok: bool) -> None:
    task = make_task(1, "x")
    data: dict[str, JsonValue] = {
        **_raw(stub_grade(task, make_parse_ok(), make_answer_ok(task, "x"))),
        "outcome": outcome,
        "normalized_answer": normalized,
    }
    if ok:
        assert build(RecordKind.RESULT, data).outcome.value == outcome
    else:
        with pytest.raises(SchemaError, match="normalized_answer"):
            build(RecordKind.RESULT, data)


# manifest.py


def test_secret_setting_names_come_from_secretstr_fields() -> None:
    assert SECRET_SETTING_NAMES == frozenset({"answer_api_key", "hf_token"})


@pytest.mark.parametrize("name", ["answer_api_key", "hf_token"])
def test_every_secret_setting_name_is_rejected_in_a_manifest(name: str) -> None:
    raw = _raw(make_manifest())
    with pytest.raises(SchemaError) as exc:
        build(RecordKind.RUN_MANIFEST, {**raw, "settings": [{"name": name, "value": ""}]})
    assert exc.value.field == "settings.0.name"


def test_settings_snapshot_writes_paths_as_given(isolated_settings_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSEBENCH_CACHE_DIR", "~/models/cache")
    entries = {e.name: e.value for e in settings_snapshot(Settings())}
    assert entries == {"cache_dir": "~/models/cache", "runs_dir": "runs"}


def test_settings_snapshot_writes_none_as_empty_string(isolated_settings_env: Path) -> None:
    class WithOptional(Settings):
        note: str | None = None

    entries = {e.name: e.value for e in settings_snapshot(WithOptional())}
    assert entries["note"] == ""


def test_settings_snapshot_refuses_a_setting_type_it_has_no_rule_for(isolated_settings_env: Path) -> None:
    class WithInt(Settings):
        retries: int = 3

    with pytest.raises(TypeError, match="int"):
        settings_snapshot(WithInt())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"created_at": "2026-11-16T09:30:00+01:00"}, "UTC"),
        ({"created_at": "2026-11-15T23:59:59Z"}, "run_id date"),
        ({"settings": [{"name": "cache_dir", "value": "a"}, {"name": "cache_dir", "value": "b"}]}, "sorted and unique"),
        ({"task_set": {"version": "v1", "sha256": H}}, "task_set.version"),
        ({"concurrency": 0}, "concurrency"),
    ],
)
def test_manifest_rejects_inconsistent_values(changes: dict[str, JsonValue], message: str) -> None:
    with pytest.raises(SchemaError, match=message):
        build(RecordKind.RUN_MANIFEST, {**_raw(make_manifest()), **changes})


def test_manifest_rejects_duplicate_parsers() -> None:
    manifest = make_manifest()
    with pytest.raises(ValidationError, match="parsers"):
        RunManifest.model_validate({**manifest.model_dump(), "parsers": manifest.parsers * 2})


def test_parser_info_rejects_unsorted_model_revisions() -> None:
    revisions = (ModelRevision(repo="org/b", revision="b" * 40), ModelRevision(repo="org/a", revision="a" * 40))
    with pytest.raises(ValidationError, match="model_revisions"):
        ParserInfo(parser_id="docling", package="docling", package_version="2.1.0", extra=None, model_revisions=revisions)


def test_environment_rejects_duplicate_system_tools() -> None:
    tool = ToolVersion(name="tesseract", version="5.3.0")
    with pytest.raises(ValidationError, match="system_tools"):
        Environment(
            python_version="3.12", os="linux", cpu="x86_64", threads=1, uv_lock_sha256=None, torch_version=None,
            system_tools=(tool, tool),
        )


def test_answering_config_rejects_infinite_temperature() -> None:
    with pytest.raises(ValidationError):
        AnsweringConfig(
            provider="p", model="m", temperature=float("inf"), prompt_sha256=H,
            truncation=TruncationRule(kind=TruncationKind.HEAD_CHARS, limit=1),
        )


# canonical.py


def test_sha256_hex_matches_the_known_empty_digest() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_task_set_sha256_hashes_the_two_file_digests() -> None:
    empty = sha256_hex(b"")
    assert task_set_sha256(b"", b"") == sha256_hex(f"{empty}\n{empty}".encode())
    assert task_set_sha256(b"a", b"b") != task_set_sha256(b"b", b"a")


def test_canonical_json_keeps_unicode_unescaped_and_unnormalized() -> None:
    composed = make_task(1, "Café")
    decomposed = make_task(1, "Café")
    assert "Café".encode() in canonical_json(composed)
    assert canonical_json(composed) != canonical_json(decomposed)


def test_canonical_json_is_compact_with_sorted_keys() -> None:
    text = canonical_json(make_task(1, "x")).decode()
    assert ", " not in text and ": " not in text
    keys = list(json.loads(text))
    assert keys == sorted(keys)


# codec.py


def test_parse_jsonl_of_empty_bytes_is_empty() -> None:
    assert parse_jsonl(b"", RecordKind.TASK, "t") == ()


def test_dump_jsonl_of_nothing_is_empty_bytes() -> None:
    assert dump_jsonl(()) == b""


def test_dump_jsonl_sorts_by_id_in_codepoint_order() -> None:
    tasks = [make_task(99, "x"), make_task(100, "x"), make_task(2, "x")]
    lines = dump_jsonl(tasks).decode().splitlines()
    assert [json.loads(line)["task_id"] for line in lines] == ["inv-0001-q02", "inv-0001-q100", "inv-0001-q99"]


def test_dump_jsonl_refuses_mixed_kinds() -> None:
    with pytest.raises(TypeError):
        dump_jsonl([make_doc(), make_task(1, "x")])


@pytest.mark.parametrize(
    ("data", "message", "line"),
    [
        (b'{"a":1}', "missing final newline", 1),
        (b"[]\n", "JSON object", 1),
        (b"{\n", "invalid JSON", 1),
        (b"\xff\n", "UTF-8", None),
    ],
)
def test_parse_jsonl_rejects_bad_framing(data: bytes, message: str, line: int | None) -> None:
    with pytest.raises(SchemaError, match=message) as exc:
        parse_jsonl(data, RecordKind.TASK, "t.jsonl")
    assert exc.value.line == line


def test_parse_jsonl_reports_the_line_of_a_missing_final_newline() -> None:
    data = dump_jsonl([make_task(1, "x")]) + canonical_json(make_task(2, "x"))
    with pytest.raises(SchemaError, match="final newline") as exc:
        parse_jsonl(data, RecordKind.TASK, "t")
    assert exc.value.line == 2


def test_parse_json_rejects_a_bom_and_accepts_a_trailing_newline() -> None:
    body = canonical_json(make_manifest())
    assert parse_json(body + b"\n", RecordKind.RUN_MANIFEST, "m") == make_manifest()
    with pytest.raises(SchemaError, match="BOM"):
        parse_json(b"\xef\xbb\xbf" + body, RecordKind.RUN_MANIFEST, "m")


def test_build_fills_in_the_current_schema_version() -> None:
    raw = _raw(make_task(1, "x"))
    del raw["schema_version"]
    assert build(RecordKind.TASK, raw).schema_version == 1


def test_build_rejects_a_newer_explicit_schema_version() -> None:
    with pytest.raises(UnknownSchemaVersion):
        build(RecordKind.TASK, {**_raw(make_task(1, "x")), "schema_version": 2})


def test_schema_error_counts_the_errors_it_does_not_name() -> None:
    with pytest.raises(SchemaError, match=r"and \d+ more errors"):
        build(RecordKind.TASK, {})


def test_kind_of_and_record_key_identify_every_record() -> None:
    task = make_task(1, "x")
    cases = [
        (make_doc(), RecordKind.DOCUMENT, (DOC,)),
        (task, RecordKind.TASK, (task.task_id,)),
        (make_parse_failed(), RecordKind.PARSE_RESULT, (RUN, DOC, "docling")),
        (make_answer_ok(task, "x"), RecordKind.ANSWER, (RUN, task.task_id, "pymupdf")),
        (stub_grade(task, make_parse_failed(), None), RecordKind.RESULT, (RUN, task.task_id, "docling")),
        (make_manifest(), RecordKind.RUN_MANIFEST, (RUN,)),
    ]
    for record, kind, key in cases:
        assert (kind_of(record), record_key(record)) == (kind, key)


# upgrade.py


def test_upgrade_stamps_each_step_version_whatever_the_function_returns() -> None:
    raw = _raw(make_task(1, "x"))

    def careless(d: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return {**d, "schema_version": 99}

    lifted = upgrade(
        RecordKind.TASK, raw, registry={(RecordKind.TASK, 1): careless}, current={**CURRENT_VERSIONS, RecordKind.TASK: 2}
    )
    assert lifted["schema_version"] == 2


def test_upgrade_at_the_current_version_returns_an_equal_copy() -> None:
    raw = _raw(make_task(1, "x"))
    lifted = upgrade(RecordKind.TASK, raw)
    assert lifted == raw and lifted is not raw


def test_current_versions_cover_every_record_kind() -> None:
    assert set(CURRENT_VERSIONS) == set(RecordKind)
    assert current_schema_versions().model_dump() == {k.value: v for k, v in CURRENT_VERSIONS.items()}


# arrow.py


def test_arrow_columns_are_exactly_the_model_fields() -> None:
    assert set(PARSE_RESULT_ARROW.names) == set(ParseOk.model_fields) | set(ParseFailed.model_fields)
    assert set(ANSWER_ARROW.names) == set(AnswerOk.model_fields) | set(AnswerFailed.model_fields)
    assert set(RESULT_ARROW.names) == set(Result.model_fields)
    assert set(ARROW_SCHEMAS) == {RecordKind.PARSE_RESULT, RecordKind.ANSWER, RecordKind.RESULT}


def test_shared_columns_are_required_and_variant_columns_nullable() -> None:
    required = {f.name for f in PARSE_RESULT_ARROW if not f.nullable}
    assert required == {"schema_version", "run_id", "doc_id", "parser_id", "latency_ms", "attempts", "status"}


def test_to_arrow_row_nulls_the_other_variants_columns() -> None:
    row = to_arrow_row(make_parse_failed())
    assert row["raw_path"] is None and row["cost_usd"] is None
    assert row["error_kind"] == "timeout"
    assert to_arrow_row(make_parse_ok(cost=Decimal("0.5")))["cost_usd"] == Decimal("0.500000")


def test_from_arrow_row_keeps_only_the_named_variants_columns() -> None:
    row = {**to_arrow_row(make_parse_ok()), "error_kind": "crash", "message": "stale"}
    assert from_arrow_row(RecordKind.PARSE_RESULT, row) == make_parse_ok()


def test_from_arrow_row_rejects_an_unsupported_value_type() -> None:
    row = {**to_arrow_row(make_parse_ok()), "latency_ms": 1.5}
    with pytest.raises(SchemaError) as exc:
        from_arrow_row(RecordKind.PARSE_RESULT, row)
    assert exc.value.field == "latency_ms"


def test_from_arrow_row_names_a_missing_required_column() -> None:
    row = {k: v for k, v in to_arrow_row(make_parse_ok()).items() if k != "doc_id"}
    with pytest.raises(SchemaError) as exc:
        from_arrow_row(RecordKind.PARSE_RESULT, row, source="p.parquet", line=4)
    assert (exc.value.field, exc.value.source, exc.value.line) == ("doc_id", "p.parquet", 4)


def test_from_arrow_table_reports_the_bad_row_number() -> None:
    good = to_arrow_row(make_parse_ok())
    bad = {**to_arrow_row(make_parse_ok(parser_id="docling")), "raw_sha256": "nothex"}
    table = pa.Table.from_pylist([good, bad], schema=PARSE_RESULT_ARROW)
    with pytest.raises(SchemaError) as exc:
        from_arrow_table(RecordKind.PARSE_RESULT, table)
    assert (exc.value.line, exc.value.field) == (2, "raw_sha256")


def test_to_arrow_table_refuses_records_of_another_kind() -> None:
    with pytest.raises(TypeError):
        to_arrow_table(RecordKind.PARSE_RESULT, [make_answer_ok(make_task(1, "x"), "x")])


def test_non_row_kinds_have_no_arrow_form() -> None:
    with pytest.raises(SchemaError, match="not stored as Arrow rows"):
        to_arrow_table(RecordKind.TASK, [])
    with pytest.raises(SchemaError):
        from_arrow_row(RecordKind.RUN_MANIFEST, {})


# integrity.py


def test_verify_raw_accepts_matching_bytes() -> None:
    verify_raw(RAW_TEXT, sha256_hex(RAW_TEXT))


def test_answer_for_an_unknown_task_is_flagged() -> None:
    stray = make_answer_ok(make_task(7, "x"), "x")
    with pytest.raises(IntegrityError) as exc:
        check_result_consistency(make_manifest(), (make_task(1, "x"),), (make_parse_ok(),), (stray,), ())
    assert any("inv-0001-q07/pymupdf has unknown task_id" in i for i in exc.value.ids)


def test_two_answers_for_one_task_and_parser_are_flagged() -> None:
    task = make_task(1, "x")
    answer = make_answer_ok(task, "x")
    with pytest.raises(IntegrityError, match="two Answers for inv-0001-q01/pymupdf"):
        check_result_consistency(make_manifest(), (task,), (make_parse_ok(),), (answer, answer), ())


def test_graded_result_without_an_answer_is_flagged() -> None:
    task = make_task(1, "x")
    result = stub_grade(task, make_parse_ok(), make_answer_ok(task, "x"))
    with pytest.raises(IntegrityError, match="disagrees with its parse and answer"):
        check_result_consistency(make_manifest(), (task,), (make_parse_ok(),), (), (result,))


def test_answer_failed_result_must_say_answer_failed() -> None:
    task = make_task(1, "x")
    failed = AnswerFailed(
        run_id=RUN, task_id=task.task_id, doc_id=DOC, parser_id="pymupdf", latency_ms=1, attempts=1,
        status="failed", error_kind=AnswerErrorKind.TIMEOUT, message="", http_status=None,
    )
    good = stub_grade(task, make_parse_ok(), failed)
    assert good.outcome is Outcome.ANSWER_FAILED
    check_result_consistency(make_manifest(), (task,), (make_parse_ok(),), (failed,), (good,))
    wrong = good.model_copy(update={"outcome": Outcome.PARSE_FAILED})
    with pytest.raises(IntegrityError):
        check_result_consistency(make_manifest(), (task,), (make_parse_ok(),), (failed,), (wrong,))


def test_empty_task_set_and_run_pass() -> None:
    check_task_set((), ())
    check_run_complete(make_manifest(), (), ())


# snapshot.py (writes to a temp folder only)


def test_write_snapshots_creates_each_file_once(tmp_path: Path) -> None:
    written = write_snapshots(tmp_path)
    assert sorted(p.name for p in written) == sorted(snapshot_name(k, CURRENT_VERSIONS[k]) for k in RecordKind)
    assert write_snapshots(tmp_path) == ()


def test_write_snapshots_refuses_to_overwrite_a_differing_file(tmp_path: Path) -> None:
    write_snapshots(tmp_path)
    target = tmp_path / snapshot_name(RecordKind.TASK, 1)
    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="bump task"):
        write_snapshots(tmp_path)
    assert target.read_text(encoding="utf-8") == "{}\n"


def test_live_schemas_forbid_unknown_fields() -> None:
    assert live_schema(RecordKind.TASK)["additionalProperties"] is False
    assert "discriminator" in json.dumps(live_schema(RecordKind.PARSE_RESULT))
