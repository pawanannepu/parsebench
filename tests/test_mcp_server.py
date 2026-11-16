"""The `parsebench-mcp` entry point before feature 28 builds it
(spec 0001, MCP server row; verify.md step 6)."""

import pytest

from parsebench.mcp_server import main


def test_entry_point_exits_1_and_says_it_is_not_built(capsys):
    # covers: verify.md step 6
    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "parsebench-mcp is not built yet" in captured.err
    assert captured.out == ""
