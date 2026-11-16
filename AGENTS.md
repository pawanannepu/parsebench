# ParseBench

Agent grounded benchmark for document parsing APIs: same PDFs, same questions, same answering model, only the parser changes. A file based batch pipeline in one Python package, with no servers. Full stack decision: [spec 0001](docs/specs/0001-stack-architecture/index.md).

## Stack

- **Language / Runtime**: Python 3.12 (`>=3.12,<3.14`), stdlib asyncio
- **Framework**: Typer CLI (`parsebench`), local stdio MCP server (`parsebench-mcp`)
- **Key dependencies**: Pydantic v2 + pydantic settings, httpx, numpy/scipy, Parquet (pyarrow) queried with DuckDB, structlog
- **Package manager**: uv, one committed `uv.lock`, `uv_build` backend. Parsers are optional extras (`pymupdf`, `docling`, `marker`); `docling` and `marker` conflict, install one at a time
- **Storage**: run folders under `runs/`, large binaries in a versioned Hugging Face dataset pinned by commit SHA

## Build approach

**Skateboard**: ship the smallest benchmark that gives a real, usable number, then grow it release by release, and keep it shippable at every step.

## Commands

```bash
uv sync                      # install core (no parsers, no torch)
uv sync --extra pymupdf      # add one parser extra
uv run parsebench --help     # run the CLI
uv run pytest                # test
uv run python -m parsebench.schemas.snapshot   # after a schema_version bump, add the new JSON Schema snapshot
uv run ruff check . && uv run ruff format . && uv run pyright   # after /develop tooling
```

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title/index.md` (plus `rationale.md`, `verify.md`). Scope lives in `docs/scope/scope.md`.

## Rules

- Functional style: functions are pure by default (generators, normalization, grading, stats). I/O, subprocesses, HTTP, and clocks live at the edges (CLI, harness, workers, storage) and are explicit.
- Data is immutable: Pydantic models use `frozen=True`, collections are tuples or frozensets, never mutate in place. Module level names are constants only.
- Prefer plain functions and composition over classes and inheritance. Return explicit values instead of `None` sentinels.
- One error pattern: expected failures (a parser error, a timeout, a vendor 4xx) are returned as error results and counted as failures, never raised into a crash. Bugs and broken invariants raise typed exceptions from a small project hierarchy.
- Strict types: full annotations everywhere, Pyright in strict mode, no implicit `Any`.
- Validate settings at startup: all config goes through the pydantic settings model in `settings.py`, which fails fast on missing or bad env vars. Secrets are never logged or written to manifests.
- Docstrings on every public module, class, and function.
- Determinism: call `determinism.py` at the start of every command; randomness only from a seeded `numpy.random.Generator` whose seed goes in the manifest.
- Benchmark fairness (scope ground rules): one model and one prompt for every parser, same truncation, parser default settings only, retries resend the identical request.
- Layout: one subpackage per pipeline stage under `src/parsebench/`, as spec 0001 laid out.
- Test any code that does I/O or calls a model against fixture parsers and the httpx mock transport, never real vendors.
- Shared records (Document, Task, ParseResult, Answer, Result, RunManifest) come only from `parsebench.schemas`; read them through its codec (`parse_jsonl`, `parse_json`, `build`, `from_arrow_row`), never raw `model_validate`. A shape change needs a `schema_version` bump, an upgrade function, and a new snapshot; committed snapshots are never edited ([spec 0002](docs/specs/0002-core-schemas/index.md)). Exceptions live in `src/parsebench/errors.py`.
- Decision log: every decision the engineer takes (a spec choice, a scope change, a tooling pick, a reversal) belongs in [DECISIONS.md](DECISIONS.md). Run `/decisions` after `/scope`, `/architect`, or `/audit`, and `/decisions add "..."` for a choice made in chat. Never renumber or delete; a reversal is a new entry that marks the old one `Superseded`.

## Tooling

Chosen here, installed by `/develop tooling`: Ruff (lint + format), Pyright strict, pre commit hooks running Ruff check, Ruff format, and Pyright on every commit, and GitHub Actions CI per spec 0001 (`uv sync --locked`, `uv lock --check`, lint, types, tests).
CI also runs `scripts/check-schema-snapshots.sh` (fails if a committed `src/parsebench/schemas/json/*.v*.json` changed; spec 0002, AC-9). pyarrow types come from `pyarrow-stubs` in the dev group.
Testing gate: pytest unit + integration tests on fixture parsers and the stubbed answering model (no keys, no torch, no network).

## Git

- integration: off

## Agent skills

- [uv](.claude/skills/uv/): `astral-sh/agent-plugins`, dependencies, extras, lockfile, `uv run`
- [pydantic](.claude/skills/pydantic/): `pydantic/skills`, schemas, validation, settings
- [typer](.claude/skills/typer/): `fastapi/typer`, CLI commands and options
- [huggingface-datasets](.claude/skills/huggingface-datasets/): `huggingface/skills`, reading datasets via the Dataset Viewer API

Declined: third party Typer skills, Hypothesis property testing skill, GitHub Actions hardening skill, GitHub MCP server
MCP servers: Hugging Face MCP (connected), DuckDB / MotherDuck MCP (connected)

## Context files

- [src/parsebench/storage/AGENTS.md](src/parsebench/storage/AGENTS.md): run folders, atomic writes, Parquet + DuckDB
- [src/parsebench/mcp_server/AGENTS.md](src/parsebench/mcp_server/AGENTS.md): local stdio MCP server over published results

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
