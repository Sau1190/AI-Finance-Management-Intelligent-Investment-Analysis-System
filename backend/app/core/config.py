"""Application settings loaded from environment variables.

Beginner view:
  The app should not hardcode secrets. A `.env` file (or real environment
  variables) supplies values. This module reads them once at startup.

Technical view:
  Pydantic Settings maps env vars to a typed Settings object.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPLOAD_DIR = BACKEND_ROOT / "storage" / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Finance Management"
    app_env: str = "development"
    app_debug: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ai_finance"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_bytes: int = 10 * 1024 * 1024
    upload_dir: Path = DEFAULT_UPLOAD_DIR
    exports_dir: Path = BACKEND_ROOT / "storage" / "exports"
    extracts_dir: Path = BACKEND_ROOT / "storage" / "extracts"
    analysis_dir: Path = BACKEND_ROOT / "storage" / "analysis"
    market_dir: Path = BACKEND_ROOT / "storage" / "market"
    max_processing_rows: int = Field(
        default=50_000,
        description="Rows per worksheet/CSV beyond this are reported, not fully processed.",
    )
    max_pdf_pages: int = Field(
        default=200,
        description="Pages per PDF beyond this are reported as too large, not fully extracted.",
    )
    market_data_provider: str = Field(
        default="alpha_vantage",
        description="Which market data adapter to use. Only 'alpha_vantage' is implemented.",
    )
    market_data_timeout_seconds: float = Field(
        default=10.0, description="Per-request timeout for market data providers."
    )
    alpha_vantage_api_key: str = ""
    news_provider: str = Field(
        default="newsapi", description="Which news adapter to use. Only 'newsapi' is implemented."
    )
    news_timeout_seconds: float = Field(default=10.0, description="Per-request timeout for news providers.")
    news_page_size: int = Field(default=50, ge=1, le=100, description="Articles requested per news fetch.")
    news_api_key: str = ""
    llm_api_key: str = ""
    current_phase: int = Field(default=9, description="Development phase marker for health responses.")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
