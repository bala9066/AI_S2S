"""
Hardware Pipeline - Central Configuration
All settings loaded from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # --- LLM API Keys ---
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    glm_api_key: str = Field(default="", alias="GLM_API_KEY")

    # --- LLM Models ---
    # Defaults to GLM-4.7 if no Anthropic key; override with PRIMARY_MODEL env var
    primary_model: str = Field(default="glm-4.7", alias="PRIMARY_MODEL")
    fast_model: str = Field(default="glm-4-flash", alias="FAST_MODEL")
    fallback_model: str = Field(default="ollama/qwen2.5-coder:32b", alias="FALLBACK_MODEL")
    last_resort_model: str = Field(default="glm-4.7", alias="LAST_RESORT_MODEL")

    # --- Ollama (Air-Gap) ---
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5-coder:32b", alias="OLLAMA_MODEL")

    # --- GLM / Z.AI (primary when no Anthropic key) ---
    glm_base_url: str = Field(default="https://api.z.ai/api/anthropic", alias="GLM_BASE_URL")
    glm_model: str = Field(default="glm-4.7", alias="GLM_MODEL")
    glm_fast_model: str = Field(default="glm-4-flash", alias="GLM_FAST_MODEL")

    # --- Component Search APIs ---
    digikey_client_id: str = Field(default="", alias="DIGIKEY_CLIENT_ID")
    digikey_client_secret: str = Field(default="", alias="DIGIKEY_CLIENT_SECRET")
    digikey_api_url: str = Field(default="https://api.digikey.com/v3", alias="DIGIKEY_API_URL")
    mouser_api_key: str = Field(default="", alias="MOUSER_API_KEY")
    mouser_api_url: str = Field(default="https://api.mouser.com/api/v2", alias="MOUSER_API_URL")

    # --- Database ---
    database_url: str = Field(
        default="sqlite:///./hardware_pipeline.db",
        alias="DATABASE_URL"
    )

    # --- ChromaDB ---
    chroma_persist_dir: str = Field(default="./chroma_data", alias="CHROMA_PERSIST_DIR")
    chroma_collection_name: str = Field(
        default="component_datasheets",
        alias="CHROMA_COLLECTION_NAME"
    )

    # --- Embedding ---
    embedding_model: str = Field(
        default="text-embedding-3-large",
        alias="EMBEDDING_MODEL"
    )
    offline_embedding_model: str = Field(
        default="nomic-embed-text",
        alias="OFFLINE_EMBEDDING_MODEL"
    )

    # --- Application ---
    app_name: str = Field(default="Hardware Pipeline", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Server ---
    fastapi_host: str = Field(default="0.0.0.0", alias="FASTAPI_HOST")
    fastapi_port: int = Field(default=8000, alias="FASTAPI_PORT")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT")

    # --- Paths ---
    base_dir: Path = Path(__file__).parent
    output_dir: Path = Path(__file__).parent / "output"
    templates_dir: Path = Path(__file__).parent / "templates"
    data_dir: Path = Path(__file__).parent / "data"

    # --- Fallback Chain ---
    @property
    def fallback_chain(self) -> list[str]:
        """LLM fallback order: Opus -> Haiku -> Ollama -> GLM-4"""
        return [
            self.primary_model,
            self.fast_model,
            self.fallback_model,
            self.last_resort_model,
        ]

    @property
    def has_any_llm_key(self) -> bool:
        """True if at least one cloud LLM API key is configured."""
        return bool(self.anthropic_api_key or self.glm_api_key)

    @property
    def is_air_gapped(self) -> bool:
        """True when running fully offline (no cloud LLM keys)."""
        return not self.has_any_llm_key

    @property
    def api_base_url(self) -> str:
        """Get the FastAPI base URL for the backend."""
        return f"http://{self.fastapi_host}:{self.fastapi_port}"

    def get_api_key_status(self) -> dict[str, tuple[bool, str]]:
        """
        Get status of all configured API keys.
        Returns dict of {provider: (is_configured, status_icon)}
        """
        return {
            "Anthropic": (bool(self.anthropic_api_key), "✅" if self.anthropic_api_key else "⬜"),
            "GLM / Z.AI": (bool(self.glm_api_key), "✅" if self.glm_api_key else "⬜"),
            "OpenAI": (bool(self.openai_api_key), "✅" if self.openai_api_key else "⬜"),
            "DigiKey": (bool(self.digikey_client_id and self.digikey_client_secret), "✅" if self.digikey_client_id else "⬜"),
            "Mouser": (bool(self.mouser_api_key), "✅" if self.mouser_api_key else "⬜"),
        }

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance
settings = Settings()
