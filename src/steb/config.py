"""Application configuration loaded from environment variables and ``.env``.

All settings live in one typed object, ``Settings``. Other modules call ``get_settings()``
instead of reading ``os.environ`` directly, so every variable is validated in one place.
The variables are documented in ``.env.example``.
"""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for steb.

    Values are read from environment variables (case-insensitive) and from a ``.env`` file in
    the current working directory. Real environment variables win over the ``.env`` file.

    Attributes:
        steb_home: Directory holding the SQLite database, indexes and caches.
        llm_provider: Which LLM backend the agent uses.
        llm_model: Model name for the chosen provider (empty until the agent exists).
        anthropic_api_key: API key for Anthropic.
        openai_api_key: API key for OpenAI.
        ollama_base_url: URL of a local Ollama server.
        embedding_model: sentence-transformers model id used for dense retrieval.
        reranker_model: Cross-encoder model id used for reranking.
        agent_max_corrective_loops: Maximum retrieval retries inside the agent.
        github_token: Token for the GitHub API (higher rate limits).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    steb_home: Path = Path("./data")

    llm_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    llm_model: str = ""
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    ollama_base_url: str = "http://localhost:11434"

    embedding_model: str = ""
    reranker_model: str = ""

    agent_max_corrective_loops: int = 2

    github_token: SecretStr = SecretStr("")

    @property
    def db_path(self) -> Path:
        """Path of the SQLite database file inside ``steb_home``."""
        return self.steb_home / "steb.db"


@cache
def get_settings() -> Settings:
    """Return the application settings, created once and reused.

    Returns:
        The shared ``Settings`` instance.
    """
    return Settings()
