"""Tests for the settings module."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from steb.config import Settings

ENV_VARS = [
    "STEB_HOME",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OLLAMA_BASE_URL",
    "EMBEDDING_MODEL",
    "RERANKER_MODEL",
    "AGENT_MAX_CORRECTIVE_LOOPS",
    "GITHUB_TOKEN",
]

#removes steb’s variables from the environment before every test
 # so a key set in your own terminal can’t change the results.
#monkeypatch restores everything afterwards.
@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults() -> None:
    settings = Settings(_env_file=None) #the test dosen't read your real .env
                                        # =>the tests behave the same on every machine.
    assert settings.llm_provider == "anthropic"
    assert settings.agent_max_corrective_loops == 2
    assert settings.steb_home == Path("./data")


def test_env_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AGENT_MAX_CORRECTIVE_LOOPS", "5")
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "ollama"
    assert settings.agent_max_corrective_loops == 5


def test_invalid_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secrets_are_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    settings = Settings(_env_file=None)
    assert "sk-test-123" not in repr(settings)
    assert settings.anthropic_api_key.get_secret_value() == "sk-test-123"


def test_db_path_is_inside_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STEB_HOME", "somewhere")
    settings = Settings(_env_file=None)
    assert settings.db_path == Path("somewhere") / "steb.db"
