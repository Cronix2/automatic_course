"""Base abstraction for an AI chat provider.

Every provider must implement `stream_chat`. The orchestrator (routes_ai.py)
talks only to this interface; adding a new provider = adding a subclass +
registering it in `registry.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ChatTurn:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ProviderCredentials:
    api_key: Optional[str] = None
    oauth_token: Optional[str] = None
    base_url: Optional[str] = None


class AIProvider(ABC):
    """Generic chat-completion provider."""

    kind: str = "base"

    def __init__(self, model: str, credentials: ProviderCredentials) -> None:
        self.model = model
        self.credentials = credentials

    @abstractmethod
    async def stream_chat(self, messages: List[ChatTurn]) -> AsyncIterator[str]:
        """Yield text tokens as they arrive."""
        raise NotImplementedError
