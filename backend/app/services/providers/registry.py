"""Provider registry: maps kind -> class and builds instances from DB rows."""
from __future__ import annotations

from typing import Type

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProviderConfig
from app.services.secrets_service import get_secret

from .anthropic import AnthropicProvider
from .base import AIProvider, ProviderCredentials
from .github_copilot import GitHubCopilotProvider
from .openai_compatible import (
    CustomOpenAIProvider,
    GitHubModelsProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
)

_REGISTRY: dict[str, Type[AIProvider]] = {
    "openrouter": OpenRouterProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "github_models": GitHubModelsProvider,
    "github_copilot": GitHubCopilotProvider,
    "ollama": OllamaProvider,
    "custom": CustomOpenAIProvider,
}


def supported_kinds() -> list[str]:
    return sorted(_REGISTRY.keys())


async def build_provider(db: AsyncSession, config: ProviderConfig) -> AIProvider:
    """Instantiate a configured provider, decrypting its credentials."""
    cls = _REGISTRY.get(config.kind)
    if cls is None:
        raise ValueError(f"Unsupported provider kind: {config.kind}")

    api_key = None
    oauth = None
    if config.auth_method == "api_key":
        api_key = await get_secret(db, f"provider.{config.id}.api_key")
    elif config.auth_method == "oauth":
        oauth = await get_secret(db, f"provider.{config.id}.oauth_access_token")

    creds = ProviderCredentials(
        api_key=api_key,
        oauth_token=oauth,
        base_url=config.base_url or None,
    )
    return cls(model=config.model, credentials=creds)
