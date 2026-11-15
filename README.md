# ParseBench

An agent grounded benchmark for document parsing APIs. It runs the same PDFs, the same questions, and the same answering model, swaps only the parser, and scores how often the agent answers correctly.

Status: early scaffold. The CLI subcommands exist but are not built yet.

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.12 for you.

```sh
uv sync                     # core only: no parsers, no torch
uv sync --extra pymupdf     # add one parser
uv sync --extra docling     # heavy parsers install one at a time
uv run parsebench --help
```

`docling` and `marker` are declared as conflicting extras, so install one or the other, not both. Copy `.env.example` to `.env` for keys and paths.

## License

Code: AGPL 3.0 or later (see `LICENSE`). Labels, generated documents, and results: CC BY 4.0. Real documents keep their own licenses, recorded per document in the task manifest.
