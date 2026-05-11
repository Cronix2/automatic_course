"""Shared OpenAI-compatible streaming client.

OpenRouter, OpenAI, GitHub Models and Ollama all expose an OpenAI-style
`/chat/completions` endpoint with Server-Sent Events. We use this single
implementation parameterized by base_url + auth header.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import List

import httpx

from .base import AIProvider, ChatTurn


class OpenAICompatibleProvider(AIProvider):
    """OpenAI-style /v1/chat/completions provider with SSE streaming."""

    default_base_url: str = "https://api.openai.com/v1"

    def _build_headers(self) -> dict[str, str]:
        token = self.credentials.oauth_token or self.credentials.api_key
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _base_url(self) -> str:
        return self.credentials.base_url or self.default_base_url

    async def stream_chat(self, messages: List[ChatTurn]) -> AsyncIterator[str]:
        url = f"{self._base_url().rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "stream": True,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=self._build_headers(), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Provider error {resp.status_code}: {body.decode(errors='replace')[:500]}"
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        obj.get("choices", [{}])[0].get("delta", {}).get("content")
                    )
                    if delta:
                        yield delta


class OpenRouterProvider(OpenAICompatibleProvider):
    kind = "openrouter"
    default_base_url = "https://openrouter.ai/api/v1"


class OpenAIProvider(OpenAICompatibleProvider):
    kind = "openai"
    default_base_url = "https://api.openai.com/v1"


class GitHubModelsProvider(OpenAICompatibleProvider):
    kind = "github_models"
    default_base_url = "https://models.inference.ai.azure.com"


class OllamaProvider(OpenAICompatibleProvider):
    kind = "ollama"
    default_base_url = "http://localhost:11434/v1"
