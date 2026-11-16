"""Strict, versioned records every stage shares (spec 0002).

Six records: Document, Task, ParseResult (ParseOk | ParseFailed), Answer
(AnswerOk | AnswerFailed), Result, and RunManifest. All are frozen, strict,
and forbid unknown fields. Read them through the codec (`parse_jsonl`,
`parse_json`, `build`, `from_arrow_row`), which upgrades old versions and
turns validation failures into `SchemaError`. No I/O happens here except
`snapshot.write_snapshots`, which you run by hand.
"""

from parsebench.schemas.answer import ANSWER, Answer, AnswerBase, AnswerFailed, AnswerOk, raw_answer_path
from parsebench.schemas.arrow import (
    ANSWER_ARROW,
    ARROW_SCHEMAS,
    PARSE_RESULT_ARROW,
    RESULT_ARROW,
    from_arrow_row,
    from_arrow_table,
    to_arrow_row,
    to_arrow_table,
)
from parsebench.schemas.base import Frozen, Record
from parsebench.schemas.canonical import canonical_json, sha256_hex, task_set_sha256
from parsebench.schemas.codec import (
    AnyRecord,
    build,
    dump_jsonl,
    kind_of,
    parse_json,
    parse_jsonl,
    record_key,
    validate_raw,
)
from parsebench.schemas.document import Document, Knobs, Provenance, RealOrigin, SyntheticOrigin
from parsebench.schemas.integrity import (
    check_result_consistency,
    check_run_complete,
    check_task_set,
    verify_raw,
)
from parsebench.schemas.manifest import (
    SECRET_SETTING_NAMES,
    AnsweringConfig,
    Environment,
    ModelRevision,
    ParserInfo,
    RunManifest,
    SchemaVersions,
    SettingEntry,
    TaskSetRef,
    ToolVersion,
    TruncationRule,
    settings_snapshot,
)
from parsebench.schemas.parse import PARSE_RESULT, ParseBase, ParseFailed, ParseOk, ParseResult, raw_parse_path
from parsebench.schemas.result import Result
from parsebench.schemas.task import Task
from parsebench.schemas.types import (
    AnswerErrorKind,
    AnswerType,
    DocType,
    Outcome,
    ParseErrorKind,
    RawFormat,
    RecordKind,
    TruncationKind,
)
from parsebench.schemas.upgrade import CURRENT_VERSIONS, UPGRADES, current_schema_versions, upgrade

__all__ = [
    "ANSWER",
    "ANSWER_ARROW",
    "ARROW_SCHEMAS",
    "CURRENT_VERSIONS",
    "PARSE_RESULT",
    "PARSE_RESULT_ARROW",
    "RESULT_ARROW",
    "SECRET_SETTING_NAMES",
    "UPGRADES",
    "Answer",
    "AnswerBase",
    "AnswerErrorKind",
    "AnswerFailed",
    "AnswerOk",
    "AnswerType",
    "AnsweringConfig",
    "AnyRecord",
    "DocType",
    "Document",
    "Environment",
    "Frozen",
    "Knobs",
    "ModelRevision",
    "Outcome",
    "ParseBase",
    "ParseErrorKind",
    "ParseFailed",
    "ParseOk",
    "ParseResult",
    "ParserInfo",
    "Provenance",
    "RawFormat",
    "RealOrigin",
    "Record",
    "RecordKind",
    "Result",
    "RunManifest",
    "SchemaVersions",
    "SettingEntry",
    "SyntheticOrigin",
    "Task",
    "TaskSetRef",
    "ToolVersion",
    "TruncationKind",
    "TruncationRule",
    "build",
    "canonical_json",
    "check_result_consistency",
    "check_run_complete",
    "check_task_set",
    "current_schema_versions",
    "dump_jsonl",
    "from_arrow_row",
    "from_arrow_table",
    "kind_of",
    "parse_json",
    "parse_jsonl",
    "raw_answer_path",
    "raw_parse_path",
    "record_key",
    "settings_snapshot",
    "sha256_hex",
    "task_set_sha256",
    "to_arrow_row",
    "to_arrow_table",
    "upgrade",
    "validate_raw",
    "verify_raw",
]
