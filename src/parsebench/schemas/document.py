"""Document: one PDF in a task set, with how it was made or where it came from."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from parsebench.schemas.base import Frozen, Record
from parsebench.schemas.types import DocId, DocType, HttpUrlStr, Name, SemVer, Sha256


class Knobs(Frozen):
    """Layout features the generator switched on for a document (v1 knobs)."""

    tables: bool = False
    multi_column: bool = False
    footnotes: bool = False
    spanning_tables: bool = False


class SyntheticOrigin(Frozen):
    """Provenance of a generated document: generator, version, seed, and source data hash."""

    origin: Literal["synthetic"]
    generator: Name
    generator_version: SemVer
    seed: Annotated[int, Field(ge=0)]
    source_data_sha256: Sha256


class RealOrigin(Frozen):
    """Provenance of a real world document: where it was fetched and under which license."""

    origin: Literal["real"]
    source_url: HttpUrlStr
    license: Name
    """SPDX license ID."""
    retrieved_on: date


Provenance = Annotated[SyntheticOrigin | RealOrigin, Field(discriminator="origin")]
"""Where a document came from, discriminated on `origin`."""


class Document(Record):
    """One PDF in a task set, keyed by `doc_id`. `sha256` covers the PDF bytes."""

    doc_id: DocId
    sha256: Sha256
    doc_type: DocType
    pages: Annotated[int, Field(ge=1)]
    knobs: Knobs
    provenance: Provenance
