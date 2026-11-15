"""Local stdio MCP server that reads published results (feature 28).

The `mcp` SDK is added when feature 28 is built. Until then the entry point
only reports that it is not built yet.
"""

import sys


def main() -> None:
    print("parsebench-mcp is not built yet (feature 28: MCP server).", file=sys.stderr)
    raise SystemExit(1)
