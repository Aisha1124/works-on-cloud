"""App settings, read from environment variables (and .env in dev)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Gemini
    gemini_api_key: SecretStr | None = None
    gemini_model: str = ""

    # Google Cloud
    gcp_project_id: str = ""
    gcp_region: str = "asia-southeast1"
    firestore_database: str = "(default)"
    gcs_bucket: str = ""

    # App
    store_backend: Literal["local", "firestore"] = "local"
    base_url: str = "http://localhost:8000"
    owner_key: SecretStr | None = None

    # Internal paths. Not listed in .env.example; the defaults work everywhere.
    data_dir: Path = REPO_ROOT / "data"
    uploads_dir: Path = REPO_ROOT / "uploads"
    dashboard_dist: Path = REPO_ROOT / "dashboard" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
