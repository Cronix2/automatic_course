"""Pydantic schemas for the public API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


# ---- TryHackMe -------------------------------------------------------------
class THMCredentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class THMStatus(BaseModel):
    configured: bool
    session_valid: bool
    email_masked: Optional[str] = None


# ---- Providers -------------------------------------------------------------
ProviderKind = Literal["openrouter", "openai", "anthropic", "github_models", "github_copilot", "ollama", "custom"]
AuthMethod = Literal["api_key", "oauth", "none"]


class ProviderIn(BaseModel):
    # `name` and `model` are optional — if omitted the backend fills them
    # from the preset for the chosen `kind`. This keeps the UI minimal.
    kind: ProviderKind
    name: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, max_length=200)
    base_url: Optional[str] = None
    auth_method: Optional[AuthMethod] = None
    api_key: Optional[str] = None  # write-only, never returned
    is_default: bool = False


class ProviderOut(BaseModel):
    id: int
    name: str
    kind: ProviderKind
    model: str
    base_url: Optional[str]
    auth_method: AuthMethod
    has_credentials: bool
    is_default: bool


# ---- General settings ------------------------------------------------------
class AppSettings(BaseModel):
    """Public, non-secret preferences."""

    whisper_model: str = "base"
    piper_voice: str = "fr_FR-siwis-medium"
    language: str = "fr"
    wake_word_enabled: bool = False
    wake_word: str = "ordinateur"
    push_to_talk_key: str = "Space"
    interruption_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)


# ---- Settings status (for the UI gate) -------------------------------------
class CategoryStatus(BaseModel):
    ok: bool
    message: str


class SettingsStatus(BaseModel):
    thm: CategoryStatus
    providers: CategoryStatus
    local_models: CategoryStatus
    overall_ok: bool


# ---- Provider presets (UI hints) ------------------------------------------
class ProviderPresetOut(BaseModel):
    kind: str
    label: str
    description: str
    default_model: str
    default_base_url: Optional[str] = None
    auth_methods: list[AuthMethod]
    api_key_help: Optional[str] = None
    needs_local_runtime: bool = False
    oauth_supported: bool = False
