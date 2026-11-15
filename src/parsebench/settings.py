"""Typed settings read from environment variables and a git ignored `.env`.

Secrets are `SecretStr`, so they never print in reprs or logs. The run manifest
records which settings were used, never secret values.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PARSEBENCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    answer_api_key: SecretStr | None = None
    """Key for the answering LLM provider (feature 6)."""

    cache_dir: Path = Path(".cache/parsebench")
    """Where downloaded bundles and model weights live."""

    runs_dir: Path = Path("runs")
    """Where run folders are written."""

    threads: int = Field(default=4, ge=1)
    """CPU thread count for local parsers."""

    hf_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("HF_TOKEN", "PARSEBENCH_HF_TOKEN"),
    )
    """Only needed to publish bundles to Hugging Face, never to read them."""


@lru_cache
def get_settings() -> Settings:
    return Settings()
