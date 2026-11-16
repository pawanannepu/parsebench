# Storage

## Overview

Run folders, atomic writes, Parquet result shards, and DuckDB queries over them (features 12 and 13). Still a stub; this doc records the rules spec 0001 fixed so the build follows them.

## Conventions

- One run folder per run: `runs/<YYYY-MM-DD>-<shortid>/` with `manifest.json`, `log.jsonl`, `raw/` (one raw output per task and parser, with its SHA-256), and `results/` (Parquet shards).
- Every file is written to a temp name, then renamed into place. Never leave a half written file.
- Parquet files are never appended. Write one shard per run chunk and query with a DuckDB glob such as `runs/*/results/*.parquet`.
- Raw parser outputs stay as checksummed files, not Parquet rows.

## Gotchas

- `runs/*/raw/` and `runs/*/results/` are git ignored until published. Downloads go to `PARSEBENCH_CACHE_DIR`, never to tracked folders.

## Agent skills

- [duckdb-docs](../../../.claude/skills/duckdb-docs/): `duckdb/duckdb-skills`, DuckDB documentation lookup
- [query](../../../.claude/skills/query/): `duckdb/duckdb-skills`, running DuckDB SQL over results
- [read-file](../../../.claude/skills/read-file/): `duckdb/duckdb-skills`, previewing Parquet, JSON, and CSV files

## Related specs

- [0001 Stack & architecture](../../../docs/specs/0001-stack-architecture/index.md)

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
