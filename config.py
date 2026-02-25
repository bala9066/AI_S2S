"""
Hardware Pipeline - Central Configuration
All settings loaded from environment variables with sensible defaults.
Compatible with Python 3.10+ (no pydantic-settings dependency).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, str(default)).lower()
    return val in ("1", "true", "yes", "on")


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


class Settings:
    """Application settings loaded from .env file.

    Reads environment variables at instantiation time so tests can
    modify os.environ before creating a new Settings() instance.
    """

    def __init__(self):
        # --- LLM API Keys ---
        self.anthropic_api_key = _env("ANTHROPIC_API_KEY", "")
        self.openai_api_key = _env("OPENAI_API_KEY", "")
        self.glm_api_key = _env("GLM_API_KEY", "")

        # --- LLM Models ---
        self.primary_model = _env("PRIMARY_MODEL", "glm-4.7")
        self.fast_model = _env("FAST_MODEL", "glm-4-flash")
        self.fallback_model = _env("FALLBACK_MODEL", "ollama/qwen2.5-coder:32b")
        self.last_resort_model = _env("LAST_RESORT_MODEL", "glm-4.7")

        # --- Ollama (Air-Gap) ---
        self.ollama_base_url = _env("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = _env("OLLAMA_MODEL", "qwen2.5-coder:32b")

        # --- GLM / Z.AI ---
        self.glm_base_url = _env("GLM_BASE_URL", "https://api.z.ai/api/anthropic")
        self.glm_model = _env("GLM_MODEL", "glm-4.7")
        self.glm_fast_model = _env("GLM_FAST_MODEL", "glm-4-flash")

        # --- Component Search APIs ---
        self.digikey_client_id = _env("DIGIKEY_CLIENT_ID", "")
        self.digikey_client_secret = _env("DIGIKEY_CLIENT_SECRET", "")
        self.digikey_api_url = _env("DIGIKEY_API_URL", "https://api.digikey.com/v3")
        self.mouser_api_key = _env("MOUSER_API_KEY", "")
        self.mouser_api_url = _env("MOUSER_API_URL", "https://api.mouser.com/api/v2")

        # --- Database ---
        self.database_url = _env("DATABASE_URL", "sqlite:///./hardware_pipeline.db")

        # --- ChromaDB ---
        self.chroma_persist_dir = _env("CHROMA_PERSIST_DIR", "./chroma_data")
        self.chroma_collection_name = _env("CHROMA_COLLECTION_NAME", "component_datasheets")

        # --- Embedding ---
        self.embedding_model = _env("EMBEDDING_MODEL", "text-embedding-3-large")
        self.offline_embedding_model = _env("OFFLINE_EMBEDDING_MODEL", "nomic-embed-text")

        # --- Application ---
        self.app_name = _env("APP_NAME", "Hardware Pipeline")
        self.app_env = _env("APP_ENV", "development")
        self.debug = _env_bool("DEBUG", True)
        self.log_level = _env("LOG_LEVEL", "INFO")

        # --- Server ---
        self.fastapi_host = _env("FASTAPI_HOST", "0.0.0.0")
        self.fastapi_port = _env_int("FASTAPI_PORT", 8000)
        self.streamlit_port = _env_int("STREAMLIT_PORT", 8501)

        # --- Paths ---
        self.base_dir = Path(__file__).parent
        self.output_dir = Path(__file__).parent / "output"
        self.templates_dir = Path(__file__).parent / "templates"
        self.data_dir = Path(__file__).parent / "data"

    @property
    def fallback_chain(self) -> list:
        return [
            self.primary_model,
            self.fast_model,
            self.fallback_model,
            self.last_resort_model,
        ]

    @property
    def has_any_llm_key(self) -> bool:
        return bool(self.anthropic_api_key or self.glm_api_key)

    @property
    def is_air_gapped(self) -> bool:
        return not self.has_any_llm_key

    @property
    def api_base_url(self) -> str:
        return f"http://{self.fastapi_host}:{self.fastapi_port}"

    def get_api_key_status(self) -> dict:
        return {
            "Anthropic": (bool(self.anthropic_api_key), "✅" if self.anthropic_api_key else "⬜"),
            "GLM / Z.AI": (bool(self.glm_api_key), "✅" if self.glm_api_key else "⬜"),
            "OpenAI": (bool(self.openai_api_key), "✅" if self.openai_api_key else "⬜"),
            "DigiKey": (bool(self.digikey_client_id and self.digikey_client_secret), "✅" if self.digikey_client_id else "⬜"),
            "Mouser": (bool(self.mouser_api_key), "✅" if self.mouser_api_key else "⬜"),
        }


# Singleton instance
settings = Settings()
