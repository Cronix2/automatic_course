"""AI orchestration: enhance a course, chat with interruption."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import ProviderConfig
from app.schemas.course import ChatRequest, EnhanceRequest
from app.services.providers import ChatTurn, build_provider

router = APIRouter(prefix="/api/ai", tags=["ai"])


# Soft throttle between section calls to stay below provider rate limits
# (GitHub Copilot is currently 10 req/min/model → ~6 s spacing is safe).
SECTION_DELAY_SECONDS = 6.5
# Max times we retry a section that hit a 429.
SECTION_MAX_RETRIES = 3


def _parse_retry_after(error_text: str) -> float | None:
    """Extract a wait hint from a 429 message, in seconds.

    Looks for patterns like ``"Please wait 12 seconds"`` or
    ``"Rate limit of 10 per 60s"``. Returns None if nothing usable found.
    """
    m = re.search(r"wait\s+(\d+(?:\.\d+)?)\s*seconds?", error_text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r"per\s+(\d+)\s*s\b", error_text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


ENHANCE_SYSTEM = (
    "Tu es un instructeur de cybersécurité expert. "
    "TA SEULE SOURCE D'INFORMATION est le cours fourni par l'utilisateur ci-dessous. "
    "Tu n'as PAS le droit d'ajouter des faits, exemples, commandes ou détails "
    "qui ne sont pas explicitement présents dans ce cours. "
    "Si une notion est mentionnée mais pas expliquée, tu peux la clarifier "
    "uniquement avec une définition générique très courte, en indiquant "
    "(« non détaillé dans le cours »). "
    "Réécris la SECTION fournie de manière concise en français. "
    "Conserve le titre de niveau ## tel quel. "
    "Adapte le ton à une lecture vocale : phrases courtes, pas de bloc de code "
    "long, pas d'URL longue. Format Markdown léger (titres et listes autorisés). "
    "Ne dis JAMAIS « voici la réécriture », commence directement par le titre."
)


def _split_into_sections(markdown: str) -> list[tuple[str, str]]:
    """Split a markdown course into ``[(title_line, body)]`` chunks.

    Each chunk starts at a ``## ...`` header and contains everything until
    the next ``## ...`` header. If the markdown has no ``## `` header, the
    whole text is returned as a single chunk.
    """
    if not markdown.strip():
        return []
    # Find every ## header position
    pattern = re.compile(r"(?m)^##\s+.+$")
    matches = list(pattern.finditer(markdown))
    if not matches:
        return [("", markdown.strip())]
    chunks: list[tuple[str, str]] = []
    # Preamble before first ## (if any meaningful content)
    if matches[0].start() > 0:
        pre = markdown[: matches[0].start()].strip()
        if pre:
            chunks.append(("", pre))
    for i, m in enumerate(matches):
        title = m.group(0).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        chunks.append((title, body))
    return chunks


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

    sections = _split_into_sections(payload.content.markdown)
    if not sections:
        sections = [("", payload.content.markdown)]

    async def gen():
        for idx, (title_line, body) in enumerate(sections, start=1):
            label = title_line or f"Partie {idx}"
            # Pace the calls to stay below provider rate limits.
            if idx > 1:
                yield "\n\n"
                await asyncio.sleep(SECTION_DELAY_SECONDS)

            user_msg = (
                f"Cours « {payload.content.title} » "
                f"(room TryHackMe « {payload.content.room_code} »).\n"
                f"Style demandé : « {payload.style} ».\n"
                f"Section {idx} / {len(sections)}.\n\n"
                f"=== DÉBUT DE LA SECTION SOURCE (ne pas extrapoler au-delà) ===\n"
                f"{title_line}\n{body}\n"
                f"=== FIN DE LA SECTION SOURCE ===\n\n"
                f"Réécris uniquement cette section en respectant les consignes système."
            )
            messages = [
                ChatTurn("system", ENHANCE_SYSTEM),
                ChatTurn("user", user_msg),
            ]

            # Per-section retry loop on rate-limit errors.
            attempt = 0
            while True:
                attempt += 1
                section_failed = False
                buffered_tokens: list[str] = []
                try:
                    async for tok in provider.stream_chat(messages):
                        buffered_tokens.append(tok)
                        yield tok
                    break  # success
                except Exception as exc:
                    err_text = str(exc)
                    is_429 = "429" in err_text or "RateLimitReached" in err_text or "rate limit" in err_text.lower()
                    if is_429 and attempt <= SECTION_MAX_RETRIES:
                        # If we already streamed partial output, push a marker
                        # so the user knows we are retrying after a wait.
                        wait_s = _parse_retry_after(err_text) or 30.0
                        wait_s = max(5.0, min(wait_s, 90.0))
                        if buffered_tokens:
                            yield (
                                f"\n\n⏳ Limite de requêtes atteinte sur « {label} ». "
                                f"Reprise dans ~{int(wait_s)} s (tentative {attempt + 1}/{SECTION_MAX_RETRIES + 1})...\n"
                            )
                        else:
                            yield (
                                f"⏳ Limite de requêtes atteinte sur « {label} ». "
                                f"Reprise dans ~{int(wait_s)} s (tentative {attempt + 1}/{SECTION_MAX_RETRIES + 1})...\n"
                            )
                        await asyncio.sleep(wait_s)
                        continue
                    section_failed = True
                    yield (
                        f"\n\n⚠️ Erreur sur la section « {label} » : {exc}\n"
                        f"(Les sections suivantes vont quand même être traitées.)\n"
                    )
                    break
                finally:
                    if section_failed:
                        # ensure we leave the inner while
                        pass

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.post("/chat")
async def chat(
    payload: ChatRequest, db: AsyncSession = Depends(db_session)
) -> StreamingResponse:
    provider = await _get_provider_or_404(db, payload.provider_id)
    turns = [ChatTurn(m.role, m.content) for m in payload.messages]

    async def gen():
        try:
            async for tok in provider.stream_chat(turns):
                yield tok
        except Exception as exc:
            yield f"\n\n⚠️ Erreur du provider : {exc}\n"

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
