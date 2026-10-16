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
    # Owner key of the sample shop seeded by scripts/seed_shop.py (mak-kuih). Every other shop
    # gets its own random key when it goes live. This key opens mak-kuih only.
    owner_key: SecretStr | None = None
    # Optional: the sample shop's owner email, so its order emails reach someone.
    sample_owner_email: str = ""

    # Email (Resend). Empty key: emails are not sent, only logged (subject + masked recipient).
    resend_api_key: SecretStr | None = None
    email_from: str = "KampungCart <onboarding@resend.dev>"

    # Internal paths. Not listed in .env.example; the defaults work everywhere.
    data_dir: Path = REPO_ROOT / "data"
    uploads_dir: Path = REPO_ROOT / "uploads"
    dashboard_dist: Path = REPO_ROOT / "dashboard" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
