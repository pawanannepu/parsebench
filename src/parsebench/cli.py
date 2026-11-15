"""The `parsebench` command line.

Each pipeline stage is one subcommand. Stages not built yet are registered as
stubs that exit with code 1 and name the feature that builds them, so a script
can never mistake a stub for a successful run.
"""

from typing import Annotated

import typer

from parsebench import __version__, determinism

app = typer.Typer(
    name="parsebench",
    help="Agent grounded benchmark for document parsing APIs.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"parsebench {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    determinism.apply()


# (command, help, feature that builds it)
_STAGES = [
    ("generate", "Generate synthetic documents and their questions.", "feature 4"),
    ("freeze", "Freeze the task set and write its SHA-256 manifest.", "feature 11"),
    ("verify", "Verify a frozen task set against its manifest.", "feature 11"),
    ("prefetch", "Download a parser's model weights at pinned revisions.", "feature 12"),
    ("run", "Run parsers over the frozen task set.", "feature 12"),
    ("score", "Grade answers and score a run.", "feature 7"),
    ("rescore", "Rescore an archived run without calling any parser.", "feature 19"),
    ("build-site", "Build the static results board.", "feature 25"),
    ("publish-data", "Publish bundles to the Hugging Face dataset repo.", "feature 27"),
]


def _register_stub(name: str, help_text: str, feature: str) -> None:
    def stub() -> None:
        typer.echo(f"`parsebench {name}` is not built yet ({feature}).", err=True)
        raise typer.Exit(code=1)

    app.command(name=name, help=f"{help_text} Not built yet ({feature}).")(stub)


for _name, _help, _feature in _STAGES:
    _register_stub(_name, _help, _feature)
