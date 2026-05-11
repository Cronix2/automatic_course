"""GitHub OAuth flow for binding a provider entry to GitHub Models.

Flow:
  1. UI calls GET /api/oauth/github/start?provider_id=<id>
     -> redirects to GitHub authorize URL with state=signed(provider_id).
  2. GitHub redirects back to /api/oauth/github/callback?code=...&state=...
  3. We exchange the code for an access_token (server-side) and store it
     encrypted in `secrets` under `provider.<id>.oauth_access_token`.
"""
from __future__ import annotations

import secrets as pysecrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.config import get_settings
from app.db.models import ProviderConfig
from app.services.secrets_service import set_secret

router = APIRouter(prefix="/api/oauth/github", tags=["oauth"])

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_SCOPE = "read:user"


def _signer() -> URLSafeSerializer:
    s = get_settings()
    if not s.session_secret:
        raise HTTPException(500, "SESSION_SECRET is not configured.")
    return URLSafeSerializer(s.session_secret, salt="github-oauth")


@router.get("/start")
async def start(provider_id: int = Query(...)) -> RedirectResponse:
    s = get_settings()
    if not s.github_oauth_client_id or not s.github_oauth_client_secret:
        raise HTTPException(
            400,
            "GitHub OAuth n'est pas configuré côté serveur. "
            "Créez une OAuth App sur https://github.com/settings/developers, "
            "réglez 'Authorization callback URL' sur "
            f"{s.public_base_url}/api/oauth/github/callback, puis renseignez "
            "GITHUB_OAUTH_CLIENT_ID et GITHUB_OAUTH_CLIENT_SECRET dans .env. "
            "Cela fonctionne aussi en localhost. Astuce : sinon, collez "
            "directement un Personal Access Token via le champ « API key ».",
        )
    state = _signer().dumps(
        {"provider_id": provider_id, "nonce": pysecrets.token_urlsafe(16)}
    )
    params = {
        "client_id": s.github_oauth_client_id,
        "redirect_uri": f"{s.public_base_url}/api/oauth/github/callback",
        "scope": _SCOPE,
        "state": state,
        "allow_signup": "false",
    }
    return RedirectResponse(f"{_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(db_session),
) -> HTMLResponse:
    try:
        data = _signer().loads(state)
    except BadSignature:
        raise HTTPException(400, "Invalid OAuth state.")
    provider_id = int(data.get("provider_id"))
    cfg = await db.get(ProviderConfig, provider_id)
    if cfg is None:
        raise HTTPException(404, "Provider not found.")

    s = get_settings()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": s.github_oauth_client_id,
                "client_secret": s.github_oauth_client_secret,
                "code": code,
                "redirect_uri": f"{s.public_base_url}/api/oauth/github/callback",
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(502, "OAuth token exchange failed.")
        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise HTTPException(502, f"GitHub did not return an access_token: {body}")

    await set_secret(db, f"provider.{provider_id}.oauth_access_token", token)
    # Tiny HTML page that just closes the popup / redirects back
    return HTMLResponse(
        """<!doctype html><html><body style="font-family:sans-serif;background:#0b0118;color:#eee;padding:2rem">
        <h2>GitHub connecté ✅</h2>
        <p>Vous pouvez fermer cette fenêtre.</p>
        <script>setTimeout(()=>window.close(),800)</script>
        </body></html>"""
    )
