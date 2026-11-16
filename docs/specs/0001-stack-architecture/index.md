# 0001. Stack & architecture: one Python package with a light core, per parser extras, and file based storage

**Date**: 2026-11-16
**Status**: Accepted

## Summary

ParseBench is built as one installable Python 3.12 package run from the command line, with no servers. The core (schemas, harness, scoring, storage, CLI, MCP server) stays light, and each parser arrives as an optional extra, so heavy ML parsers like Docling and Marker only install when you ask for them. Each local parser runs in its own long lived worker process that is killed and restarted if it hangs, so one bad parse cannot sink a run. Results are files (Parquet, queried with DuckDB), and big binaries (PDFs, raw outputs) live in a versioned Hugging Face dataset, with their checksums and pinned revisions kept in git.

## Rationale

Reasoning, options weighed, the tool landscape check, and references: see [rationale.md](rationale.md).

## Decision

**Chosen option**: Option 1: One installable package, light core, optional extras per parser, local parsers in persistent worker processes.

Build ParseBench as a single file based Python package (a monolith: one codebase, one install), managed by uv with one lockfile, with parsers isolated by optional extras and by one worker process per local parser, rather than by separate services or containers.

**Implementation skills**: `uv` (`astral-sh/agent-plugins`, `.claude/skills/uv/`) · `pydantic` (`pydantic/skills`, `.claude/skills/pydantic/`) · `typer` (`fastapi/typer`, `.claude/skills/typer/`) · `duckdb-docs`, `query`, `read-file` (`duckdb/duckdb-skills`, `.claude/skills/duckdb-docs/`, `.claude/skills/query/`, `.claude/skills/read-file/`) · `mcp-builder` (`anthropics/skills`, `.claude/skills/mcp-builder/`) · `huggingface-datasets` (`huggingface/skills`, `.claude/skills/huggingface-datasets/`, covers reading datasets through the Dataset Viewer API, not uploading)

## Proposed stack

**Architecture pattern**: a batch pipeline in one package. CLI commands run the stages, and each stage reads and writes files. Nothing runs as a server. The MCP server is a local process that an agent starts over stdio (standard input and output).

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12. `requires-python = ">=3.12,<3.14"`, and `.python-version` set to `3.12` | The safest version for the torch based parsers. Docling, Marker, PyMuPDF (3.11+), and the MCP SDK (3.11+) all support it. CI uses the same version. |
| Packaging | uv with one committed `uv.lock`, the `uv_build` build backend, a `py.typed` marker, and console scripts `parsebench` and `parsebench-mcp` | One command reproduces the exact environment for you, CI, and anyone rerunning the benchmark. |
| Parser isolation | Optional extras per parser (`pymupdf`, `docling`, `marker`, and one per commercial vendor) plus a `dev` dependency group. `[tool.uv] conflicts` declares `docling` and `marker` as conflicting extras from day one | The core and CI never install torch. If Docling and Marker pins ever disagree, the lock still resolves, and each can be installed on its own. |
| torch builds | The CPU torch wheel index for the `docling` and `marker` extras, applied only when `sys_platform == 'linux'` through `[tool.uv.sources]`. macOS uses the normal PyPI wheels | Keeps Linux installs small and GPU free. The CPU index has no macOS wheels, so it must not apply there. |
| Code layout | `src/parsebench/` with subpackages `schemas`, `generators`, `tasks` (freeze, verify, held out split), `adapters`, `workers`, `answering`, `harness`, `scoring` (normalization, grading, fidelity), `stats` (bootstrap, correlation), `storage`, `publish`, `mcp_server`, plus `cli.py`, `settings.py`, and `determinism.py` | One import root with clean boundaries. It keeps your brief's areas as subpackages, and every scope feature has an obvious home. |
| CLI | Typer, one entry point `parsebench` with subcommands `generate`, `freeze`, `verify`, `prefetch`, `run`, `score`, `rescore`, `build-site`, `publish-data` | The scope's "one command" outcomes map to these names. Help text and testing come built in. |
| Schemas | Pydantic v2 models for Task, ParseResult, Result, and the run manifest. Every record carries a schema version | Strict validation at every stage boundary. Feature 3 (Core schemas) designs the fields and the strictness settings. |
| Concurrency | stdlib asyncio | The harness is I/O bound on HTTP calls and worker pipes. asyncio is what httpx and the MCP SDK use. |
| Local parser execution | One long lived worker process per local parser (`workers` subpackage), started with `asyncio.create_subprocess_exec`. The worker loads its models once, then reads one JSON job per line on stdin and writes one JSON result per line on stdout. On a timeout, the harness kills that worker and starts a fresh one. Only one heavy (torch) parser runs at a time, behind a semaphore | Real hard timeouts, no orphan processes, models load once instead of on every restart, and a crash or leak stays inside one worker. Only plain JSON crosses the pipe, so no Python objects or version skew leak across. The same protocol lets a clashing parser later run from its own environment with no harness change. |
| Parser runtime settings | Every local parser runs on CPU, with a fixed thread count (`OMP_NUM_THREADS` and torch threads set from settings). Before a run, `parsebench prefetch <parser>` downloads model weights at pinned revisions into a known cache, and runs then set `HF_HUB_OFFLINE=1` | Weights don't drift between runs, CPU and GPU differences don't change outputs, and nothing downloads in the middle of a timed run. |
| HTTP | httpx (async). Mandatory for the answering LLM client. Commercial adapters use httpx by default, but may use the vendor's official SDK inside that vendor's extra when the API needs upload and polling, as long as the adapter documents the defaults it relies on | One HTTP client on the measured path, with a practical exception for job style vendor APIs. |
| Retries & rate limits | Retry only on transport errors, HTTP 429, and 5xx. Always resend the identical request. Log every attempt. Rate limiting is per vendor, set in settings | Retries can never change what a parser or the model is asked, which keeps the comparison neutral. |
| Answering LLM access | A thin client of the project's own on top of httpx, which records the raw request and response and the prompt hash. In tests and CI it runs against httpx's mock transport (a fake network layer) with canned responses | The exact request is part of the method, and no SDK default may change it. Feature 6 (Answering protocol) picks the provider and model. |
| Latency measurement | Local parser latency is measured inside the worker (wall time of the parse call only). The first call after a worker starts is a warmup and is excluded. The run manifest records the concurrency used | Model load time and queueing don't count against a parser, so latency numbers compare fairly. |
| Run folders | `runs/<YYYY-MM-DD>-<shortid>/` holding `manifest.json`, `log.jsonl`, `raw/` (one raw output file per task and parser, with its SHA-256), and `results/` (Parquet shards). Every file is written to a temp name, then renamed into place | Two runs on one day can't collide. A crash or a laptop sleep never leaves a half written file, which is what lets the harness resume (feature 12). |
| Result storage | Parquet (via pyarrow), one file per run shard, never appended. DuckDB (in process) queries them with a glob such as `runs/*/results/*.parquet`. Raw outputs stay as checksummed files, not Parquet rows | Parquet files can't be appended safely, and shards make resuming simple. Feature 13 (Results store) designs the tables. |
| Stats | numpy and scipy in the core dependencies. Randomness always comes from a seeded `numpy.random.Generator`, and the seed goes into the manifest | Bootstrap intervals (feature 15) and correlation (feature 26) are reproducible within the locked versions. |
| Determinism conventions | `determinism.py` sets `TZ=UTC`, `PYTHONHASHSEED`, and seeds for `random` and numpy, and is called at the start of every command. Freeze checksums hash the frozen bundle built once on one machine. CI only verifies those checksums and never regenerates PDFs to compare bytes | PDF bytes can differ across machines and library builds, so the frozen artifact, not the generator rerun, is the source of truth. |
| Reproducibility promise | Firm: rescoring archived raw outputs with the same scorer version gives identical results. Best effort: rerunning a parser, with every version recorded (package versions, model revisions, torch version, OS, CPU, and system tools such as tesseract or poppler when a parser calls them) | Model based parsers aren't bit for bit reproducible across machines. Promising more would be a claim the benchmark can't keep. |
| Settings & secrets | pydantic settings: a typed settings model that reads env vars and a git ignored `.env`, with a committed `.env.example`. A logging processor redacts any setting marked secret. The manifest records which settings were used, never secret values | Typos and missing keys fail at startup, and keys can't leak into logs or archives. |
| Logging | structlog, one JSON line per event written to the run folder's `log.jsonl`, with readable console output while a run is live | Every run explains itself after the fact, and DuckDB can query the log directly. |
| Tests | pytest, pytest asyncio, and Hypothesis (as dev dependencies) | The standard runner with async support. Hypothesis property tests (generated edge cases) cover normalization and bootstrap code. |
| Lint, format, type checks, task runner | Owned by `/audit` and `/develop tooling` in feature 2 (Coding standards & tooling) | The scaffold only has to install and run. Feature 2 adds the tooling and the CI workflow that checks it. |
| CI | GitHub Actions on standard Linux runners. It installs with `uv sync --locked`, checks `uv lock --check`, and runs lint, types, and tests on fixture parsers with the stubbed answering model, plus a PyMuPDF smoke run. No API keys, no torch. Dependency bots never bump the lock automatically | Fast, free, and inside the 14 GB runner disk. Lock changes are always deliberate, because a benchmark's environment is part of its method. |
| What lives where | **Git**: code, generators, templates, real doc labels and license records (JSON), `data/tasks/v1.0/` manifests with SHA-256 checksums, pinned Hugging Face revisions, run manifests and logs. **Hugging Face**: frozen task set PDFs, scanned variants, real doc PDFs, raw output archives. **Git ignored**: `runs/*/raw/`, `runs/*/results/` until published, `.env`, and the download cache | The repo stays small, and everything in git is either source or a checksum that proves a downloaded file is the right one. |
| Large binaries | Published as bundles in a public Hugging Face dataset repo through `huggingface_hub`. Git pins each bundle by Hugging Face commit SHA, not by tag, because tags can move. The frozen v1.0 task bundle is also attached to a GitHub Release as a mirror. Downloads land in `PARSEBENCH_CACHE_DIR` (default `.cache/parsebench/`), never in tracked folders | Free hosting, checksums that catch tampering, and a second copy that guards against loss. |
| Static site hosting | GitHub Pages | Free, static, and next to the code. Feature 25 (Results board) decides how the site is built and how dated snapshots are kept. |
| MCP server | The official `mcp` Python SDK, stdio transport, shipped in the package as the `parsebench-mcp` entry point. It needs no parser extras. It reads a results.json pinned to a published snapshot and caches it locally, so tool calls work offline after the first fetch. v1 installs from git with `uvx --from git+<repo url> parsebench-mcp`, with no PyPI release | Agents install and run it locally, with no hosting and no heavy dependencies. Feature 28 designs the tools. |
| License | Code: AGPL 3.0. Labels, generated documents, and results: CC BY 4.0. Real documents keep their own licenses, recorded per document in the manifest. The bundle as a whole is labeled "mixed licenses, see manifest" | Matches PyMuPDF's AGPL terms with no gray area, and stays honest about third party documents. |

**Decided in later features, not here** (each owns its choice): the PDF rendering approach for the generator (feature 4), the answering provider, model, and prompt (feature 6), the text fidelity and table structure libraries (feature 18), the site build approach and snapshot mechanism (feature 25), and charting for the findings page (feature 26). The brief's candidates for these (WeasyPrint or ReportLab, RapidFuzz, TEDS) are the starting input for those specs.

**Configuration required** (the settings model reads these; names are final unless feature 6 or 20 renames them):
- `PARSEBENCH_ANSWER_API_KEY`: key for the answering LLM provider (feature 6)
- `PARSEBENCH_CACHE_DIR`: where downloaded bundles and model weights live (default `.cache/parsebench/`, git ignored)
- `PARSEBENCH_RUNS_DIR`: where run folders are written (default `runs/`)
- `PARSEBENCH_THREADS`: CPU thread count for local parsers (default 4)
- `HF_TOKEN`: only to publish bundles to Hugging Face, never needed to read them
- One key per commercial vendor, added by feature 20 (for example `LLAMAPARSE_API_KEY`)

## Consequences

**Positive**:
- `uv sync` plus an extra name reproduces any parser's environment exactly, for anyone.
- The core, CI, and fixture tests run with no torch, no keys, and no network.
- A hanging or crashing local parser costs one task, never the run, and a timeout truly stops it.
- Rescoring archived outputs is exactly reproducible, which is the promise vendors and readers can check.
- Nothing to host or operate: files, a static site, and a local MCP process.

**Negative / tradeoffs**:
- The worker protocol (JSON lines over a pipe) is a small interface you have to write and test, next to the adapter contract.
- Running one heavy parser at a time makes full runs slower on a laptop.
- A universal lock with torch and two conflicting extras is large and slow to resolve.
- Parser reruns are only best effort reproducible, and METHODOLOGY.md has to say so plainly.
- AGPL on the code may discourage some corporate contributors, and some companies ban AGPL tools, which can limit who installs the MCP server.
- Heavy parsers are never tested in CI, so upstream breakage in Docling or Marker shows up only on your machine.
- Hugging Face free storage is best effort. Large raw output archives may need trimming or a second host later.

**Neutral**:
- This folder is not a git repository yet. The scaffold needs `git init` and a GitHub remote before CI and Pages can work.
- Marker's model weights license (free for research and personal use) and PyMuPDF's AGPL both belong in METHODOLOGY.md's licensing notes.
- The scaffold (`/develop stack & architecture`) is checked against the scope row's Done when: `uv sync` installs the empty project, `parsebench --help` lists the subcommands, and `uv lock` resolves with every extra declared (including `docling` and `marker`), so a torch conflict surfaces in week one, not in feature 14.

## Follow-up

- [ ] Before the first push, confirm the Hugging Face dataset repo name and the GitHub repo name.
- [ ] Feature 2 (`/audit`) records the lint, format, and type checking tools, plus the conventions in this spec, into root `AGENTS.md`.
- [ ] Add licensing and reproducibility sections to METHODOLOGY.md (feature 31): AGPL code, mixed license bundles, PyMuPDF's AGPL, Marker's weights license, and the firm versus best effort reproducibility promise.
- [ ] Consider a Zenodo DOI (a permanent, citable ID) for the frozen v1.0 bundle once it ships.
- [ ] Consider a PyPI release of the package after v1 (check the name first), so the MCP server installs with a plain `uvx parsebench-mcp`.
- [ ] Root `AGENTS.md` `## Agent skills` (written by `/audit`) should list the installed project wide skills (`uv`, `pydantic`, `typer`, and `huggingface-datasets`) at root. `duckdb-docs`, `query`, and `read-file` belong in a nested `src/parsebench/storage/AGENTS.md`, and `mcp-builder` in `src/parsebench/mcp_server/AGENTS.md`. Record as declined: the third party Typer skills, the Hypothesis property testing skill, the GitHub Actions hardening skill, and the GitHub MCP server.
- [ ] Connect the MCP servers you chose (a step in your own MCP settings): the official Hugging Face MCP (hosted at `https://huggingface.co/mcp`, for example `claude mcp add --transport http huggingface https://huggingface.co/mcp`), and the DuckDB / MotherDuck MCP (`mcp-server-motherduck`, run through `uvx`). The MotherDuck server was not verified against its official GitHub org, so check its README for the current command and flags before you connect it. Once connected, `/audit` records them on the `MCP servers:` line.
