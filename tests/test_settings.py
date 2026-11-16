"""Typed settings and secret handling (spec 0001, Settings & secrets row;
verify.md step 12)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from parsebench.settings import Settings, get_settings

pytestmark = pytest.mark.usefixtures("isolated_settings_env")


def test_defaults_match_the_spec():
    settings = Settings()

    assert settings.cache_dir == Path(".cache/parsebench")
    assert settings.runs_dir == Path("runs")
    assert settings.threads == 4
    assert settings.answer_api_key is None
    assert settings.hf_token is None


def test_env_vars_with_the_parsebench_prefix_override_defaults(monkeypatch):
    # covers: verify.md step 12
    monkeypatch.setenv("PARSEBENCH_THREADS", "8")
    monkeypatch.setenv("PARSEBENCH_CACHE_DIR", "/data/cache")
    monkeypatch.setenv("PARSEBENCH_RUNS_DIR", "/data/runs")

    settings = Settings()

    assert settings.threads == 8
    assert settings.cache_dir == Path("/data/cache")
    assert settings.runs_dir == Path("/data/runs")


def test_values_are_read_from_a_dotenv_file_in_the_working_folder(isolated_settings_env):
    (isolated_settings_env / ".env").write_text("PARSEBENCH_THREADS=2\n", encoding="utf-8")

    assert Settings().threads == 2


def test_env_var_wins_over_dotenv_file(isolated_settings_env, monkeypatch):
    (isolated_settings_env / ".env").write_text("PARSEBENCH_THREADS=2\n", encoding="utf-8")
    monkeypatch.setenv("PARSEBENCH_THREADS", "6")

    assert Settings().threads == 6


@pytest.mark.parametrize("bad", ["0", "-1", "four", ""])
def test_invalid_thread_count_fails_at_startup(monkeypatch, bad):
    monkeypatch.setenv("PARSEBENCH_THREADS", bad)

    with pytest.raises(ValidationError):
        Settings()


def test_threads_of_one_is_the_smallest_valid_value(monkeypatch):
    monkeypatch.setenv("PARSEBENCH_THREADS", "1")

    assert Settings().threads == 1


def test_unknown_parsebench_vars_are_ignored(monkeypatch):
    monkeypatch.setenv("PARSEBENCH_SOMETHING_NEW", "x")

    Settings()  # does not raise


@pytest.mark.parametrize("var", ["HF_TOKEN", "PARSEBENCH_HF_TOKEN"])
def test_hf_token_is_read_from_either_name(monkeypatch, var):
    monkeypatch.setenv(var, "hf_abc")

    settings = Settings()

    assert settings.hf_token is not None
    assert settings.hf_token.get_secret_value() == "hf_abc"


def test_secrets_never_appear_in_repr_str_or_json(monkeypatch):
    # covers: verify.md step 12 (token printed masked)
    monkeypatch.setenv("HF_TOKEN", "hf_supersecret")
    monkeypatch.setenv("PARSEBENCH_ANSWER_API_KEY", "sk_supersecret")

    settings = Settings()
    rendered = [repr(settings), str(settings), settings.model_dump_json()]

    for text in rendered:
        assert "hf_supersecret" not in text
        assert "sk_supersecret" not in text


def test_secret_values_are_still_reachable_on_purpose(monkeypatch):
    monkeypatch.setenv("PARSEBENCH_ANSWER_API_KEY", "sk_123")

    key = Settings().answer_api_key

    assert key is not None
    assert key.get_secret_value() == "sk_123"


def test_get_settings_returns_one_cached_instance():
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
