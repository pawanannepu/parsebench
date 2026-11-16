"""Shared model bases: one strict, frozen config for every record.

`Frozen` is for embedded models (Knobs, origins, manifest parts). `Record`
adds `schema_version` and is the base of the six top level records.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

STRICT_FROZEN = ConfigDict(
    frozen=True,
    strict=True,
    extra="forbid",
    allow_inf_nan=False,
    hide_input_in_errors=True,
)
"""Model config shared by every schema model."""


class Frozen(BaseModel):
    """Strict, immutable model that forbids unknown fields and never echoes input in errors."""

    model_config = STRICT_FROZEN


class Record(Frozen):
    """Top level record carrying its own schema version."""

    schema_version: Literal[1] = 1
