"""AI orchestration: enhance a course, chat with interruption."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import ProviderConfig
from app.schemas.course import ChatRequest, EnhanceRequest
from app.services.providers import ChatTurn, build_provider

router = APIRouter(prefix="/api/ai", tags=["ai"])


ENHANCE_SYSTEM = (
    "Tu es un instructeur de cybersécurité expert. Réécris le cours fourni "
    "de manière concise, en français, en développant les aspects techniques "
    "(commandes, protocoles, vulnérabilités, mitigations) avec rigueur. "
    "Utilise un ton clair et pédagogique adapté à une lecture vocale : "
    "phrases courtes, pas de markdown lourd, pas d'URLs longues."
)


async def _get_provider_or_404(db: AsyncSession, provider_id: int):
    cfg = await db.get(ProviderConfig, provider_id)
    if cfg is None:
        raise HTTPException(404, "Provider not found.")
    return await build_provider(db, cfg)


@router.post("/enhance")
async def enhance_course(
    payload: EnhanceRequest, db: AsyncSession = Depends(db_session)
) -> StreamingResponse:
    provider = await _get_provider_or_404(db, payload.provider_id)
    messages = [
        ChatTurn("system", ENHANCE_SYSTEM),
        ChatTurn(
            "user",
            f"Voici le contenu du cours « {payload.content.title} ». "
            f"Réécris-le selon le style « {payload.style} ».\n\n"
            f"{payload.content.markdown}",
        ),
    ]

    async def gen():
        async for tok in provider.stream_chat(messages):
            yield tok

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.post("/chat")
async def chat(
    payload: ChatRequest, db: AsyncSession = Depends(db_session)
) -> StreamingResponse:
    provider = await _get_provider_or_404(db, payload.provider_id)
    turns = [ChatTurn(m.role, m.content) for m in payload.messages]

    async def gen():
        async for tok in provider.stream_chat(turns):
            yield tok

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
