# 0002. Core schemas: rationale

Decision record for [index.md](index.md). `/develop` doesn't need this file.

## Context

> ⚠️ Premise note: the scope row says "a Result can be rebuilt from a stored ParseResult alone". That isn't possible as written: the answering model sits between the parse and the grade, and asking it again, even at temperature 0, isn't reproducible. Without an archived answer, spec 0001's firm promise ("rescoring archived raw outputs with the same scorer version gives identical results") can't hold. The right framing: a Result rebuilds from Task + ParseResult + an archived Answer, with no parser or model call. The engineer confirmed this framing.

ParseBench is credible only if its numbers can be checked. Every stage (generate, parse, answer, grade, score, publish) hands data to the next through files, and several later features depend on those files outliving the code that wrote them: rescoring (19), the results store (13), the discard review (16), and the published results.json (27). If a shape is loose, a stage can write something the next stage reads differently, and the score moves with no error raised. That is the failure that kills a benchmark's credibility, and the scope tags scoring correctness at GA rigor for this reason.

The forces at play:
- **Reproducibility across code versions.** Archives are read long after they're written, by newer code. Records must say which shape they are, and old shapes must stay readable.
- **The parse and question grain mismatch.** Parsers work on whole PDFs, but questions are per task, several per document.
- **Error results, not crashes.** Per AGENTS.md, a parser timeout or vendor 4xx is a counted failure, so failure has to be a first class record shape.
- **Three storage forms.** JSON (manifest), JSON lines (task sets, logs, worker pipe), and Parquet (results). Each has its own type quirks for decimals, datetimes, unions, and nulls.
- **Project rules.** Frozen models, tuples, strict Pyright, no implicit Any, no None sentinels, secrets never in manifests.
- **Skateboard.** Release 1 needs the records next, and the generator (feature 4) is the first consumer.

## Options considered

### Option 1: Pydantic as the single source of truth, strict, versioned per record (chosen)

Strict, frozen Pydantic models per record, each with its own integer `schema_version` and pure upgrade functions. Arrow schemas are written by hand next to the models, and JSON Schema snapshots are committed as a drift guard.

**Pros**: one place defines every contract; malformed data fails loudly; old archives stay readable; drift is caught by a test.
**Cons**: Arrow fields are duplicated by hand; every shape change costs a bump, a snapshot, and an upgrade function; strict mode JSON and Python validation paths must be used correctly.

### Option 2: Minimal lax models, one global version, decide storage later

Plain Pydantic models with default (lax) validation, a single package version, and no Arrow mapping or upgrade path until features 13 and 19 need them.

**Pros**: fastest to write; the fewest files; matches Skateboard at its most literal.
**Cons**: coercion hides writer bugs; any change orphans past runs or forces a rushed migration later; the Parquet shape gets decided implicitly by whoever writes feature 13 first.

### Option 3: Schema first (JSON Schema or Arrow as the source, Pydantic generated)

Write language neutral JSON Schema files by hand and generate the Pydantic models with a code generator.

**Pros**: a contract outsiders can read in any language; results.json (feature 27) gets a published schema for free.
**Cons**: adds a code generation step to the build and CI; generated models fight the project's frozen, tuple, and strict Pyright rules; the snapshots in Option 1 already give outsiders a readable schema.

## Rationale

Option 1 is the only one that keeps the firm reproducibility promise over time. Option 2 is cheaper this week, but features 17, 18, and 19 all change Result in Releases 3 and 4. Without per record versions and upgrade functions, each change either strands archived runs or forces a rescue migration under deadline pressure, which is exactly when scoring bugs slip in. Option 3 solves outsider readability, a problem Option 1's committed snapshots already handle, at the cost of a generator that clashes with the project's strict Python rules.

The finer calls follow from the same forces. Parsing per document fixes the grain mismatch and keeps the comparison fair: every question on a document sees the same text. Archiving the Answer is what makes regrading exact. Discriminated unions make the error results rule impossible to violate by construction. Putting the Arrow mapping in `schemas` pins tricky types (Decimal cost, flattened unions) before feature 13 can guess them. Per record integer versions keep a Task change from rippling into Result.

A cross check by a second model then closed 13 gaps the draft left open. The two that mattered most: every read now goes through the JSON validation path, because strict validation in Python mode rejects the plain strings pyarrow returns. And the task set hash now covers the stored file bytes instead of records serialized again, so upgrades can't change a frozen hash.

Each decision was offered as a choice, and the engineer took the recommended option in every case: per document parse grain, regrade from archived answers, the six records, add fields when needed, strict with extra forbidden, an integer version per record, explicit upgrade functions, readable slug IDs with the content hash kept in its own field, typed knobs, origin discriminated provenance, an `answer_type` enum plus canonical gold, `source_ref`, a pointer plus sha256 to raw files, discriminated unions for failures, Decimal or None cost, an attempt count, the extracted answer plus a raw call file, no Answer for a failed parse, four outcomes, a keyed Result with normalized values, a parser name key with versions kept in the manifest, a task set version plus sha256, the full environment capture, a semver scorer with a sha256 prompt, Arrow owned by schemas, JSON Schema snapshots, all three cross checks, a typed `SchemaError`, a canonical JSON function, an allowlisted settings snapshot, and JSON lines task files.
