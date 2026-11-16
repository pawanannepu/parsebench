"""The `parsebench` command line (spec 0001, CLI row; verify.md steps 3 to 5)."""

import os

import pytest
from typer.testing import CliRunner

from parsebench import __version__
from parsebench.cli import app

SUBCOMMANDS = [
    "generate",
    "freeze",
    "verify",
    "prefetch",
    "run",
    "score",
    "rescore",
    "build-site",
    "publish-data",
]


@pytest.fixture
def runner():
    return CliRunner()


def test_help_lists_every_pipeline_subcommand(runner):
    # covers: verify.md step 3 (C: `--help` lists the 9 subcommands)
    result = runner.invoke(app, ["--help"], env={"COLUMNS": "200"})

    assert result.exit_code == 0
    for name in SUBCOMMANDS:
        assert name in result.output


def test_version_prints_package_version_and_exits_zero(runner):
    # covers: verify.md step 4 (DW: runs a no op command)
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"parsebench {__version__}"


def test_package_version_is_0_1_0():
    assert __version__ == "0.1.0"


def test_no_arguments_shows_help_instead_of_doing_anything(runner):
    result = runner.invoke(app, [])

    assert "Usage" in result.output
    assert "generate" in result.output


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_unbuilt_stage_exits_1_and_says_so_on_stderr(runner, name):
    # covers: verify.md step 5 (a stub never fakes success)
    result = runner.invoke(app, [name])

    assert result.exit_code == 1
    assert f"`parsebench {name}` is not built yet" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_unbuilt_stage_help_marks_it_not_built(runner, name):
    result = runner.invoke(app, [name, "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == 0
    assert "Not built yet" in result.output


def test_unknown_subcommand_is_rejected(runner):
    result = runner.invoke(app, ["no-such-stage"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_every_command_applies_determinism_first(runner, monkeypatch):
    # Spec: determinism.apply() runs at the start of every command.
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)

    runner.invoke(app, ["run"])

    assert os.environ["TZ"] == "UTC"
    assert os.environ["PYTHONHASHSEED"] == "0"
