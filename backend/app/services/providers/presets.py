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
        label="GitHub Models (Azure)",
        description=(
            "Catalogue Azure AI accessible via PAT GitHub : GPT-4o, o1, Phi, "
            "Llama, Mistral, Cohere. ⚠ Ce n'est PAS GitHub Copilot et ne contient "
            "ni Claude, ni Gemini, ni Grok — pour ceux-là utilise OpenRouter."
        ),
        default_model="gpt-4o-mini",
        default_base_url=None,
        auth_methods=["oauth", "api_key"],
        api_key_help="https://github.com/settings/tokens (scope: models:read)",
    ),
    ProviderPreset(
        kind="github_copilot",
        label="GitHub Copilot (non officiel)",
        description=(
            "Utilise ton abonnement GitHub Copilot via l'endpoint privé Chat. "
            "⚠ API non officielle (utilisée par VS Code) — peut casser sans préavis. "
            "Authentification OAuth GitHub obligatoire ; le compte doit avoir Copilot actif."
        ),
        default_model="gpt-4o",
        default_base_url=None,
        auth_methods=["oauth", "api_key"],
        api_key_help="Token GitHub avec accès Copilot (généré par la CLI gh ou l'extension Copilot)",
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
    ProviderPreset(
        kind="custom",
        label="Personnalisé (OpenAI-compatible)",
        description=(
            "N'importe quel endpoint compatible OpenAI /v1/chat/completions "
            "(API tierce, proxy local, serveur LLM auto-hébergé). "
            "Tu fournis l'URL, le modèle et la clé d'API."
        ),
        default_model="gpt-4o-mini",
        default_base_url="https://api.openai.com/v1",
        auth_methods=["api_key", "none"],
        api_key_help="Clé d'API du service distant (laisser vide si pas nécessaire).",
    ),
]


def get_preset(kind: str) -> Optional[ProviderPreset]:
    return next((p for p in PRESETS if p.kind == kind), None)
