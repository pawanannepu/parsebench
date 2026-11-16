# Scope: ParseBench

ParseBench is an agent grounded benchmark for document parsing APIs. It runs the same PDFs, the same questions, and the same answering model, swaps only the parser, and scores how often the agent answers correctly. It serves three groups: engineers picking a parser for their agents, agents picking a parser for themselves, and vendors who want a neutral score they can cite.

**Build approach:** Skateboard (ship the smallest benchmark that gives a real, usable number, then grow it release by release, and keep it shippable at every step).
**Workflow:** Beta (after `/develop`, run `/check verify`, then `/test`). This is the project's default level of rigor. Scoring correctness and the task freeze carry `· GA`, because the benchmark's credibility rests on them. `/architect` is the recommended first stop for a feature with a real decision, but you can skip it when you already know how to build the feature. Any feature can carry its own tag to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use `/develop` and skip `/architect`. You decide when a feature is `done`._

**Ground rules every feature honors** (from your brief): freeze tasks before any commercial vendor runs; use one model and one prompt for every parser; truncate every parser's output the same way; report confidence intervals, never bare point scores; publish every discard with its reason; run each parser on its default settings only; count vendor errors as failures and show them in their own column; confirm each vendor's terms allow published results before you run it.

**Budget:** about 6 weeks, solo, free tiers and trial credits only. Roughly: foundations plus Release 1 in week 1, Release 2 in weeks 2 and 3 (labelling is the long pole), Releases 3 and 4 in week 4, Release 5 in week 5, Releases 6 and 7 in week 6.

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Stack & architecture | Foundation | done |
| 2 | Coding standards & tooling | Foundation | in-progress |
| 3 | Core schemas | Foundation | planned |
| 4 | Synthetic invoice generator | Release 1 (P0) | planned |
| 5 | Parser adapter contract + first two adapters | Release 1 (P0) | planned |
| 6 | Answering protocol | Release 1 (P0) | planned |
| 7 | Grading and first scoreboard | Release 1 (P0) | planned |
| 8 | Synthetic doc families and difficulty knobs | Release 2 (P1) | planned |
| 9 | Scanned and noisy variants | Release 2 (P1) | planned |
| 10 | Real document set (50 docs) | Release 2 (P1) | planned |
| 11 | Task set freeze v1.0 + held out split | Release 2 (P1) | planned |
| 12 | Async run harness + raw output archive | Release 3 (P2) | planned |
| 13 | Results store | Release 3 (P2) | planned |
| 14 | Remaining open source adapters | Release 3 (P2) | planned |
| 15 | Bootstrap confidence intervals | Release 4 (P3) | planned |
| 16 | Discard policy | Release 4 (P3) | planned |
| 17 | Efficiency metrics | Release 4 (P3) | planned |
| 18 | Fidelity metrics (text + table structure) | Release 4 (P3) | planned |
| 19 | Versioned scorer + rescore from archive | Release 4 (P3) | planned |
| 20 | Commercial adapter pattern + vendor gate | Release 5 (P4) | planned |
| 21 | LlamaParse adapter | Release 5 (P4) | planned |
| 22 | Reducto adapter | Release 5 (P4) | planned |
| 23 | Unstructured adapter | Release 5 (P4) | planned |
| 24 | Mistral OCR adapter | Release 5 (P4) | planned |
| 25 | Results board | Release 6 (P5) | planned |
| 26 | Headline finding: similarity vs success | Release 6 (P5) | planned |
| 27 | Machine readable results (results.json + llms.txt) | Release 6 (P5) | planned |
| 28 | MCP server (local package) | Release 6 (P5) | planned |
| 29 | Rescore and diff script | Release 7 (P6) | planned |
| 30 | Offline test suite with fixture parsers | Release 7 (P6) | planned |
| 31 | Methodology page | Release 7 (P6) | planned |

## Foundations

### 1. Stack & architecture · done
Decide the stack and repo layout, then scaffold a runnable project so every later release builds on real structure. Your listed stack and repo layout are the starting input for this spec.
**Done when:** the stack and layout are recorded in a spec, and the empty scaffold installs, runs a no op command, and passes build locally.
- [x] Decide the stack (spec): `/architect stack & architecture`
- [x] Scaffold from the decision: `/develop stack & architecture`
- [x] Verify it: `/check verify stack & architecture`
- [x] Test it: `/test stack & architecture`
Spec [0001](../specs/0001-stack-architecture/index.md) · code in `pyproject.toml`, `src/parsebench/`

### 2. Coding standards & tooling · in-progress
Capture conventions and tooling from the real scaffold (lint, format, type strictness, pre commit hooks, CI), then install them.
**Done when:** root `AGENTS.md` reflects the real stack, and lint, format, type checks, and CI run clean on the scaffold.
- [x] Capture conventions + tooling choices: `/audit`

### 3. Core schemas · needs a decision
The strict contracts every part shares: Task, ParseResult, Result, plus a run manifest (task set version, scorer version, model, prompt hash). If these are wrong, rescoring and comparing across runs break.
**Done when:** schemas reject malformed records, every record carries the versions needed to reproduce it, and a Result can be rebuilt from a stored ParseResult alone.
- [ ] Design it (spec): `/architect core schemas`

## Release 1 (P0): the weekend MVP loop

The smallest usable benchmark: 20 synthetic invoices, PyMuPDF and Docling, one model, exact match grading, and one real accuracy number per parser.

### 4. Synthetic invoice generator · needs a decision
Generate 20 invoice PDFs from structured data, so every answer is known exactly, plus short factual questions for each one.
**Done when:** one command generates the same 20 PDFs and question/answer pairs every time from a fixed seed, and every answer can be traced to a field in the source data.
- [ ] Design it (spec): `/architect synthetic invoice generator`

### 5. Parser adapter contract + first two adapters · needs a decision
One common async interface (parse a PDF, return text, latency, cost, and error), with PyMuPDF and Docling behind it on default settings. Adding a fixture parser here, one that returns canned text, lets every later feature be tested without parsers or keys.
**Done when:** both adapters and a fixture parser return valid ParseResults through the same interface; a parser failure becomes an error result, not a crash; no adapter changes vendor defaults.
- [ ] Design it (spec): `/architect parser adapter contract`

### 6. Answering protocol · needs a decision
The fixed answering setup shared by every parser: one model, temperature 0, one prompt, and one truncation rule applied the same way to every output.
**Done when:** the model, prompt, and truncation rule are pinned and hashed into the run manifest, and swapping parsers changes nothing else in the request.
- [ ] Design it (spec): `/architect answering protocol`

### 7. Grading and first scoreboard · needs a decision · GA
Normalize answers (numbers, dates, currency, whitespace, case), grade by exact match against the known answer, and print accuracy per parser. This is the first usable result.
**Done when:** one command runs the 20 invoices through both parsers and prints accuracy per parser; the normalization rules are documented and covered by tests on tricky cases (for example `1,200.00` vs `1200`).
- [ ] Design it (spec): `/architect grading and normalization`

## Release 2 (P1): a task set worth freezing

### 8. Synthetic doc families and difficulty knobs · needs a decision
Grow past invoices to more doc types, with knobs you can turn: tables, multi column layout, footnotes, and tables that span pages. Each task is tagged with its doc type and knobs, so results can be sliced by them later.
**Done when:** each doc family generates from a seed with known answers, each knob can be turned on or off on its own, and every task records its doc type and knob settings.
- [ ] Design it (spec): `/architect synthetic doc families and difficulty knobs`

### 9. Scanned and noisy variants · needs a decision
Degrade generated PDFs into image only versions with scan noise (skew, blur, compression), so the benchmark covers documents that need OCR.
**Done when:** every synthetic doc can produce a scanned variant with a recorded noise level, its answers stay the same as the clean original, and the variant has no text layer.
- [ ] Design it (spec): `/architect scanned and noisy variants`

### 10. Real document set (50 docs) · needs a decision
Fifty permissively licensed real documents with hand labelled short factual questions, so the results are not built on synthetic data alone.
**Done when:** 50 docs are collected, each with its source and license recorded, every question has one unambiguous answer under a written labelling protocol, and anything doubtful is flagged for the discard review.
- [ ] Design it (spec): `/architect real document set`

### 11. Task set freeze v1.0 + held out split · needs a decision · GA
Freeze the full task set as v1.0 with a SHA-256 manifest, and hold out about 20% of the tasks, publishing only their hash.
**Done when:** the frozen set verifies against its manifest, the held out split is chosen reproducibly and publishes only its hash, and every run refuses to start on an unfrozen or mismatched set.
- [ ] Design it (spec): `/architect task set freeze`

## Release 3 (P2): open source parsers at scale

### 12. Async run harness + raw output archive · needs a decision
Run every parser over the frozen set concurrently, with timeouts, retries, and rate limits, and archive every raw output with a checksum under `runs/<date>/`.
**Done when:** a full run finishes unattended, picks up where it left off after an interruption, records every raw output with its checksum, and counts timeouts and errors as failures instead of dropping them.
- [ ] Design it (spec): `/architect run harness`

### 13. Results store · needs a decision
A columnar, file based store for runs and results that you can query locally, with no servers.
**Done when:** every run writes its results to the store, and you can query accuracy by parser, doc type, and knob with one local query.
- [ ] Design it (spec): `/architect results store`

### 14. Remaining open source adapters
Add the remaining open source parsers (Marker, plus any open source editions of the others) on the adapter contract, using default settings.
**Done when:** each new adapter passes the same contract tests as the first two and finishes a full run on the frozen set.
- [ ] Build it: `/develop remaining open source adapters`

## Release 4 (P3): scoring you can defend

### 15. Bootstrap confidence intervals · needs a decision · GA
Report every accuracy figure with a bootstrap 95% confidence interval, overall and per doc type, and never a bare point score.
**Done when:** every reported score carries its interval, the resampling is seeded and reproducible, and the results show when two parsers are not meaningfully different.
- [ ] Design it (spec): `/architect bootstrap confidence intervals`

### 16. Discard policy · needs a decision · GA
A written rule for spotting ambiguous tasks. Every discard applies to every parser and is published with its reason.
**Done when:** discards are decided without looking at which parser got the task right, each one is removed for all parsers at once, and the discard list with reasons ships with every result.
- [ ] Design it (spec): `/architect discard policy`

### 17. Efficiency metrics · needs a decision
Tokens, cost, and latency per task for each parser, plus a separate column for vendor error rate.
**Done when:** every result row carries tokens, cost, and latency (cost is marked unknown where a vendor does not report it), and error rate shows separately from accuracy.
- [ ] Design it (spec): `/architect efficiency metrics`

### 18. Fidelity metrics (text + table structure) · needs a decision
Text similarity against the source text, and table structure similarity against the source tables. You need these secondary scores to produce the headline finding.
**Done when:** every synthetic task with source text gets a text fidelity score, and every task with tables gets a table structure score, both computed from archived raw outputs.
- [ ] Design it (spec): `/architect fidelity metrics`

### 19. Versioned scorer + rescore from archive · needs a decision · GA
Give the scorer a version, and let any past run be rescored from its archived raw outputs without calling a parser again.
**Done when:** every result records its scorer version, and rescoring an archived run with the same scorer version reproduces its results exactly.
- [ ] Design it (spec): `/architect versioned scorer`

## Release 5 (P4): commercial vendors

### 20. Commercial adapter pattern + vendor gate · needs a decision
The shared pattern for paid APIs (credentials, cost capture, rate limits, a budget guard), plus a recorded go or no go per vendor: do the terms allow published results, and do the free credits cover the full frozen set?
**Done when:** each vendor has a recorded terms check and credit estimate before it runs, a run stops before it goes over budget, and keys never reach the archive or the logs.
- [ ] Design it (spec): `/architect commercial adapter pattern`

### 21. LlamaParse adapter
**Done when:** the vendor gate is a go, the adapter passes the contract tests, and a full frozen set run is archived within the free credits.
- [ ] Build it: `/develop LlamaParse adapter`

### 22. Reducto adapter
**Done when:** the vendor gate is a go, the adapter passes the contract tests, and a full frozen set run is archived within the free credits.
- [ ] Build it: `/develop Reducto adapter`

### 23. Unstructured adapter
**Done when:** the vendor gate is a go, the adapter passes the contract tests, and a full frozen set run is archived within the free credits.
- [ ] Build it: `/develop Unstructured adapter`

### 24. Mistral OCR adapter
**Done when:** the vendor gate is a go, the adapter passes the contract tests, and a full frozen set run is archived within the free credits.
- [ ] Build it: `/develop Mistral OCR adapter`

## Release 6 (P5): publishing for people and agents

### 25. Results board · needs a decision
A static results site with a leaderboard (confidence intervals, error column, cost) and dated snapshots, so past results stay citable.
**Done when:** the board builds from the results store with no server, each snapshot keeps its own stable dated URL, discards are linked, and it reads well on a phone.
- [ ] Design it (spec): `/architect results board`

### 26. Headline finding: similarity vs success · needs a decision
Measure how well text similarity predicts agent task success, per parser and per doc type, and publish it as a dated findings page on the board.
**Done when:** the correlation is reported with its uncertainty per parser and per doc type, the page shows where similarity and task success disagree, and the analysis reruns from the results store.
- [ ] Design it (spec): `/architect headline finding`

### 27. Machine readable results (results.json + llms.txt) · needs a decision
A versioned public results file and an llms.txt, so agents can read the benchmark without scraping the board.
**Done when:** results.json follows a published, versioned schema and matches the board exactly, and llms.txt points agents to the results, the methodology, and the MCP server.
- [ ] Design it (spec): `/architect machine readable results`

### 28. MCP server (local package) · needs a decision
A small installable MCP server that reads the published results and offers tools like `get_leaderboard()` and `best_parser_for(doc_type)`.
**Done when:** an agent can install it and call each tool, answers match results.json, and `best_parser_for` returns confidence intervals, not just a winner.
- [ ] Design it (spec): `/architect MCP server`

## Release 7 (P6): the trust layer

### 29. Rescore and diff script
One command that rescores an archived run and diffs it against the published results, so anyone can check the numbers.
**Done when:** running it on a published snapshot reports zero differences, and any difference it finds is listed per task.
- [ ] Build it: `/develop rescore and diff script`

### 30. Offline test suite with fixture parsers · needs a decision
The full pipeline (generate, parse, answer, grade, score, publish) runs in CI on fixture parsers and a stubbed answering model, with no API keys.
**Done when:** CI runs the whole pipeline with no keys and no network, and fails if a scoring or normalization change shifts any known fixture result.
- [ ] Design it (spec): `/architect offline test suite`

### 31. Methodology page
METHODOLOGY.md: how tasks are built, frozen, answered, graded, discarded, and scored, plus a clear section on what the benchmark does NOT measure.
**Done when:** every ground rule above is explained, the "what this does not measure" section is explicit, and the board and llms.txt link to it.
- [ ] Build it: `/develop methodology page`

## Deferred
Out of scope for v1.0, kept here so the plan stays honest.
- **Hosted MCP endpoint**: let agents connect with no install · needs a decision
- **Grow the real set to 100 docs**: tighter intervals in v1.1 · needs a decision
- **Multi model sweep**: check whether parser rankings hold across answering models · needs a decision
- **Tuned settings track**: a separate board for vendor tuned configurations, kept apart from the defaults board · needs a decision
- **Vendor submission flow**: vendors ask for a rerun on a new version and get a citable badge · needs a decision
- **Citable DOI for the frozen set**: a permanent dataset ID for v1.0 · from spec 0001
- **PyPI release**: publish the package so the MCP server installs with a plain `uvx parsebench-mcp` · from spec 0001 · needs a decision

## Legend

**The decision box.** Every feature carries exactly one sub task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack & architecture), so skills find it by that `(spec)` suffix, never by an exact label. Every other box is an execution box, and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves. Each row shows what the feature looks like and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | **`/architect` at spec capture** | `Design it` ticked; spec linked; `Build it: /develop <feature>` + **2 to 5 milestones**; the tier's closing boxes (`Verify it` Alpha+, `Test it` Beta+, `Review it` + `Document it` GA) |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | **you, when you decide it is**; `/sync` reconciles | the boxes you ran are ticked, skipped ones are marked skipped; the tier's last stage is the suggested point to call it done |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise go straight to `/develop` (or `/audit` for standards & tooling). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here.** The scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (built before this workflow) and `dropped` (taken out of scope, kept for history).
- **Workflow tier tag** beside a heading (e.g. `· GA`) sets that one feature's rigor above or below the project default; no tag means it inherits the default.
- **Workflow** (header line) is the project default, what runs after `/develop`: **Prototype** = nothing; **Alpha** = `/check verify`; **Beta** = `/check verify` then `/test`; **GA** = adds a fresh model `/check review` then `/document`.
- **Pointer line** (`spec <n> · code in <path>`): the spec link is added by `/architect`, the code path by `/develop`.
