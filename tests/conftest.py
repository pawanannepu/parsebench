"""Shared fixtures.

`determinism.apply()` runs at the start of every CLI command and changes
process wide state (env vars, the timezone, global random seeds). These
fixtures put that state back after each test, so tests never leak into each
other.
"""

import os
import time

import pytest


@pytest.fixture(autouse=True)
def restore_process_env():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
    if hasattr(time, "tzset"):
        time.tzset()


@pytest.fixture
def isolated_settings_env(monkeypatch, tmp_path):
    """Run with no PARSEBENCH_* or HF_TOKEN vars and an empty working folder,
    so a developer's real env or `.env` can never change the result."""
    for key in list(os.environ):
        if key.startswith("PARSEBENCH_") or key == "HF_TOKEN":
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    return tmp_path
