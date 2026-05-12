"""GitHub Copilot Chat provider (unofficial).

GitHub Copilot exposes an OpenAI-compatible chat endpoint at
`https://api.githubcopilot.com/chat/completions` but auth is done with a
short-lived bearer token obtained from a long-lived GitHub OAuth token
via `GET https://api.github.com/copilot_internal/v2/token`.

Models are fetched dynamically from `GET https://api.githubcopilot.com/models`
so the user sees the same catalogue as VS Code (Claude, Gemini, Grok, GPT…).
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import List

import httpx

from .base import AIProvider, ChatTurn


_COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
_COPILOT_BASE = "https://api.githubcopilot.com"
_COPILOT_CHAT_URL = f"{_COPILOT_BASE}/chat/completions"
_COPILOT_MODELS_URL = f"{_COPILOT_BASE}/models"

# Stable per-process IDs (Copilot tracks them but accepts random UUIDs).
_MACHINE_ID = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
_SESSION_ID = f"{uuid.uuid4()}{int(time.time() * 1000)}"

_EDITOR_HEADERS = {
    "Editor-Version": "vscode/1.95.0",
    "Editor-Plugin-Version": "copilot-chat/0.22.0",
    "User-Agent": "GitHubCopilotChat/0.22.0",
    "Copilot-Integration-Id": "vscode-chat",
    "VScode-SessionId": _SESSION_ID,
    "VScode-MachineId": _MACHINE_ID,
    "Openai-Intent": "conversation-panel",
}


def _per_request_headers() -> dict:
    """Headers that must rotate per request (X-Request-Id is unique)."""
    return {"X-Request-Id": str(uuid.uuid4())}


async def fetch_copilot_models(gh_token: str) -> list[str]:
    """Return the list of model IDs available to this Copilot account.

    Performs the token exchange + a GET on /models. Returns model IDs as
    expected by /chat/completions (e.g. `claude-sonnet-4.5`, `gpt-4o`,
    `gemini-2.5-pro`). Raises `RuntimeError` on auth failure.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Exchange long-lived GH token for short Copilot token
        tok_resp = await client.get(
            _COPILOT_TOKEN_URL,
            headers={
                "Authorization": f"token {gh_token}",
                "Accept": "application/json",
                **_EDITOR_HEADERS,
                **_per_request_headers(),
            },
        )
        if tok_resp.status_code == 401:
            raise RuntimeError(
                "GitHub Copilot: token GitHub rejeté. Vérifie que ton compte "
                "a un abonnement Copilot actif."
            )
        if tok_resp.status_code >= 400:
            raise RuntimeError(
                f"GitHub Copilot: /copilot_internal/v2/token a renvoyé "
                f"{tok_resp.status_code}: {tok_resp.text[:200]}"
            )
        short_token = tok_resp.json()["token"]

        # 2. Fetch available models
        models_resp = await client.get(
            _COPILOT_MODELS_URL,
            headers={
                "Authorization": f"Bearer {short_token}",
                "Content-Type": "application/json",
                **_EDITOR_HEADERS,
                **_per_request_headers(),
            },
        )
        if models_resp.status_code >= 400:
            raise RuntimeError(
                f"GitHub Copilot: /models a renvoyé "
                f"{models_resp.status_code}: {models_resp.text[:200]}"
            )
        data = models_resp.json()
        # Response shape: {"data": [{"id": "...", "name": "...", "capabilities": {...}}]}
        ids = []
        for item in data.get("data", []):
            mid = item.get("id")
            if not mid:
                continue
            # Keep only chat-capable models
            caps = item.get("capabilities", {}) or {}
            ctype = caps.get("type")
            if ctype and ctype != "chat":
                continue
            ids.append(str(mid))
        return ids


class GitHubCopilotProvider(AIProvider):
    """Talk to GitHub Copilot Chat via the unofficial endpoint."""

    kind = "github_copilot"
    default_base_url = _COPILOT_CHAT_URL  # informational only

    # Cached short-lived Copilot token (per process)
    _short_token: str | None = None
    _short_token_expiry: float = 0.0

    async def _refresh_short_token(self) -> str:
        gh_token = self.credentials.oauth_token or self.credentials.api_key
        if not gh_token:
            raise RuntimeError(
                "GitHub Copilot: aucun token GitHub configuré. "
                "Connecte-toi via OAuth GitHub dans Réglages, ou colle un "
                "token obtenu via `gh auth token` (compte avec Copilot actif)."
            )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _COPILOT_TOKEN_URL,
                headers={
                    "Authorization": f"token {gh_token}",
                    "Accept": "application/json",
                    **_EDITOR_HEADERS,
                    **_per_request_headers(),
                },
            )
        if resp.status_code == 401:
            raise RuntimeError(
                "GitHub Copilot: token rejeté (401). Vérifie que ton compte a "
                "bien un abonnement Copilot actif."
            )
        if resp.status_code == 403:
            raise RuntimeError(
                "GitHub Copilot: accès interdit (403). Ton compte n'a pas "
                "d'abonnement Copilot actif (Individual / Business / Enterprise)."
            )
        if resp.status_code == 404:
            raise RuntimeError(
                "GitHub Copilot: 404 sur /copilot_internal/v2/token. "
                "Ton token GitHub n'est PAS un token Copilot. Les tokens "
                "acceptés sont uniquement ceux issus du flow OAuth Copilot "
                "(client_id Iv1.b507a08c87ecfe98) ou obtenus via `gh auth login` "
                "puis `gh auth token` sur un compte avec abonnement Copilot. "
                "Les PAT classiques (Developer Settings) et les tokens OAuth "
                "github_models ne fonctionnent pas ici."
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"GitHub Copilot: échec /copilot_internal/v2/token "
                f"({resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        self.__class__._short_token = data["token"]
        self.__class__._short_token_expiry = float(data.get("expires_at", 0)) - 60
        return self.__class__._short_token

    async def _get_short_token(self) -> str:
        if (
            self.__class__._short_token
            and time.time() < self.__class__._short_token_expiry
        ):
            return self.__class__._short_token
        return await self._refresh_short_token()

    async def stream_chat(self, messages: List[ChatTurn]) -> AsyncIterator[str]:
        token = await self._get_short_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **_EDITOR_HEADERS,
            **_per_request_headers(),
        }
        payload = {
            "model": self.model or "gpt-4o",
            "stream": True,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", _COPILOT_CHAT_URL, headers=headers, json=payload
            ) as resp:
                if resp.status_code == 400:
                    body = await resp.aread()
                    msg = body.decode(errors="replace")[:500]
                    raise RuntimeError(
                        f"Copilot a refusé la requête (400). Vérifie que le "
                        f"modèle « {self.model} » existe bien dans ton "
                        f"abonnement (utilise le bouton « Rafraîchir les "
                        f"modèles » dans Réglages). Détail : {msg}"
                    )
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Copilot error {resp.status_code}: "
                        f"{body.decode(errors='replace')[:500]}"
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
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0] or {}).get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
