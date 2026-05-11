"""Centralized application configuration.

All values come from environment variables (see .env.example).
No secret is ever hardcoded.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.bootstrap import ensure_secrets

# Auto-provision APP_MASTER_KEY / SESSION_SECRET if missing. Must run BEFORE
# Settings() is instantiated, hence at module import time.
ensure_secrets()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core
    app_env: str = Field(default="development")
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8001)
    public_base_url: str = Field(default="http://localhost:8001")
    log_level: str = Field(default="INFO")

    # Security (REQUIRED)
    app_master_key: str = Field(default="", description="Base64 32-byte AES-GCM master key")
    session_secret: str = Field(default="", description="Random secret for signing sessions")
    cors_origins: str = Field(default="http://localhost:5173")

    # Database
    database_url: str = Field(default="sqlite+aiosqlite:///./data/app.db")

    # OAuth — GitHub
    github_oauth_client_id: str = Field(default="")
    github_oauth_client_secret: str = Field(default="")

    # Local STT/TTS
    whisper_model: str = Field(default="base")
    whisper_device: str = Field(default="auto")
    whisper_compute_type: str = Field(default="auto")
    piper_voice: str = Field(default="fr_FR-siwis-medium")
    piper_models_dir: str = Field(default="./models/piper")

    # TryHackMe
    thm_base_url: str = Field(default="https://tryhackme.com")
    # Debug / diagnostics — useful when 2FA detection misbehaves.
    # When `thm_headful` is true the Playwright browser opens with a UI
    # (only works on a machine with a display; in Docker on Linux you must
    # mount the X11 socket — easier to run the backend manually for this).
    thm_headful: bool = Field(default=False)
    thm_slow_mo_ms: int = Field(default=0, ge=0, le=2000)
    thm_debug_dir: str = Field(default="./data/thm-debug")

    # Derived
    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def master_key_bytes(self) -> bytes:
        """Decode the master key. Accepts standard or url-safe base64."""
        if not self.app_master_key:
            raise RuntimeError(
                "APP_MASTER_KEY is not set. Run deploy.ps1/deploy.sh to generate one."
            )
        raw = self.app_master_key.strip()
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except Exception:
            key = base64.b64decode(raw + "=" * (-len(raw) % 4))
        if len(key) != 32:
            raise RuntimeError(
                f"APP_MASTER_KEY must decode to 32 bytes (got {len(key)})."
            )
        return key

    @field_validator("app_env")
    @classmethod
    def _env_lower(cls, v: str) -> str:
        return v.lower()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
