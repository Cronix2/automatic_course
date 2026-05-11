"""Provider presets: sensible defaults so the UI does not need to ask the
user for `name`, `base_url`, and (often) `model`. The user picks a preset
and only provides credentials (API key) — or starts an OAuth flow.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


AuthMethod = Literal["api_key", "oauth", "none"]


class ProviderPreset(BaseModel):
    kind: str
    label: str                       # human-readable name shown in the UI
    description: str
    default_model: str               # used unless the user overrides
    default_base_url: Optional[str]  # `None` -> use the provider class default
    auth_methods: List[AuthMethod]   # ordered: first = recommended
    api_key_help: Optional[str] = None
    needs_local_runtime: bool = False  # e.g. Ollama


PRESETS: List[ProviderPreset] = [
    ProviderPreset(
        kind="openrouter",
        label="OpenRouter",
        description="Accès unifié à 100+ modèles via une seule clé API.",
        default_model="openai/gpt-4o-mini",
        default_base_url=None,
        auth_methods=["api_key"],
        api_key_help="https://openrouter.ai/keys",
    ),
    ProviderPreset(
        kind="openai",
        label="OpenAI",
        description="API OpenAI directe (GPT-4o, o1, etc.).",
        default_model="gpt-4o-mini",
        default_base_url=None,
        auth_methods=["api_key"],
        api_key_help="https://platform.openai.com/api-keys",
    ),
    ProviderPreset(
        kind="anthropic",
        label="Anthropic",
        description="Claude Sonnet / Haiku.",
        default_model="claude-3-5-sonnet-latest",
        default_base_url=None,
        auth_methods=["api_key"],
        api_key_help="https://console.anthropic.com/settings/keys",
    ),
    ProviderPreset(
        kind="github_models",
        label="GitHub Models",
        description="Modèles hébergés par GitHub. Authentification OAuth ou PAT (`models:read`).",
        default_model="gpt-4o-mini",
        default_base_url=None,
        auth_methods=["oauth", "api_key"],
        api_key_help="https://github.com/settings/tokens (scope: models:read)",
    ),
    ProviderPreset(
        kind="ollama",
        label="Ollama (local)",
        description="Modèles tournant en local via Ollama.",
        default_model="llama3.1:8b",
        default_base_url="http://localhost:11434/v1",
        auth_methods=["none"],
        needs_local_runtime=True,
    ),
]


def get_preset(kind: str) -> Optional[ProviderPreset]:
    return next((p for p in PRESETS if p.kind == kind), None)
