# Storage

## Overview

Run folders, atomic writes, Parquet result shards, and DuckDB queries over them (features 12 and 13). Still a stub; this doc records the rules spec 0001 fixed so the build follows them.

## Conventions

- One run folder per run: `runs/<YYYY-MM-DD>-<shortid>/` with `manifest.json`, `log.jsonl`, `raw/` (`raw/parse/<parser_id>/<doc_id>.<txt|md>`, one parse per document and parser, and `raw/answer/<parser_id>/<task_id>.json`, one archived answering call per task and parser; each SHA-256 is recorded on its row and checked with `schemas.verify_raw`, per spec 0002), and `results/` (Parquet shards).
- Every file is written to a temp name, then renamed into place. Never leave a half written file.
- Parquet files are never appended. Write one shard per run chunk and query with a DuckDB glob such as `runs/*/results/*.parquet`.
- Raw parser outputs stay as checksummed files, not Parquet rows.
- Parquet rows use the explicit Arrow schemas in `parsebench.schemas.arrow` (`PARSE_RESULT_ARROW`, `ANSWER_ARROW`, `RESULT_ARROW`); convert with `to_arrow_table` / `from_arrow_table`, never `pa.Table.from_pylist` on raw dicts.
- Task sets live at `data/tasks/<version>/documents.jsonl` + `tasks.jsonl`, written once with `schemas.dump_jsonl` and never rewritten; the manifest's task set hash is `schemas.task_set_sha256` over those stored bytes.

## Gotchas

- `runs/*/raw/` and `runs/*/results/` are git ignored until published. Downloads go to `PARSEBENCH_CACHE_DIR`, never to tracked folders.
- With pyarrow 26, a Parquet round trip through an in memory `io.BytesIO` makes Python hang at exit (Arrow thread pool shutdown). Write and read Parquet through real files, in code and in tests.

## Agent skills

- [duckdb-docs](../../../.claude/skills/duckdb-docs/): `duckdb/duckdb-skills`, DuckDB documentation lookup
- [query](../../../.claude/skills/query/): `duckdb/duckdb-skills`, running DuckDB SQL over results
- [read-file](../../../.claude/skills/read-file/): `duckdb/duckdb-skills`, previewing Parquet, JSON, and CSV files
- [designing-data-storage](../../../.claude/skills/designing-data-storage/): `legout/data-agent-skills`, Parquet and Arrow format choices (compression, partitioning, schema evolution). Ignore its lakehouse sections (Delta, Iceberg, Hudi); spec 0001 fixed plain Parquet shards

## Related specs

- [0001 Stack & architecture](../../../docs/specs/0001-stack-architecture/index.md)
- [0002 Core schemas](../../../docs/specs/0002-core-schemas/index.md): records, raw layout, Arrow schemas

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
