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
    primary_model: str = Field(default="claude-opus-4-6", alias="PRIMARY_MODEL")
    fast_model: str = Field(default="claude-haiku-4-5-20251001", alias="FAST_MODEL")
    fallback_model: str = Field(default="ollama/qwen2.5-coder:32b", alias="FALLBACK_MODEL")
    last_resort_model: str = Field(default="glm-4", alias="LAST_RESORT_MODEL")

    # --- Ollama (Air-Gap) ---
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5-coder:32b", alias="OLLAMA_MODEL")

    # --- GLM-4 (Last Resort) ---
    glm_base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4", alias="GLM_BASE_URL")
    glm_model: str = Field(default="glm-4", alias="GLM_MODEL")

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
    def is_air_gapped(self) -> bool:
        """Check if running in air-gapped mode (no API keys)."""
        return not self.anthropic_api_key

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance
settings = Settings()
