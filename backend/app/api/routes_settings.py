"""Settings / providers / TryHackMe credentials API."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api.deps import db_session
from app.db.models import ProviderConfig
from app.schemas.settings import (
    CategoryStatus,
    ProviderIn,
    ProviderOut,
    ProviderPresetOut,
    SettingsStatus,
    THMCredentials,
    THMStatus,
)
from app.config import get_settings as get_app_settings
from app.services.providers import PRESETS, get_preset, supported_kinds
from app.services.secrets_service import (
    delete_secret,
    has_secret,
    set_secret,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---- TryHackMe -------------------------------------------------------------
@router.get("/thm", response_model=THMStatus)
async def thm_status(db: AsyncSession = Depends(db_session)) -> THMStatus:
    configured = await has_secret(db, "thm.email") and await has_secret(db, "thm.password")
    session_valid = await has_secret(db, "thm.session_cookie")
    email_masked = None
    if configured:
        from app.services.secrets_service import get_secret

        email = await get_secret(db, "thm.email")
        if email:
            user, _, domain = email.partition("@")
            if user:
                masked = user[0] + "***" + (user[-1] if len(user) > 1 else "")
                email_masked = f"{masked}@{domain}" if domain else masked
    return THMStatus(
        configured=configured, session_valid=session_valid, email_masked=email_masked
    )


@router.put("/thm")
async def set_thm_credentials(
    creds: THMCredentials, db: AsyncSession = Depends(db_session)
) -> dict:
    await set_secret(db, "thm.email", creds.email)
    await set_secret(db, "thm.password", creds.password)
    # Invalidate any cached session so a fresh login is forced
    await delete_secret(db, "thm.session_cookie")
    return {"ok": True}


@router.delete("/thm")
async def clear_thm_credentials(db: AsyncSession = Depends(db_session)) -> dict:
    for k in ("thm.email", "thm.password", "thm.session_cookie"):
        await delete_secret(db, k)
    return {"ok": True}


# ---- Providers -------------------------------------------------------------
@router.get("/providers/kinds", response_model=List[str])
async def list_kinds() -> List[str]:
    return supported_kinds()


@router.get("/providers/presets", response_model=List[ProviderPresetOut])
async def list_presets() -> List[ProviderPresetOut]:
    """UI-friendly preset list with default model + base URL per provider.

    The `oauth_supported` flag is True only when both the preset advertises
    OAuth *and* the server actually has the GitHub OAuth client configured.
    """
    s = get_app_settings()
    github_oauth_ready = bool(s.github_oauth_client_id and s.github_oauth_client_secret)
    out: List[ProviderPresetOut] = []
    for p in PRESETS:
        oauth_supported = "oauth" in p.auth_methods and (
            p.kind != "github_models" or github_oauth_ready
        )
        out.append(
            ProviderPresetOut(
                kind=p.kind,
                label=p.label,
                description=p.description,
                default_model=p.default_model,
                default_base_url=p.default_base_url,
                auth_methods=list(p.auth_methods),
                api_key_help=p.api_key_help,
                needs_local_runtime=p.needs_local_runtime,
                oauth_supported=oauth_supported,
            )
        )
    return out


@router.get("/providers", response_model=List[ProviderOut])
async def list_providers(db: AsyncSession = Depends(db_session)) -> List[ProviderOut]:
    rows = (await db.scalars(select(ProviderConfig).order_by(ProviderConfig.id))).all()
    out: List[ProviderOut] = []
    for r in rows:
        creds_ok = False
        if r.auth_method == "api_key":
            creds_ok = await has_secret(db, f"provider.{r.id}.api_key")
        elif r.auth_method == "oauth":
            creds_ok = await has_secret(db, f"provider.{r.id}.oauth_access_token")
        elif r.auth_method == "none":
            creds_ok = True
        out.append(
            ProviderOut(
                id=r.id,
                name=r.name,
                kind=r.kind,
                model=r.model,
                base_url=r.base_url,
                auth_method=r.auth_method,
                has_credentials=creds_ok,
                is_default=r.is_default,
            )
        )
    return out


@router.post("/providers", response_model=ProviderOut, status_code=201)
async def create_provider(
    payload: ProviderIn, db: AsyncSession = Depends(db_session)
) -> ProviderOut:
    if payload.kind not in supported_kinds():
        raise HTTPException(400, f"Unknown provider kind: {payload.kind}")

    preset = get_preset(payload.kind)
    # Fill in sensible defaults from the preset so the UI doesn't have to
    # ask the user for name / model / base_url / auth_method.
    name = (payload.name or (preset.label if preset else payload.kind)).strip()
    model = (payload.model or (preset.default_model if preset else "")).strip()
    base_url = payload.base_url or (preset.default_base_url if preset else None)
    auth_method = payload.auth_method or (
        preset.auth_methods[0] if preset else "api_key"
    )

    if not model:
        raise HTTPException(400, "A model name is required.")
    if preset and auth_method not in preset.auth_methods:
        raise HTTPException(
            400,
            f"auth_method '{auth_method}' not allowed for {payload.kind}.",
        )

    if payload.is_default:
        # Demote all existing defaults
        rows = (await db.scalars(select(ProviderConfig))).all()
        for r in rows:
            r.is_default = False
    row = ProviderConfig(
        name=name,
        kind=payload.kind,
        model=model,
        base_url=base_url,
        auth_method=auth_method,
        is_default=payload.is_default,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    if payload.api_key:
        if auth_method != "api_key":
            raise HTTPException(400, "api_key requires auth_method=api_key.")
        await set_secret(db, f"provider.{row.id}.api_key", payload.api_key)

    return ProviderOut(
        id=row.id,
        name=row.name,
        kind=row.kind,
        model=row.model,
        base_url=row.base_url,
        auth_method=row.auth_method,
        has_credentials=bool(payload.api_key) or auth_method == "none",
        is_default=row.is_default,
    )


@router.delete("/providers/{provider_id}", status_code=204, response_class=Response)
async def delete_provider(provider_id: int, db: AsyncSession = Depends(db_session)) -> Response:
    row = await db.get(ProviderConfig, provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found.")
    for k in (
        f"provider.{provider_id}.api_key",
        f"provider.{provider_id}.oauth_access_token",
    ):
        await delete_secret(db, k)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


class _ProviderApiKeyIn(BaseModel):
    api_key: str


@router.put("/providers/{provider_id}/api_key", status_code=204, response_class=Response)
async def set_provider_api_key(
    provider_id: int,
    payload: _ProviderApiKeyIn,
    db: AsyncSession = Depends(db_session),
) -> Response:
    row = await db.get(ProviderConfig, provider_id)
    if row is None:
        raise HTTPException(404, "Provider not found.")
    if row.auth_method not in ("api_key", "oauth"):
        raise HTTPException(400, "This provider does not accept API keys.")
    if not payload.api_key.strip():
        raise HTTPException(400, "API key is empty.")
    # GitHub Models accepts a PAT in the same Authorization: Bearer header
    # as OAuth, so we store it under the OAuth slot if auth_method is oauth.
    slot = (
        f"provider.{provider_id}.oauth_access_token"
        if row.auth_method == "oauth"
        else f"provider.{provider_id}.api_key"
    )
    await set_secret(db, slot, payload.api_key.strip())
    return Response(status_code=204)


@router.post("/providers/{provider_id}/default", status_code=204, response_class=Response)
async def set_default_provider(
    provider_id: int, db: AsyncSession = Depends(db_session)
) -> Response:
    row = await db.get(ProviderConfig, provider_id)
    if row is None:
        raise HTTPException(404, "Provider not found.")
    rows = (await db.scalars(select(ProviderConfig))).all()
    for r in rows:
        r.is_default = (r.id == provider_id)
    await db.commit()
    return Response(status_code=204)


class _ProviderModelIn(BaseModel):
    model: str


@router.put("/providers/{provider_id}/model", status_code=204, response_class=Response)
async def set_provider_model(
    provider_id: int,
    payload: _ProviderModelIn,
    db: AsyncSession = Depends(db_session),
) -> Response:
    row = await db.get(ProviderConfig, provider_id)
    if row is None:
        raise HTTPException(404, "Provider not found.")
    model = payload.model.strip()
    if not model:
        raise HTTPException(400, "Model name is empty.")
    row.model = model
    await db.commit()
    return Response(status_code=204)


@router.get("/providers/{provider_id}/models", response_model=List[str])
async def list_provider_models(
    provider_id: int, db: AsyncSession = Depends(db_session)
) -> List[str]:
    """Best-effort listing of available models for a provider.

    Tries the remote `/models` endpoint when possible; falls back to a
    curated catalog per provider kind so the UI always shows useful
    options. Never raises.
    """
    import httpx
    from loguru import logger
    from app.services.secrets_service import get_secret

    row = await db.get(ProviderConfig, provider_id)
    if row is None:
        raise HTTPException(404, "Provider not found.")

    preset = get_preset(row.kind)

    # Curated fallback per provider kind — used when the remote listing
    # is unreachable, unauthenticated, or returns an unexpected shape.
    fallbacks: dict[str, List[str]] = {
        "openrouter": [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3.5-haiku",
            "google/gemini-2.0-flash-exp",
            "meta-llama/llama-3.3-70b-instruct",
            "mistralai/mistral-large",
            "deepseek/deepseek-chat",
            "qwen/qwen-2.5-72b-instruct",
            "x-ai/grok-2",
        ],
        "openai": [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
            "o1-mini",
            "o1",
            "o3-mini",
            "gpt-3.5-turbo",
        ],
        "anthropic": [
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-3-opus-latest",
            "claude-3-haiku-20240307",
        ],
        "github_models": [
            "gpt-4o-mini",
            "gpt-4o",
            "o1-mini",
            "o1-preview",
            "Phi-3.5-mini-instruct",
            "Phi-3.5-MoE-instruct",
            "Mistral-large-2407",
            "Meta-Llama-3.1-70B-Instruct",
            "Meta-Llama-3.1-405B-Instruct",
            "Cohere-command-r-plus-08-2024",
            "AI21-Jamba-1.5-Large",
        ],
        "github_copilot": [
            "gpt-4o",
            "gpt-4.1",
            "gpt-5",
            "gpt-5-mini",
            "o1",
            "o3-mini",
            "o4-mini",
            "claude-3.5-sonnet",
            "claude-3.7-sonnet",
            "claude-sonnet-4",
            "claude-sonnet-4.5",
            "claude-opus-4",
            "claude-opus-4.1",
            "gemini-2.0-flash-001",
            "gemini-2.5-pro",
            "grok-code-fast-1",
        ],
        "ollama": [
            "llama3.1:8b",
            "llama3.2:3b",
            "llama3.3:70b",
            "mistral:7b",
            "qwen2.5:7b",
            "phi3.5:3.8b",
            "gemma2:9b",
            "deepseek-r1:8b",
        ],
    }

    # Resolve base URL.
    base = row.base_url
    if not base:
        defaults = {
            "openrouter": "https://openrouter.ai/api/v1",
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "github_models": "https://models.inference.ai.azure.com",
            "github_copilot": "https://api.githubcopilot.com",
            "ollama": "http://localhost:11434/v1",
        }
        base = defaults.get(row.kind)

    # Resolve token.
    token = None
    if row.auth_method == "api_key":
        token = await get_secret(db, f"provider.{provider_id}.api_key")
    elif row.auth_method == "oauth":
        token = await get_secret(db, f"provider.{provider_id}.oauth_access_token")

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def _curated() -> List[str]:
        catalog = fallbacks.get(row.kind, [])
        if preset and preset.default_model and preset.default_model not in catalog:
            catalog = [preset.default_model] + catalog
        return catalog

    # Anthropic: no /models endpoint we can hit. Return curated.
    if row.kind == "anthropic" or not base:
        return _curated()

    # GitHub Copilot: dynamic catalog fetched via the unofficial /models
    # endpoint after exchanging the GH token for a short Copilot token.
    if row.kind == "github_copilot":
        from app.services.providers.github_copilot import fetch_copilot_models

        if not token:
            return _curated()
        try:
            ids = await fetch_copilot_models(token)
        except Exception as exc:
            logger.warning("github_copilot: model fetch failed: %s", exc)
            return _curated()
        if not ids:
            return _curated()
        # Put default model first if present
        if preset and preset.default_model in ids:
            ids = [preset.default_model] + [m for m in ids if m != preset.default_model]
        return ids

    # Build candidate URLs (some hosts expose /models, others /v1/models).
    base_clean = base.rstrip("/")
    candidates = [f"{base_clean}/models"]
    if not base_clean.endswith("/v1"):
        candidates.append(f"{base_clean}/v1/models")

    ids: List[str] = []
    last_error: str | None = None
    for url in candidates:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                last_error = f"{resp.status_code} {url}"
                continue
            data = resp.json()
        except Exception as e:  # network / json
            last_error = f"{type(e).__name__}: {e} on {url}"
            continue

        # OpenAI shape: {"data": [{"id": "..."}]}
        for item in (data.get("data") if isinstance(data, dict) else None) or []:
            mid = item.get("id") if isinstance(item, dict) else None
            if mid:
                ids.append(str(mid))
        # Ollama / generic shape: {"models": [{"name": "..."}]}
        for item in (data.get("models") if isinstance(data, dict) else None) or []:
            if isinstance(item, dict):
                mid = item.get("id") or item.get("name")
                if mid:
                    ids.append(str(mid))
        # Azure inference shape: {"value": [{"name": "..."}]}
        for item in (data.get("value") if isinstance(data, dict) else None) or []:
            if isinstance(item, dict):
                mid = item.get("name") or item.get("id")
                if mid:
                    ids.append(str(mid))
        if ids:
            break

    if not ids:
        logger.info(
            "Provider {} ({}): remote /models unavailable ({}); using curated catalog.",
            provider_id, row.kind, last_error or "no data",
        )
        return _curated()

    # Deduplicate, preserve order
    seen: set[str] = set()
    out: List[str] = []
    for m in ids:
        if m not in seen:
            seen.add(m)
            out.append(m)
    # Surface preset's default first if present
    if preset and preset.default_model and preset.default_model in out:
        out.remove(preset.default_model)
        out.insert(0, preset.default_model)
    return out


# ---- Overall status (used by the UI gate) ----------------------------------
@router.get("/status", response_model=SettingsStatus)
async def overall_status(db: AsyncSession = Depends(db_session)) -> SettingsStatus:
    thm_ok = (
        (await has_secret(db, "thm.email") and await has_secret(db, "thm.password"))
        or await has_secret(db, "thm.session_cookie")
    )
    providers = (await db.scalars(select(ProviderConfig))).all()
    providers_ok = False
    if providers:
        # At least one provider with credentials (or auth_method=none)
        for p in providers:
            if p.auth_method == "none":
                providers_ok = True
                break
            if p.auth_method == "api_key" and await has_secret(db, f"provider.{p.id}.api_key"):
                providers_ok = True
                break
            if p.auth_method == "oauth" and await has_secret(
                db, f"provider.{p.id}.oauth_access_token"
            ):
                providers_ok = True
                break

    # Local models are considered ok if env defaults exist (we cannot check
    # downloaded weights cheaply here; the UI surfaces hints on first use).
    local_ok = True

    return SettingsStatus(
        thm=CategoryStatus(
            ok=thm_ok,
            message="OK" if thm_ok else "TryHackMe : configure les identifiants ou importe un cookie de session.",
        ),
        providers=CategoryStatus(
            ok=providers_ok,
            message="OK"
            if providers_ok
            else "Add at least one AI provider with valid credentials.",
        ),
        local_models=CategoryStatus(ok=local_ok, message="Configured."),
        overall_ok=bool(thm_ok and providers_ok and local_ok),
    )
