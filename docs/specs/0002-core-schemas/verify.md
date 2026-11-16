# Verify: core schemas · spec 0002 · updated 2026-11-16
_Steps derived from spec 0002 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Commands
- [x] `uv run pytest tests/test_schemas.py -q` → all pass → AC-1 to AC-9
- [x] `uv run python -c "import parsebench.schemas"` from the repo root → imports with no error → AC-1
- [x] Pyright strict over `src/parsebench/errors.py` and `src/parsebench/schemas` → 0 errors (pyarrow types come from `pyarrow-stubs`) → AC-1
- [x] `uv run python -m parsebench.schemas.snapshot` on a clean tree → writes nothing (all six `*.v1.json` already exist and match) → AC-9
- [x] Edit one field type in `task.py` (say `gold: str` to `gold: int`) without bumping → `test_json_schema_matches_committed_snapshot[task]` fails; `write_snapshots()` raises `FileExistsError`. Revert afterwards → AC-9
- [x] Once snapshots are on `origin/main`: change a byte in `src/parsebench/schemas/json/task.v1.json`, run `scripts/check-schema-snapshots.sh` → exits 1. Revert → exits 0 → AC-9
- [x] `uv lock --check` → passes (pyarrow in core deps, pyarrow-stubs in dev) → AC-7

## Behavior checks (Python REPL, `uv run python`)
- [x] `parse_jsonl` on a Document line with `"pages":"12"` → `SchemaError` with `field == "pages"`, the right `line`, and the message does not contain `12` → AC-1
- [x] Same for an unknown key, a duplicate key, `NaN`, a BOM, a blank line, a `\r\n` ending, a naive `created_at`, an uppercase sha256, a `..` path, and a negative `cost_usd` → each a `SchemaError` naming the field or line → AC-1
- [x] A record with `schema_version: 2` → `UnknownSchemaVersion`; `schema_version: true`, `"1"`, `0`, or missing → `SchemaError` → AC-2
- [x] `ParseOk` with an `error_kind`, or `ParseFailed` with a `raw_path` → `ValidationError`; a row with `status: "maybe"` → `SchemaError` with `field == "status"` → AC-3
- [x] Build a manifest from `settings_snapshot(Settings())` with `PARSEBENCH_ANSWER_API_KEY` and `HF_TOKEN` set to long distinctive values → `canonical_json` contains neither the values nor the names; `SettingEntry(name="hf_token", value="x")` raises → AC-4
- [x] Store Tasks, a ParseOk, and Answers via `dump_jsonl`, read them back, regrade with a stub grader → Results equal the originals; flip one raw byte → `verify_raw` raises `IntegrityError` → AC-5
- [x] `cost_usd` given as `"0"`, `0`, `0.0`, and `"0.000000"` → identical `canonical_json` bytes containing `"0.000000"`; `created_at` given as `+00:00` → serialized ending in `Z`; `dump_jsonl` of shuffled tasks → identical bytes and `task_set_sha256` → AC-6
- [x] `to_arrow_table` then `from_arrow_table` for ParseOk (Decimal cost and None cost), ParseFailed (with and without `http_status`), AnswerOk (empty `answer_text`), AnswerFailed, and Result (both `normalized_answer` states) → equal records; `cost_usd` column is `decimal128(18, 6)` → AC-7
- [x] Each cross check: duplicate `doc_id`, Task with unknown `doc_id`, two ParseResults per (doc, parser), Answer with a failed or missing parse, Result outcome that disagrees, wrong `run_id`, `parser_id` not in manifest, row `doc_id` not matching its Task, run with a missing, duplicate, or unknown Result → `IntegrityError` whose `ids` name the offenders → AC-8

## Value sourcing (one per row; schemas only validate, so each checks the edge the source must meet)
- [x] Document `doc_id`, `pages`, `knobs`, `provenance`: `pages=0`, a `doc_id` with an uppercase letter, `origin: "scanned"` → each rejected; `Knobs()` defaults all `False` → AC-1
- [x] Document `sha256`: equals `sha256_hex(pdf_bytes)`; a 63 char or uppercase hash is rejected → AC-1
- [x] Task fields: `question` with trailing space or empty `gold` is rejected (not stripped); `task_id` `inv-0002-q01` on `doc_id` `inv-0001` is rejected → AC-1
- [x] ParseOk `raw_path`, `raw_sha256`, `raw_format`: `raw_format=markdown` with a `.txt` path is rejected; the path must be `raw/parse/<parser_id>/<doc_id>.md` → AC-5
- [x] ParseOk `latency_ms`: `-1` rejected, `0` accepted → AC-1
- [x] ParseOk `cost_usd`: `None` (vendor did not report) and `0` (local parser) stay distinct after JSON and Arrow round trips; 7 decimal places rejected → AC-6, AC-7
- [x] `attempts`: `0` rejected on every Parse and Answer variant → AC-1
- [x] AnswerOk `prompt_sha256`, `truncated`, `input_sha256`, tokens: negative tokens rejected; `truncated` must be a JSON bool (`"false"` rejected) → AC-1
- [x] AnswerOk `answer_text`, `raw_call_path`, `raw_call_sha256`: empty `answer_text` accepted; a `raw_call_path` for a different task rejected → AC-5
- [x] Result `outcome`, `normalized_answer`, `normalized_gold`: `parse_failed` with a `normalized_answer` rejected; `correct` with `None` rejected → AC-8
- [x] `scorer_version` on Result and manifest: `1.0` and `v1.0.0` rejected, `1.0.0` accepted → AC-4
- [x] RunManifest `run_id`: `2026-02-30-0123abcd` (not a real date) rejected; date must equal `created_at`'s UTC date, so a run created at 23:30 in UTC+5:30 (18:00 UTC) still uses the UTC date → AC-4
- [x] RunManifest `created_at`: `+05:30` offset rejected, naive rejected → AC-4
- [x] RunManifest `seed`: negative rejected → AC-4
- [x] RunManifest `task_set`: version `v1.0` and `dev` accepted, `1.0` rejected; sha256 equals `task_set_sha256` over the stored file bytes → AC-6
- [x] RunManifest `answering.*`: `temperature` of `-0.1` or `inf` rejected; `truncation.limit=0` rejected → AC-4
- [x] RunManifest `parsers[*]`: unsorted or duplicate `parser_id`s rejected; a `revision` that is not 40 hex chars rejected → AC-4
- [x] RunManifest `environment.*`: `uv_lock_sha256=None` and `torch_version=None` accepted; unsorted `system_tools` rejected → AC-4
- [x] RunManifest `settings`: `settings_snapshot` writes paths as given (`~/x` stays `~/x`, never resolved to a home folder), leaves out `threads` and both secrets → AC-4
- [x] RunManifest `concurrency`: `0` rejected → AC-4
- [x] RunManifest `schema_versions`: `current_schema_versions()` equals `CURRENT_VERSIONS` for all six kinds → AC-2

## Acceptance-criteria coverage
- AC-1: malformed table, codec rejections, no echo, frozen, value sourcing shape checks · AC-2: upgrade chain and unknown version steps · AC-3: union mixing step · AC-4: secret leak step and manifest rows · AC-5: regrade and `verify_raw` step · AC-6: canonical bytes step · AC-7: JSON and Arrow round trip steps · AC-8: cross check step · AC-9: snapshot drift, `write_snapshots` refusal, and CI guard script steps
