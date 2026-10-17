from functools import lru_cache
from pathlib import Path
import sys

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Legal Decision Intelligence Engine"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = (
        "postgresql+psycopg://legal_engine:local_dev_only@localhost:5432/legal_engine"
    )
    uploads_dir: Path = Path(__file__).resolve().parents[3] / "data" / "uploads"
    max_upload_size_bytes: int = 50 * 1024 * 1024
    max_upload_files_per_batch: int = Field(default=10, ge=1, le=50)
    max_case_documents: int = Field(default=200, ge=1, le=10_000)
    max_case_storage_bytes: int = Field(default=1_073_741_824, ge=52_428_800)
    clamav_command: str | None = None
    tesseract_cmd: str | None = None
    # Optional NER worker uses the same supported Python runtime as the API.
    # The legacy OpenNyAI spaCy 3.2 model is not compatible with this runtime.
    legal_ner_python: Path = Path(sys.executable)
    case_timezone: str = "Asia/Kolkata"
    legal_ner_enabled: bool = False
    ocr_review_confidence_threshold: float = 70.0
    advocate_email: str | None = None
    advocate_password_hash: str | None = None
    session_secret: str | None = None
    app_encryption_key: str | None = None
    app_encryption_key_backup_confirmed: bool = False
    session_ttl_seconds: int = Field(default=28_800, ge=300, le=86_400)
    login_attempt_limit: int = Field(default=5, ge=1, le=20)
    login_window_seconds: int = Field(default=900, ge=60, le=86_400)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dimensions: int = Field(default=768, ge=128, le=3072)
    gemini_data_tier: str = "disabled"
    knowledge_graph_enabled: bool = False
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None
    neo4j_database: str = "neo4j"
    neo4j_storage_encryption_confirmed: bool = False
    graph_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    graph_embedding_dimensions: int = 384
    indiacode_api_base_url: str = "https://indiacode.ecourtsindia.com/api/v1"
    indiankanoon_api_base_url: str = "https://api.indiankanoon.org"
    indiankanoon_api_token: str | None = None
    indiankanoon_private_key: str | None = None
    indiankanoon_private_key_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "INDIANKANOON_PRIVATE_KEY_PATH",
            "INDIAN_KANOON_PRIVATE_KEY_PATH",
        ),
    )
    indiankanoon_customer_email: str | None = None
    legal_research_cache_ttl_seconds: int = Field(default=300, ge=0, le=3600)
    legal_research_searches_per_minute: int = Field(default=12, ge=1, le=120)
    chat_messages_per_minute: int = Field(default=12, ge=1, le=120)

    model_config = SettingsConfigDict(
        # Resolve beside the backend package so root-level CLI/test launches and
        # `cd backend` launches load the same local configuration.
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
