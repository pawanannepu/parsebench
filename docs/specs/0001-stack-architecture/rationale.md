# 0001. Stack & architecture: rationale

The decision record behind [index.md](index.md). `/develop` builds from `index.md` and can skip this file.

## Context

ParseBench is a benchmark, not an app. It is a batch pipeline you run from the command line: generate PDFs with known answers, push each PDF through a parser, ask one fixed LLM the same questions over each parser's output, grade the answers, and publish the scores. It has no users signing in, no database server, and no request traffic. The published surface is static (a results site, a results file, llms.txt) plus a small MCP server (a Model Context Protocol server, the standard way agents call tools) that agents install and run locally. One person builds it in about 6 weeks on free tiers and trial credits.

The forces that shape the stack come from what a benchmark must prove, not from scale. **Reproducibility**: anyone must be able to install the exact versions used, rerun the scorer on archived raw outputs, and get the same numbers. **Neutrality**: every parser runs on default settings, through the same interface, under the same answering setup, so the stack must not add hidden behavior (retries that rewrite requests, provider SDK defaults) to some paths and not others. **Isolation**: the parsers being tested are very different. PyMuPDF is a light native library. Docling and Marker pull in torch and model weights (several GB), are blocking and CPU heavy, and can hang or leak memory. The commercial vendors are plain HTTP APIs with rate limits and costs. A crash, hang, or dependency clash in one parser must not corrupt a run or block the others.

There are also licensing and hosting forces. PyMuPDF is dual licensed AGPL 3.0 or commercial, so code that imports it and is distributed inherits AGPL obligations. Marker's code is Apache 2.0, but its model weights use a modified OpenRAIL M license, which is free for research and personal use. Generated PDFs, scanned variants, and archived raw outputs will grow to sizes that bloat a git repo. GitHub hosted runners are free for public repos, but they have 14 GB of disk, which is tight for torch plus model weights.

If this is not decided up front, every later feature (the generator, the adapters, the harness, the scorer, the board, the MCP server) picks its own layout, dependency handling, and execution model. A benchmark whose parts disagree on versions or run conditions cannot defend its numbers.

## Options considered

### Option 1: One installable package, light core, optional extras per parser, local parsers in persistent worker processes

A single Python 3.12 package (`src/parsebench/`) managed by uv with one lockfile. The core (schemas, harness, scoring, storage, CLI, MCP server) installs light. Each parser is an optional extra, so torch only arrives when you ask for Docling or Marker. Each local parser runs in one long lived worker process that speaks JSON lines over a pipe and is killed and restarted on a timeout. Commercial parsers are async HTTP calls. Results go to Parquet files queried with DuckDB. Big binaries live outside git, in a versioned Hugging Face dataset repo, with manifests and checksums kept in git.

**Pros**:
- One install command and one lockfile reproduce the exact environment, which suits a solo builder (basis: reproducible builds through lockfiles)
- CI and the fixture tests never install torch, so they stay fast and inside the free runner disk
- Worker processes give real isolation and hard timeouts for hanging native parsers, without containers
- Everything is files, so there is nothing to operate

**Cons**:
- Docling and Marker extras share one universal lock. Declaring them as conflicting extras keeps the lock resolvable, but it is large and slow
- The worker protocol is one more small interface to write and test
- AGPL on the code may put off some corporate contributors and AGPL averse users of the MCP server

### Option 2: A workspace of packages, with a separate environment per heavy parser

Core, adapters, and the MCP server as separate packages in one repo. Each heavy parser lives in its own virtual environment and runs as a subprocess that reads a PDF path and writes ParseResult JSON.

**Pros**:
- The strongest dependency isolation: Docling and Marker can never clash
- A clean license boundary is possible (the AGPL PyMuPDF adapter could be its own package)

**Cons**:
- Several environments, lockfiles, and release flows for one solo builder in 6 weeks
- The subprocess protocol is a second interface to design and test next to the adapter contract
- Slower to reach the weekend MVP

### Option 3: One container image per parser, orchestrated by the harness

Each parser ships as a container. The harness starts containers and exchanges files with them.

**Pros**:
- The most reproducible runtime, down to system libraries
- Isolation is total

**Cons**:
- Heavy images with torch and weights, slow to build on a laptop and on free CI
- Adds a container runtime as a requirement for anyone who reruns the benchmark
- Far more operational surface than a 6 week solo project can carry

### Option 4: Scripts and notebooks with plain pip

A folder of scripts and notebooks, a `requirements.txt`, everything in one environment.

**Pros**:
- The fastest possible first number
- Zero packaging work

**Cons**:
- No lockfile discipline, so reruns drift
- torch arrives for every install, and Docling and Marker clashes surface with no fix
- Hard to test, hard to turn into an installable MCP server, and weak as a portfolio signal for benchmark engineering

## Rationale

The pipeline is batch, file based, and run by one person, which puts it squarely in "monolith first" territory (basis: monolith first for small teams). Option 1 is the simplest structure that still meets the three forces that matter. Reproducibility comes from one lockfile and versioned dataset releases. Neutrality comes from one adapter interface and a thin answering client that the project controls. Isolation comes from worker processes for the local parsers and extras that keep torch out of everything that does not need it. Options 2 and 3 buy stronger isolation than the evidence requires today, at a cost the 6 week budget cannot absorb. Option 4 gets a number fastest but cannot defend it.

The weak point of Option 1 is a possible future version clash between Docling and Marker inside one lockfile. Two things contain it. The extras are declared as conflicting from day one, so the lock always resolves. And local parsers already run as separate worker processes speaking JSON lines, so a clashing parser can run from its own environment with no change to the harness or scorer. The choice is reversible exactly where it is most likely to break.

The first draft used a stdlib process pool for local parsers. An independent cross check pointed out that a process pool cannot kill one running task: tearing it down on a timeout can leave orphan processes or block, and every rebuild reloads the torch models. A persistent worker per parser that is killed and respawned gives real hard timeouts and loads models once, and it is the same mechanism as the dependency clash escape hatch, so the design has one isolation pattern instead of two.

The same cross check sharpened the reproducibility promise. Rescoring archived outputs is exactly reproducible, and that is what the benchmark promises. Rerunning a model based parser is only best effort across machines (CPU threads, weight revisions, system OCR tools), so the spec pins what it can (CPU only, fixed threads, prefetched weights at pinned revisions, offline runs) and records the rest in the manifest.

A few calls deserve a note. **AGPL for code**: it matches PyMuPDF's terms with no gray area and keeps the project fully open source. The tradeoff is less corporate reuse of the code, which matters little because the data and results (CC BY 4.0) are what others cite. **A thin answering client over httpx** instead of a provider SDK: in a benchmark, the exact request is part of the method, so it must be visible, recorded, and identical for every parser (basis: control your measurement instrument). **Hugging Face for dataset bundles**: free public hosting with git style revisions, where benchmark readers already look, and it keeps the repo small (basis: keep large binaries out of git).

## Tool landscape check (2026-11-16)

Checked during the design conversation by a read only web pass:

- **Docling** 2.x requires Python 3.10+, and the MIT code license is separate from the model licenses. The docs recommend the CPU torch wheel index for CPU only installs. There are no wheels for Python 3.15 yet, so 3.12 is safe.
- **Marker** requires Python 3.10+ and PyTorch. The code is Apache 2.0. The model weights are a modified OpenRAIL M, free for research, personal use, and small startups, and paid above that.
- **PyMuPDF** requires Python 3.11+ and is dual licensed AGPL 3.0 or Artifex commercial.
- **uv** supports optional extras (`[project.optional-dependencies]`), dependency groups (`[dependency-groups]`, PEP 735, with a default `dev` group), and `uv.lock`.
- **The MCP Python SDK** is the `mcp` package, requires Python 3.11+, and supports the stdio transport. The page's examples use `MCPServer` from `mcp.server`, and the FastMCP import path was not confirmed.
- **Typer** is actively maintained (0.29.x). Recent releases moved validation onto Pydantic.
- **GitHub Actions** standard runners are free for public repos, with 4 vCPU, 16 GB RAM, and 14 GB SSD on Linux.
- **Hugging Face Hub** offers best effort free storage for public datasets (a few GB comfortably), with per file guidance under 200 GB. PDF support as raw files was not stated on the page checked.
- **GitHub Releases** assets must each be under 2 GiB.

## References

**Project sources**:
- `docs/scope/scope.md`, row 1 (Stack & architecture) and the ground rules in its header
- The project brief's stack list and repo layout (the starting input for this spec)

**Practices & standards**:
- Monolith first for small teams
- Reproducible builds through lockfiles
- Control your measurement instrument (no hidden behavior in the answering path)
- Keep large binaries out of git

**Links** (web verified during the design conversation):
- Docling repository: https://github.com/docling-project/docling
- Docling installation guide: https://docling-project.github.io/docling/getting_started/installation/
- Marker repository and license: https://github.com/datalab-to/marker
- PyMuPDF on PyPI: https://pypi.org/project/PyMuPDF/
- uv, managing dependencies: https://docs.astral.sh/uv/concepts/projects/dependencies/
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- GitHub hosted runners: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- Hugging Face Hub storage limits: https://huggingface.co/docs/hub/storage-limits
