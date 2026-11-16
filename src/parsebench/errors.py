"""Project wide exception hierarchy for bugs and broken invariants.

Expected failures (a parser error, a timeout, a vendor 4xx) are never raised:
they become error records. These exceptions are for data that breaks a
contract, so a bad record fails loudly at the boundary instead of skewing a
score. Later features add their own subclasses here.

    ParseBenchError
    └── SchemaError
        ├── UnknownSchemaVersion
        └── IntegrityError
"""


class ParseBenchError(Exception):
    """Root of every exception ParseBench raises on purpose."""


class SchemaError(ParseBenchError):
    """A record failed validation.

    Carries where the bad data came from (`source`, `line`) and which field
    broke (`field`, a dotted path). It never carries the offending input value,
    so secrets and document text cannot leak into logs.
    """

    def __init__(
        self,
        message: str,
        *,
        source: str | None = None,
        line: int | None = None,
        field: str | None = None,
    ) -> None:
        """Build the error and a readable `source:line: field: message` string."""
        self.message = message
        self.source = source
        self.line = line
        self.field = field
        where = source or ""
        if line is not None:
            where = f"{where}:{line}"
        parts = [p for p in (where, field) if p]
        super().__init__(": ".join([*parts, message]))


class UnknownSchemaVersion(SchemaError):
    """A record is newer than this code knows, or its upgrade chain has a gap."""


class IntegrityError(SchemaError):
    """Records are each valid but disagree with each other, or a file's hash is wrong.

    `ids` lists the offending record IDs so the caller can find them.
    """

    def __init__(self, message: str, *, ids: tuple[str, ...] = ()) -> None:
        """Build the error, listing the offending IDs after the message."""
        self.ids = ids
        detail = f"{message}: {', '.join(ids)}" if ids else message
        super().__init__(detail)
