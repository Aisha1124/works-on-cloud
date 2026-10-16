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

    # Gemini. Production: Vertex AI (GOOGLE_GENAI_USE_VERTEXAI=true, project GCP_PROJECT_ID,
    # the service account's credentials). Local development: GEMINI_API_KEY.
    gemini_api_key: SecretStr | None = None
    gemini_model: str = ""
    google_genai_use_vertexai: bool = False
    # The Interactions API on Vertex AI is served from "global" only (preview).
    gemini_location: str = "global"

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

    # Email. "smtp" (Gmail with an app password) or "resend". Without the provider's
    # credentials, emails are not sent, only logged (subject + masked recipient).
    email_provider: Literal["smtp", "resend"] = "smtp"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587  # STARTTLS
    smtp_user: str = ""
    smtp_password: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    # Empty: "KampungCart <SMTP_USER>" for smtp, "KampungCart <onboarding@resend.dev>" for resend.
    email_from: str = ""

    # Internal paths. Not listed in .env.example; the defaults work everywhere.
    data_dir: Path = REPO_ROOT / "data"
    uploads_dir: Path = REPO_ROOT / "uploads"
    dashboard_dist: Path = REPO_ROOT / "dashboard" / "dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
