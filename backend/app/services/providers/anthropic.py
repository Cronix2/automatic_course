"""Anthropic Messages API streaming provider."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import List

import httpx

from .base import AIProvider, ChatTurn


class AnthropicProvider(AIProvider):
    kind = "anthropic"
    default_base_url = "https://api.anthropic.com/v1"

    async def stream_chat(self, messages: List[ChatTurn]) -> AsyncIterator[str]:
        base = (self.credentials.base_url or self.default_base_url).rstrip("/")
        url = f"{base}/messages"
        api_key = self.credentials.api_key or self.credentials.oauth_token or ""
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Split system message
        system_prompt = "\n\n".join(m.content for m in messages if m.role == "system")
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "stream": True,
            "messages": convo,
        }
        if system_prompt:
            payload["system"] = system_prompt

        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Anthropic error {resp.status_code}: {body.decode(errors='replace')[:500]}"
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "content_block_delta":
                        delta = obj.get("delta", {}).get("text")
                        if delta:
                            yield delta
                    elif obj.get("type") == "message_stop":
                        return
