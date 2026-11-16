# Verify: Stack & architecture · spec 0001 · updated 2026-11-16
_The spec has no numbered acceptance criteria, so these steps come from the scope's Done when (DW) and the spec's scaffold check in `## Consequences` (C). `/check verify` runs these; `/test` locks the durable ones._

## Commands
- [x] `uv sync --locked` → installs the core with no errors, on Python 3.12 (`uv run python -V` shows 3.12.x) → DW install, C
- [x] `uv pip show torch` → "not found": the core never installs torch → spec Parser isolation
- [x] `uv run parsebench --help` → lists 9 subcommands: generate, freeze, verify, prefetch, run, score, rescore, build-site, publish-data → C
- [x] `uv run parsebench --version` → prints `parsebench 0.1.0`, exit 0 → DW no op command
- [x] `uv run parsebench run` → says it is not built yet, exit 1 (a stub never fakes success) → spec CLI
- [x] `uv run parsebench-mcp` → says it is not built yet, exit 1 → spec MCP server entry point
- [x] `uv lock --check` → passes, with the `pymupdf`, `docling`, and `marker` extras all declared → C
- [x] `uv sync --locked --extra docling --extra marker --dry-run` → refuses: the extras are declared conflicting → spec Parser isolation
- [x] `grep -A3 '^name = "torch"$' uv.lock` → one entry from PyPI (macOS) and one `+cpu` entry from `download.pytorch.org/whl/cpu` (Linux only) → spec torch builds
- [x] `uv sync --locked --extra pymupdf && uv run python -c "import pymupdf"` → imports → spec Parser isolation
- [x] `uv build` → builds the sdist and wheel → DW passes build
- [x] `HF_TOKEN=x PARSEBENCH_THREADS=8 uv run python -c "from parsebench.settings import Settings; print(Settings())"` → threads 8, token printed masked → spec Settings & secrets

## Acceptance-criteria coverage
- DW stack and layout recorded in a spec: already true (spec 0001)
- DW installs: steps 1, 2 · DW runs a no op command: step 4 · DW passes build: step 11
- C (`uv sync`, `--help`, `uv lock` with every extra): steps 1, 3, 7
