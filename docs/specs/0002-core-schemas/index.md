# 0002. Core schemas: six strict, versioned records keyed by document, task, parser, and run

**Date**: 2026-11-16
**Status**: Accepted

## Summary

This spec defines the six data records every part of ParseBench shares: Document, Task, ParseResult, Answer, Result, and RunManifest. Each one is a strict, frozen Pydantic model with its own version number. Bad data is rejected loudly, and old data can still be read through small upgrade functions. A PDF is parsed once per parser, and the model's answer is archived, so any past run can be graded again exactly, with no parser and no model call. Every later feature reads and writes these records, so getting them right now is what keeps rescoring and cross run comparisons honest.

## Rationale

Reasoning, options weighed, and the premise note: see [rationale.md](rationale.md).

## Requirements

**User stories**:
- As the benchmark author, I want every stage to read and write the same strict records, so a bug in one stage fails loudly at the boundary instead of silently skewing a score.
- As anyone checking a published number, I want every record to carry the versions and hashes needed to reproduce it, so I can regrade an archived run and get identical results.
- As a later feature (generator, adapters, harness, results store, scorer), I want one import for these contracts, so I never invent my own shape for shared data.

**Acceptance criteria**:
- **AC-1**: Each of the six records (Document, Task, ParseResult, Answer, Result, RunManifest) is a frozen Pydantic v2 model with strict validation and `extra="forbid"`. Malformed input read through the codec is rejected with a `SchemaError` that names the field (and the file and line, when read from JSON lines). Direct construction in Python raises Pydantic's `ValidationError` for the same cases. Malformed means a wrong type, a coerced value such as `"12"` for an int, an unknown field, a duplicate JSON key, a missing required field, an ID, sha256, or path that breaks its pattern, a naive or non UTC datetime, NaN or infinity, or a negative latency, count, or cost. No error message ever echoes the input value.
- **AC-2**: Every record carries `schema_version`. Reading a version newer than the code knows raises `UnknownSchemaVersion`. Reading an older version runs the registered pure upgrade functions, in order, before validation. A test registry proves the chain runs `v1 → v2 → v3` and fails loudly on a gap.
- **AC-3**: ParseResult and Answer are discriminated unions on `status` (`ok` or `failed`). A record that mixes the two shapes (for example, `ok` with an `error_kind`, or `failed` with a `raw_path`) cannot be constructed.
- **AC-4**: RunManifest records the task set version and sha256, the scorer version, the answering provider, model, temperature, prompt sha256, and truncation rule, the seed, each parser's package version and model revisions, the environment (Python, OS, CPU, threads, uv.lock sha256, torch version, system tools), the non secret settings, the concurrency, and the schema version of every record type. No secret setting name or value can appear in a manifest. Constructing one with a secret setting name raises `ValidationError`, and the manifest JSON built with every key set (to long, distinctive test values) contains none of the secret values.
- **AC-5**: Task, ParseResult, and Answer together hold every input grading needs: the gold, the answer type, the answer text, and each failure status. Raw files are referenced by run relative path and sha256. A test rebuilds a Result from stored records plus a stub grade function, with no parser and no model call, and gets a Result equal to the original. A raw file whose bytes don't match its sha256 raises `IntegrityError`.
- **AC-6**: `canonical_json` is deterministic. Equal records give identical bytes and sha256 on any machine, whatever order the fields were set in. Decimals serialize as fixed point strings with exactly 6 places (`0` becomes `"0.000000"`), and datetimes as UTC ISO 8601 ending in `Z` (also for `+00:00` input). The task set sha256 is computed over the stored bytes of `documents.jsonl` and `tasks.jsonl` (written once in canonical form, sorted by ID, never rewritten), so a later schema upgrade or Pydantic upgrade never changes it.
- **AC-7**: Every record round trips through JSON to an equal record. ParseResult, Answer, and Result also round trip through their explicit Arrow schemas to equal records, covering both union variants, a Decimal cost, and an unknown (None) cost.
- **AC-8**: Pure cross record checks raise `IntegrityError` with the offending IDs for: duplicate doc_id or task_id; a Task whose doc_id has no Document; two ParseResults for one (doc, parser); an Answer whose doc's ParseResult is failed or missing; a Result whose outcome disagrees with its ParseResult or Answer status; a Result whose `normalized_answer` presence disagrees with its outcome; a row whose `run_id` differs from the manifest's, or whose `parser_id` is not in the manifest; a row `doc_id` that disagrees with its Task; and a run missing a Result, holding two, or holding one for an unknown task or parser. (A task_id that doesn't match its doc_id is rejected by Task itself, per AC-1.)
- **AC-9**: A JSON Schema snapshot for each record's current version is committed under `src/parsebench/schemas/json/`. A test fails if any model's live JSON Schema differs from the snapshot for its current `schema_version`, and a CI step fails if any existing `*.vN.json` file is modified rather than added. So a shape change cannot ship without a version bump, a new snapshot, and an upgrade function.

## Decision

**Chosen option**: Option 1: Pydantic models as the single source of truth, strict and frozen, versioned per record, with explicit Arrow mappings, pure upgrade functions, and committed JSON Schema snapshots.

Define all six records in `parsebench.schemas` as strict, frozen Pydantic v2 models. ParseResult is keyed per (run, document, parser), and Answer and Result per (run, task, parser). Failures are typed union variants. Versions, hashes, and a canonical JSON form make every record reproducible and checkable.

**Implementation skills**: `pydantic` (`pydantic/skills`, `.claude/skills/pydantic/`) · `uv` (`astral-sh/agent-plugins`, `.claude/skills/uv/`)

**Calls made here** (each is a pick, with the runner up named):
- **Shared bases.** `Frozen` sets `ConfigDict(frozen=True, strict=True, extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)` and is used by embedded models (`Knobs`, origins, `TaskSetRef`, and so on). `Record(Frozen)` adds `schema_version: Literal[1] = 1` and is used by the six top level records. Union variants share a base that holds the common fields: `ParseBase` holds `run_id`, `doc_id`, `parser_id`, `latency_ms`, and `attempts`, and `AnswerBase` holds `run_id`, `task_id`, `doc_id`, `parser_id`, `latency_ms`, and `attempts`. Runner up: repeating the config on each model, which is easy to forget on one.
- **Error safety.** `hide_input_in_errors=True` keeps secrets and document text out of error messages. The codec rejects duplicate JSON keys (through `json.loads(object_pairs_hook=...)`), a UTF-8 BOM, and blank lines, and it accepts `\n` line endings only.
- **Collections** are `tuple[...]`, never `list` or `dict`, per AGENTS.md. Map shaped data (settings, parser versions) is a sorted tuple of small entry models, so the frozen rule holds deeply. Runner up: `Mapping` fields, which Pydantic stores as a mutable `dict`.
- **Datetimes** use `AwareDatetime` plus a validator that requires a UTC offset of zero. Runner up: naive datetimes with UTC assumed, which hides bugs.
- **Money** is `Decimal`, with `ge=0`, `max_digits=18`, and at most 6 decimal places. An after validator rounds it to exactly 6 places (`quantize`), and a serializer writes `format(d, "f")`, so equal costs always give equal bytes. Arrow stores it as `decimal128(18, 6)`. Runner up: integer micro dollars, which are exact but awkward to read.
- **Canonical JSON** is `json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`, with no Unicode normalization. A JSON lines file is one canonical line per record, each ending in `\n`, sorted by ID in codepoint order. `model_dump_json` is not used here, because it can't sort keys.
- **Text fields** (`question`, `gold`, `source_ref`) must be non empty and are rejected (not silently stripped) if they have leading or trailing whitespace, so round trips stay equal. `answer_text` may be empty, and the grader marks that incorrect. `message` is capped at 2000 characters. The harness redacts vendor error text before it becomes a `message` (feature 12).
- **Setting values** are all stored as `str` (Paths as given, never resolved, so a home folder never leaks into a published manifest). A `None` non secret setting is written as `""`. A setting of any other type raises `TypeError` in `settings_snapshot`, so the snapshot gets updated when a new setting type appears. `threads` lives in `environment`, not in `settings`.
- **Enums** are `StrEnum`, stored as plain strings in Arrow. Runner up: Arrow dictionary types, which aren't worth it at this row count.
- **Raw file layout** inside a run folder: `raw/parse/<parser_id>/<doc_id>.<ext>` and `raw/answer/<parser_id>/<task_id>.json`. Paths are POSIX, relative, and contain no `..`. This refines spec 0001's "one raw output per task and parser" to fit parsing per document.
- **Run ID** is `YYYY-MM-DD-<8 hex>`. The hex comes from `secrets.token_hex(4)` at the CLI edge. This is a deliberate exception to the seeded randomness rule, because a run ID is an identity, not an experimental draw (a seeded ID would collide across runs that share a seed on one day). Schemas only validates the pattern.
- **One validation path: JSON.** Strict validation in Python mode rejects plain strings for enums, dates, and URLs, which is what JSON dicts and pyarrow rows contain. So every read goes through `validate_json`: the codec parses text to a dict, runs `upgrade`, then validates the re-encoded JSON. `from_arrow_row` converts a row to a JSON compatible dict (Decimal and datetime to strings, the other variant's columns dropped), then takes the same path. Code that builds records in Python (generators, adapters, tests) passes enum members, `date` objects, and nested model instances, or uses the codec. A small `build(kind, data)` helper in `codec.py` wraps the JSON path for builders who have a plain dict.
- **Schema version handling.** `schema_version` defaults to `1` on construction. In `upgrade`, a missing key, a bool, a non integer, or a value below 1 raises `SchemaError`. A value above the current one raises `UnknownSchemaVersion`. `upgrade(kind, data, *, registry=UPGRADES, current=CURRENT_VERSIONS)` takes its registry as a parameter, so tests inject their own. `CURRENT_VERSIONS` is derived from the models and also fills `RunManifest.schema_versions`. Raw dicts are typed as `dict[str, JsonValue]` for Pyright strict.
- **Record kind.** A `RecordKind` StrEnum (`document`, `task`, `parse_result`, `answer`, `result`, `run_manifest`) names records in the codec, upgrade, and Arrow APIs. `@overload`s on each `Literal` give Pyright an exact return type.
- **Hash inputs.** `prompt_sha256` is the sha256 of the prompt template's UTF-8 bytes (the template, not each rendered prompt). `input_sha256` is the sha256 of the UTF-8 bytes of the truncated text actually sent. `raw_sha256` and `raw_call_sha256` cover the bytes as written to disk. There is no rule tying `input_sha256` to `raw_sha256`.
- **Knobs v1** has the four knobs scope row 8 already names, `tables`, `multi_column`, `footnotes`, and `spanning_tables`, all `bool`, all defaulting to `False`. Invoices from feature 4 set `tables=True`. Scan noise arrives with feature 9 as a version bump. Runner up: an empty model, but the generator has to record table settings from day one.
- **Error hierarchy** lives in a new `src/parsebench/errors.py`: `ParseBenchError` → `SchemaError` → `UnknownSchemaVersion` and `IntegrityError`. It's project wide, so later features extend it.

## Feature design

**Data model sketch**:

Shared types (`schemas/types.py`):

| Type | Definition |
|---|---|
| `Sha256` | `str`, pattern `^[0-9a-f]{64}$` |
| `DocId` | `str`, pattern `^[a-z0-9]+(?:-[a-z0-9]+)*$`, max 64 |
| `TaskId` | `str`, pattern `^[a-z0-9]+(?:-[a-z0-9]+)*-q[0-9]{2,}$`, max 80. Task also checks `re.fullmatch(rf"{re.escape(doc_id)}-q[0-9]{{2,}}", task_id)` |
| `ParserId` | `str`, pattern `^[a-z0-9]+(?:[-_][a-z0-9]+)*$` (for example `pymupdf`, `docling`, `llamaparse`) |
| `RunId` | `str`, pattern `^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{8}$`, and the date part must be a real date. RunManifest also requires it to equal `created_at`'s UTC date |
| `SemVer` | `str`, pattern `^[0-9]+\.[0-9]+\.[0-9]+$` |
| `RelPath` | `str`, pattern `^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$`, and no segment may be `.` or `..` (so no leading `/`, backslash, `//`, or NUL) |
| `UtcDatetime` | `AwareDatetime` with offset zero |
| `Usd` | `Decimal`, `ge=0`, `max_digits=18`, `decimal_places=6`, rounded to 6 places, serialized fixed point |
| `HttpUrlStr` | `str`, pattern `^https?://\S+$` (kept as written, so URL normalization never touches hashed bytes) |
| `GitRevision` | `str`, pattern `^[0-9a-f]{40}$` |
| counts and ms | `int`, `ge=0`, `le=2**63-1` (fits Arrow `int64`) |

Enums: `DocType` {`invoice`} · `AnswerType` {`number`, `currency`, `date`, `text`} · `RawFormat` {`text` (file extension `txt`), `markdown` (`md`)} · `TruncationKind` {`head_chars`} (feature 6 may add members with a version bump) · `ParseErrorKind` {`timeout`, `parser_error`, `vendor_http`, `crash`} · `AnswerErrorKind` {`timeout`, `provider_http`, `transport`, `malformed_response`} · `Outcome` {`correct`, `incorrect`, `parse_failed`, `answer_failed`}.

Records (each has `schema_version: Literal[1]`):

| Record | Key | Fields (required unless noted) | Relationships |
|---|---|---|---|
| **Document** | `doc_id` | `sha256: Sha256` (PDF bytes) · `doc_type: DocType` · `pages: int ≥1` · `knobs: Knobs` · `provenance: SyntheticOrigin \| RealOrigin` (discriminator `origin`) | 1:N Task · 1:N ParseResult |
| `Knobs` | (embedded) | `tables`, `multi_column`, `footnotes`, `spanning_tables`: `bool = False` | |
| `SyntheticOrigin` | (embedded) | `origin: Literal["synthetic"]` · `generator: str` · `generator_version: SemVer` · `seed: int ≥0` · `source_data_sha256: Sha256` | |
| `RealOrigin` | (embedded) | `origin: Literal["real"]` · `source_url: HttpUrlStr` · `license: str` (SPDX ID) · `retrieved_on: date` | |
| **Task** | `task_id` | `doc_id: DocId` FK · `question: str` (non empty, stripped) · `answer_type: AnswerType` · `gold: str` (canonical form, non empty) · `source_ref: str` (non empty) | N:1 Document · 1:N Answer · 1:N Result |
| **ParseOk** | (`run_id`, `doc_id`, `parser_id`) | base fields from `ParseBase` · `status: Literal["ok"]` · `raw_path: RelPath`, which must equal `raw/parse/{parser_id}/{doc_id}.{txt\|md}` with the extension set by `raw_format` · `raw_sha256: Sha256` · `raw_format: RawFormat` · `latency_ms: int ≥0` · `cost_usd: Usd \| None` (None = vendor did not report; local parsers write `0`) · `attempts: int ≥1` | N:1 Document · N:1 RunManifest · 1:N Answer |
| **ParseFailed** | same | base fields from `ParseBase` · `status: Literal["failed"]` · `error_kind: ParseErrorKind` · `message: str` · `http_status: int \| None` (None when not an HTTP error) · `latency_ms: int ≥0` · `attempts: int ≥1` | same |
| **AnswerOk** | (`run_id`, `task_id`, `parser_id`) | `doc_id: DocId` · `status: Literal["ok"]` · `answer_text: str` · `prompt_sha256: Sha256` · `input_sha256: Sha256` (truncated text sent) · `truncated: bool` · `input_tokens: int ≥0` · `output_tokens: int ≥0` · `latency_ms: int ≥0` · `raw_call_path: RelPath` (must equal `raw/answer/{parser_id}/{task_id}.json`) · `raw_call_sha256: Sha256` · `attempts: int ≥1` (the base fields come from `AnswerBase`) | N:1 ParseOk (same run, doc, parser) |
| **AnswerFailed** | same | base fields from `AnswerBase` (including `latency_ms`, the time to failure) · `status: Literal["failed"]` · `error_kind: AnswerErrorKind` · `message: str` (max 2000) · `http_status: int \| None` | same |
| **Result** | (`run_id`, `task_id`, `parser_id`) | `doc_id: DocId` · `outcome: Outcome` · `normalized_answer: str \| None` (None exactly when no answer exists) · `normalized_gold: str` (the normalizer always runs on gold, even for failed rows) · `scorer_version: SemVer` | 1:1 Answer, or 1:1 ParseFailed |
| **RunManifest** | `run_id` | `created_at: UtcDatetime` · `seed: int ≥0` · `task_set: TaskSetRef{version: pattern ^(dev\|v[0-9]+\.[0-9]+)$, sha256}` · `scorer_version: SemVer` · `answering: AnsweringConfig{provider: str, model: str, temperature: float (finite, ≥0), prompt_sha256, truncation: TruncationRule{kind: TruncationKind, limit: int ≥1 (unit set by kind, characters for head_chars)}}` · `parsers: tuple[ParserInfo{parser_id, package, package_version: str (PEP 440, not semver), extra: str \| None, model_revisions: tuple[ModelRevision{repo, revision: GitRevision}]}]` · `environment: Environment{python_version, os, cpu, threads, uv_lock_sha256: Sha256 \| None (None when installed without a lock), torch_version: str \| None, system_tools: tuple[ToolVersion{name, version}]}` · `settings: tuple[SettingEntry{name: field name, not env alias; value: str}]` · `concurrency: int ≥1` · `schema_versions: SchemaVersions{document, task, parse_result, answer, result, run_manifest: int}` | 1:N ParseResult, Answer, Result |

Every tuple of entries in the manifest is validated as sorted and unique by its key: `parsers` by `parser_id`, `model_revisions` by `repo`, `system_tools` by `name`, and `settings` by `name`. This makes byte equality enforced, not a convention.

**Arrow schemas** (`arrow.py`). Each row table has a `schema_version` column. Columns shared by both variants (the `ParseBase` or `AnswerBase` fields, plus `status`) are non nullable. Columns owned by a single variant are nullable, and on read `from_arrow_row` keeps exactly the columns of the variant named by `status`. It never strips by `None`, because `cost_usd=None` and `http_status=None` are real values. Types: IDs, enums, hashes, and text are `pa.string()`. Counts and ms are `pa.int64()`. `cost_usd` is `pa.decimal128(18, 6)`. Bools are `pa.bool_()`. No timestamps appear in row tables. A pyarrow `ArrowInvalid` raised during conversion is wrapped in `SchemaError`.

Every `run_id`, `doc_id`, and `parser_id` on a row record is required. `ParseResult`, `Answer`, and `Result` row models all carry `run_id` and `parser_id`.

On disk: a task set is `data/tasks/<version>/documents.jsonl` plus `tasks.jsonl`, canonical JSON lines sorted by ID. The manifest is `runs/<run_id>/manifest.json`. Row records go to Parquet (feature 13 writes them, using the Arrow schemas defined here).

**State transitions**: none. Records are immutable facts written once. "Change" means writing a new record in a new run.

**API surface** (the `parsebench.schemas` package and `parsebench.errors`; pure functions, no I/O, local library, no auth):

| Function / constant | Module | Key inputs | Key outputs | Key errors |
|---|---|---|---|---|
| `Document`, `Task`, `Result`, `RunManifest` classes; `ParseResult` and `Answer` union aliases (`Annotated[ParseOk \| ParseFailed, Field(discriminator="status")]`) with `PARSE_RESULT` and `ANSWER` `TypeAdapter` constants. A bad or missing `status` raises an error that names `status` | `document.py`, `task.py`, `parse.py`, `answer.py`, `result.py`, `manifest.py` | field values or JSON | validated frozen record | `ValidationError` (wrapped as `SchemaError` by the codec) |
| `canonical_json(record) -> bytes` | `canonical.py` | any record | sorted key, compact, UTF-8 JSON bytes | none |
| `sha256_hex(data: bytes) -> Sha256` | `canonical.py` | bytes | hex digest | none |
| `task_set_sha256(documents_bytes: bytes, tasks_bytes: bytes) -> Sha256` | `canonical.py` | the stored file bytes of `documents.jsonl` and `tasks.jsonl` | `sha256_hex((sha256_hex(documents_bytes) + "\n" + sha256_hex(tasks_bytes)).encode())`. An empty file is `b""` | none |
| `dump_jsonl(records) -> bytes` / `parse_jsonl(data: bytes, kind: RecordKind, source: str) -> tuple[...]` | `codec.py` | records / bytes + kind + source name for messages | canonical sorted JSON lines / validated records | `SchemaError` (attributes `source`, `line`, `field` as dotted loc, `message`; never the input value); `UnknownSchemaVersion` |
| `parse_json(data: bytes, kind, source)` / `build(kind, data: dict[str, JsonValue])` | `codec.py` | one JSON document (the manifest) / a plain dict from a builder | validated record | same |
| `upgrade(kind, data, *, registry=UPGRADES, current=CURRENT_VERSIONS) -> dict[str, JsonValue]` + `UPGRADES` (read only mapping of `(kind, from_version)` to pure function) + `CURRENT_VERSIONS` | `upgrade.py` | raw JSON dict | dict at the current version | `SchemaError` (missing or invalid version); `UnknownSchemaVersion` (newer, or a gap in the chain) |
| `PARSE_RESULT_ARROW`, `ANSWER_ARROW`, `RESULT_ARROW` (`pa.Schema` constants) + `to_arrow_row(record) -> dict` / `from_arrow_row(kind, row) -> record` | `arrow.py` | record / row dict | Arrow ready dict / record. Union variants are flattened under `status`, and the other variant's columns are null and stripped on read | `SchemaError` |
| `check_task_set(docs, tasks)` | `integrity.py` | documents, tasks | `None` on success | `IntegrityError` listing IDs |
| `check_result_consistency(manifest, tasks, parses, answers, results)` | `integrity.py` | one run's manifest, task set, and rows | `None` | `IntegrityError`: duplicate ParseResult per (doc, parser); Answer without an ok parse; outcome or `normalized_answer` mismatch; wrong `run_id`; `parser_id` not in manifest; `doc_id` disagreeing with its Task |
| `check_run_complete(manifest, tasks, results)` | `integrity.py` | manifest, task set, results | `None` | `IntegrityError` listing missing, duplicate, or unknown (task, parser) pairs |
| `verify_raw(path_bytes: bytes, expected: Sha256)` | `integrity.py` | bytes read by the caller | `None` | `IntegrityError` |
| `settings_snapshot(settings) -> tuple[SettingEntry, ...]` + `SECRET_SETTING_NAMES` constant | `manifest.py` | `Settings` | sorted non secret entries (Paths as POSIX strings) | none |
| `write_snapshots()` / `python -m parsebench.schemas.snapshot` | `snapshot.py` | none | writes `schemas/json/<kind>.v<N>.json` from `json_schema(mode="validation")` (`TypeAdapter.json_schema()` for the unions). It only creates missing files and refuses to overwrite one. This is the only I/O in the package, run by hand | none |
| `ParseBenchError`, `SchemaError`, `UnknownSchemaVersion`, `IntegrityError` | `parsebench/errors.py` | | typed exceptions | |

The integrity checks raise instead of returning a bool, because a failed check is a broken invariant (an AGENTS.md rule), not an expected failure. `None` on success is a plain procedure return, not a sentinel value.

**Value sourcing** (who fills each field; schemas only validates):

| Record | Value | Source |
|---|---|---|
| Document | `doc_id`, `pages`, `knobs`, `provenance`, `source_data_sha256` | generator (feature 4) or real set labelling (feature 10) |
| Document | `sha256` | `sha256_hex` of the PDF bytes, computed by the generator at write time |
| Task | `question`, `gold`, `answer_type`, `source_ref` | generator from its structured source data (feature 4) or the labelling protocol (feature 10). `gold` is canonical per `answer_type`, and feature 7 defines the canonical forms |
| ParseOk | `raw_path`, `raw_sha256`, `raw_format` | harness writes the adapter's text output to `raw/parse/...`, then hashes the written bytes (features 5 and 12) |
| ParseOk | `latency_ms` | measured inside the worker, warmup excluded (spec 0001) |
| ParseOk | `cost_usd` | adapter: the vendor's reported cost, `0` for local parsers, `None` if not reported (features 5 and 20) |
| Parse*/Answer* | `attempts` | harness retry loop (spec 0001 retry rules) |
| AnswerOk | `prompt_sha256`, `truncated`, `input_sha256`, tokens | answering client (feature 6): hash of the exact prompt template, the truncation outcome, the hash of the truncated text sent, and the provider's reported token counts |
| AnswerOk | `answer_text`, `raw_call_path`, `raw_call_sha256` | answering client: extracted answer, plus the raw request and response JSON written to `raw/answer/...` and hashed |
| Result | `outcome`, `normalized_answer`, `normalized_gold` | grader (feature 7) from Task + ParseResult + Answer. `parse_failed` and `answer_failed` come straight from the status, with no grading |
| Result, manifest | `scorer_version` | `SCORER_VERSION` constant in `parsebench.scoring` (feature 7 creates it at `1.0.0`, feature 19 owns the bump rules) |
| RunManifest | `run_id` | CLI edge: today's UTC date + `secrets.token_hex(4)` |
| RunManifest | `created_at` | CLI edge clock, UTC |
| RunManifest | `seed` | CLI option, default `determinism.DEFAULT_SEED` |
| RunManifest | `task_set.version`, `task_set.sha256` | the task set folder name + `task_set_sha256` over the stored bytes of its two files, read by the caller |
| RunManifest | `answering.*` | feature 6's pinned constants |
| RunManifest | `parsers[*]` | each adapter's self report (package version via `importlib.metadata`, model revisions from the prefetch pins) |
| RunManifest | `environment.*` | `platform.platform()` (os), `platform.machine()` + `platform.processor()` (cpu), `sys.version_info`, `Settings.threads`, `sha256_hex(uv.lock bytes)` or None when absent, torch's `__version__` if importable, and tool versions reported by the adapters that shell out |
| RunManifest | `settings` | `settings_snapshot(get_settings())` |
| RunManifest | `concurrency` | harness config (feature 12; `1` until then) |
| RunManifest | `schema_versions` | each model's current `schema_version` literal |

**Key invariants**:
- Every record is frozen, uses strict validation, and forbids extra fields. Every collection is a tuple.
- `task_id` fully matches `{doc_id}-q` plus two or more digits. `doc_id` and `task_id` are unique within a task set, and every Task's `doc_id` exists.
- Stored task set files are never rewritten. The task set sha256 covers their bytes. Upgrades happen in memory at load.
- One ParseResult per (run, doc, parser). One Answer per (run, task, parser), and only when that doc's ParseResult is `ok`. Exactly one Result per (run, task, parser) for every task in the set and every parser in the manifest.
- `outcome == parse_failed` exactly when the ParseResult is failed. `outcome == answer_failed` exactly when the Answer is failed. Otherwise the outcome is `correct` or `incorrect`.
- `normalized_answer is None` exactly when the outcome is `parse_failed` or `answer_failed`.
- `Result.doc_id` and `Answer.doc_id` equal the Task's `doc_id`.
- Every raw file's bytes hash to the sha256 its record names.
- Every `parser_id` on a row appears in its run's `manifest.parsers`. A run never mixes two versions of one parser.
- No `SettingEntry.name` is in `SECRET_SETTING_NAMES`. That constant is derived from the `Settings` fields typed `SecretStr` (or `SecretStr | None`), so new secrets are covered automatically.
- A model's JSON Schema equals the committed snapshot for its current `schema_version`. Committed snapshots are only ever added, never edited. If a Pydantic upgrade alone changes the generated text, that is the one allowed regeneration without a bump, done in its own commit.
- `schemas` does no I/O except `snapshot.py`. File reads and writes belong to `storage` and the CLI.

**Security model**: a local library with no users or roles. The one sensitive surface is secrets, and they never enter a record. The manifest snapshot is an allowlist (it skips SecretStr fields), and a validator rejects any secret name. Raw files may contain real document text, which is covered by each document's recorded license (feature 10). No PII or regulated data is in scope.

**Configuration required**: none. No new environment variables.

**Critical test scenarios**:
- Happy path: build one Document, two Tasks, a ParseOk, two AnswerOks, and two Results plus a manifest. All validate, round trip through JSON and Arrow, pass every cross check, and a Result rebuilt with a stub grader equals the original. Verifies **AC-1**, **AC-5**, **AC-7**, **AC-8**.
- Failure case: a ParseFailed doc yields `parse_failed` Results with no Answer. A Result claiming `correct` for it raises `IntegrityError`. A raw file with one flipped byte fails `verify_raw`. Verifies **AC-3**, **AC-5**, **AC-8**.
- Malformed input: a table driven test over each record covers `"12"` for an int, an unknown field, a naive datetime, an uppercase sha256, a `..` path, and a negative cost. Each raises `SchemaError` naming the field, and JSON lines errors name the line. Verifies **AC-1**.
- Versioning: a newer `schema_version` raises `UnknownSchemaVersion`. A test only upgrade chain lifts a v1 dict to v3. Editing a field without a bump fails the snapshot test. Verifies **AC-2**, **AC-9**.
- Secret leak (stands in for auth here): with `answer_api_key` and `hf_token` set, the manifest JSON contains neither value nor field name, and a manifest built with a secret entry raises an error. Verifies **AC-4**.
- Determinism: records built with fields in different orders give identical `canonical_json` bytes. `dump_jsonl` gives identical bytes for shuffled input order, so `task_set_sha256` over those bytes is stable. Costs `0`, `0.0`, and `0.000000` serialize identically. Verifies **AC-6**.

## Build plan

Skateboard: each milestone leaves a usable package that the next Release 1 feature can import right away. Feature 4 (the generator) needs Documents and Tasks first.

**Milestone 1: records you can write and trust**
0. Add `pyarrow` to the core dependencies and update `uv.lock` (`uv add pyarrow`). Check whether Pyright strict passes with pyarrow's own hints. If it doesn't, add `pyarrow-stubs` to the `dev` group. Satisfies **AC-7**.
1. Add `src/parsebench/errors.py` with the four exception classes. Satisfies **AC-1**, **AC-2**, **AC-8**.
2. Add `schemas/types.py` (constrained types, enums) and `schemas/base.py` (the `Record` base config). Satisfies **AC-1**.
3. Add Document (with `Knobs`, `SyntheticOrigin`, and `RealOrigin`) and Task. Satisfies **AC-1**.
4. Add ParseOk and ParseFailed, then AnswerOk and AnswerFailed, as discriminated unions with `TypeAdapter` constants. Add Result. Satisfies **AC-1**, **AC-3**, **AC-5**.
5. Add RunManifest with its nested models, `settings_snapshot`, `SECRET_SETTING_NAMES`, and the secret name validator. Satisfies **AC-4**.

**Milestone 2: canonical form and the codec**
6. Add `canonical.py` (`canonical_json`, `sha256_hex`, `task_set_sha256`). Satisfies **AC-6**.
7. Add `codec.py` (`dump_jsonl`, `parse_jsonl`, `parse_json`), which wraps `ValidationError` into `SchemaError` with the source, line, and field. Satisfies **AC-1**, **AC-7**.

**Milestone 3: cross record checks**
8. Add `integrity.py` (`check_task_set`, `check_result_consistency`, `check_run_complete`, `verify_raw`) and the stub grader rebuild test. Satisfies **AC-5**, **AC-8**.

**Milestone 4: versioning guard and Arrow mapping**
9. Add `upgrade.py` (an empty `UPGRADES` registry at v1, with the chain logic) and route `codec` through it. Satisfies **AC-2**.
10. Add `snapshot.py`, commit `schemas/json/*.v1.json`, and add the snapshot drift test. Add a CI step that fails when any existing `src/parsebench/schemas/json/*.v*.json` differs from the base branch (`git diff --exit-code origin/main -- <existing files>`). Satisfies **AC-9**.
11. Add `arrow.py` (three `pa.Schema` constants plus row converters) and the round trip tests for both variants and for None cost. Satisfies **AC-7**.
12. Export the public surface from `schemas/__init__.py`, and add docstrings on every public name. Satisfies **AC-1**.

## Consequences

**Positive**:
- A bug in any stage fails at the boundary with a precise message, instead of skewing a score.
- Any archived run can be regraded exactly, which delivers spec 0001's firm reproducibility promise and unblocks feature 19.
- Parsing once per document cuts parse calls by the number of questions per document, and keeps every question on a document grounded in the same text.
- Shape drift is caught by a test, not by a confused rescore months later.

**Negative / tradeoffs**:
- Strict mode adds friction. Builders must pass enum members, dates, and nested instances, or go through `codec.build`. Every read takes the JSON path, which costs one extra encode per Arrow row.
- JSON Schema snapshots don't capture custom validators (Decimal rounding, the UTC check, path layout, sorted tuples). Changing only a validator still needs a manual version bump decision, which the snapshot test can't catch.
- The Arrow schemas are written by hand next to the models, so every field exists in two places. Only the round trip tests keep them in sync.
- Each later field addition (features 8, 9, 17, 18) costs a version bump, a snapshot, and an upgrade function. Expect several bumps during Releases 2 to 4.
- The upgrade registry grows forever. Old functions can't be deleted while any published run uses that version.
- pyarrow ships incomplete type hints, so Pyright strict may need `pyarrow-stubs` or a narrow ignore in `arrow.py` only.
- `Result` copies `doc_id` from Task for convenient slicing, and an invariant check has to keep it honest.

**Neutral**:
- Spec 0001 and `src/parsebench/storage/AGENTS.md` say "one raw output per task and parser". This spec refines it to one parse output per (doc, parser) plus one answer call per (task, parser).
- The error hierarchy in `errors.py` is project wide. Later features add their own subclasses there.

## Follow-up

- [ ] After this ships, `/sync` should update `src/parsebench/storage/AGENTS.md` (the raw layout `raw/parse/...` and `raw/answer/...`) and the matching line in spec 0001.
- [ ] Feature 7 (grading) defines the canonical `gold` form per `AnswerType` and creates `SCORER_VERSION`. Task validation stays type agnostic until then.
- [ ] Feature 11 (freeze) decides whether the held out split lives in a separate hashed list. Task deliberately has no `split` field.
- [ ] Feature 9 adds `variant_of` and scan noise to Document as a version bump, with an upgrade function.
- [ ] Feature 16 (discard policy) defines its own Discard record outside this spec.
- [ ] Feature 6 confirms or extends `TruncationKind` (it starts with `head_chars`), and feature 12 owns redacting vendor error text before it becomes a `message`.
