# MCP server

## Overview

Local stdio MCP server (`parsebench-mcp`) that lets agents query published ParseBench results (feature 28). Until then the entry point only reports that it is not built yet.

## Conventions

- Use the official `mcp` Python SDK with stdio transport. No hosting.
- It needs no parser extras: never import adapters, workers, or torch from here.
- It reads a `results.json` pinned to a published snapshot and caches it locally, so tool calls work offline after the first fetch.
- v1 installs from git: `uvx --from git+<repo url> parsebench-mcp`. No PyPI release yet.

## Agent skills

- [mcp-builder](../../../.claude/skills/mcp-builder/): `anthropics/skills`, designing MCP tools and servers

## Related specs

- [0001 Stack & architecture](../../../docs/specs/0001-stack-architecture/index.md)

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
