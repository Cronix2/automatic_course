"""STT / TTS HTTP routes."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.config import get_settings
from app.db.models import Setting
from app.services import stt as stt_service
from app.services import tts as tts_service

router = APIRouter(prefix="/api/voice", tags=["voice"])


class _TTSBody(BaseModel):
    # Local Piper handles arbitrarily long texts; we keep a generous cap
    # to avoid pathological payloads but allow full-course inputs.
    text: str = Field(min_length=1, max_length=500_000)
    voice: str | None = None


@router.post("/stt")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str = Form("fr"),
) -> dict:
    if audio.content_type and not audio.content_type.startswith(("audio/", "video/")):
        raise HTTPException(400, f"Unexpected content type: {audio.content_type}")
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio payload.")
    text = await stt_service.transcribe(data, language=language)
    return {"text": text}


async def _resolve_voice(db: AsyncSession, override: Optional[str]) -> str:
    """Pick the active voice: explicit override > DB setting > config default."""
    if override:
        return override
    row = await db.scalar(select(Setting).where(Setting.key == "tts.voice"))
    if row and row.value:
        return row.value
    return get_settings().piper_voice


@router.post("/tts")
async def synthesize_post(
    body: _TTSBody, db: AsyncSession = Depends(db_session)
) -> Response:
    """Synthesize TTS from a JSON body (preferred for long texts)."""
    voice = await _resolve_voice(db, body.voice)
    wav = await tts_service.synthesize_to_wav(body.text, voice_name=voice)
    return Response(content=wav, media_type="audio/wav")


@router.get("/tts")
async def synthesize(
    text: str,
    voice: str | None = None,
    db: AsyncSession = Depends(db_session),
) -> Response:
    if not text.strip():
        raise HTTPException(400, "Empty text.")
    v = await _resolve_voice(db, voice)
    wav = await tts_service.synthesize_to_wav(text, voice_name=v)
    return Response(content=wav, media_type="audio/wav")


@router.get("/tts/stream")
async def synthesize_stream(
    text: str,
    voice: str | None = None,
    db: AsyncSession = Depends(db_session),
) -> StreamingResponse:
    if not text.strip():
        raise HTTPException(400, "Empty text.")
    v = await _resolve_voice(db, voice)

    async def gen():
        async for chunk in tts_service.stream_pcm(text, voice_name=v):
            yield chunk

    return StreamingResponse(gen(), media_type="application/octet-stream")


# ---- Voice management ------------------------------------------------------

class VoiceInfo(BaseModel):
    id: str           # e.g. "fr_FR-tom-medium"
    label: str        # human-friendly
    gender: str       # "male" | "female" | "unknown"
    quality: str      # "low" | "medium" | "high" | "x_low"
    installed: bool
    is_default: bool = False
    download_url: Optional[str] = None
    config_url: Optional[str] = None


# Curated catalog of French Piper voices from rhasspy/piper-voices on HuggingFace.
# Each tuple: (voice_id, gender, quality, speaker_folder, label).
_CURATED_FR_VOICES = [
    # Female
    ("fr_FR-siwis-medium", "female", "medium", "siwis", "Siwis (femme, fluide)"),
    ("fr_FR-siwis-low", "female", "low", "siwis", "Siwis (femme, rapide)"),
    ("fr_FR-upmc-medium", "female", "medium", "upmc", "UPMC Jessica (femme)"),
    # Male
    ("fr_FR-tom-medium", "male", "medium", "tom", "Tom (homme, naturel)"),
    ("fr_FR-gilles-low", "male", "low", "gilles", "Gilles (homme, rapide)"),
    ("fr_FR-mls_1840-low", "male", "low", "mls_1840", "MLS 1840 (homme)"),
]

_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR"


def _voice_paths(voice_id: str) -> tuple[Path, Path]:
    s = get_settings()
    models_dir = Path(s.piper_models_dir)
    return models_dir / f"{voice_id}.onnx", models_dir / f"{voice_id}.onnx.json"


def _voice_download_urls(voice_id: str, speaker: str, quality: str) -> tuple[str, str]:
    base = f"{_HF_BASE}/{speaker}/{quality}/{voice_id}"
    return f"{base}.onnx", f"{base}.onnx.json"


@router.get("/voices", response_model=List[VoiceInfo])
async def list_voices(db: AsyncSession = Depends(db_session)) -> List[VoiceInfo]:
    current = await _resolve_voice(db, None)
    out: List[VoiceInfo] = []
    seen: set[str] = set()
    # Curated entries (with download links)
    for voice_id, gender, quality, speaker, label in _CURATED_FR_VOICES:
        onnx_path, cfg_path = _voice_paths(voice_id)
        installed = onnx_path.exists() and cfg_path.exists()
        onnx_url, cfg_url = _voice_download_urls(voice_id, speaker, quality)
        out.append(
            VoiceInfo(
                id=voice_id,
                label=label,
                gender=gender,
                quality=quality,
                installed=installed,
                is_default=(voice_id == current),
                download_url=onnx_url,
                config_url=cfg_url,
            )
        )
        seen.add(voice_id)
    # Any other already-installed voice we don't know about
    s = get_settings()
    models_dir = Path(s.piper_models_dir)
    if models_dir.exists():
        for onnx in sorted(models_dir.glob("*.onnx")):
            voice_id = onnx.stem
            if voice_id in seen:
                continue
            cfg_path = onnx.with_suffix(".onnx.json")
            if not cfg_path.exists():
                continue
            out.append(
                VoiceInfo(
                    id=voice_id,
                    label=voice_id,
                    gender="unknown",
                    quality="unknown",
                    installed=True,
                    is_default=(voice_id == current),
                )
            )
    return out


class _SetVoiceIn(BaseModel):
    voice: str = Field(min_length=1, max_length=120)


@router.put("/voices/default")
async def set_default_voice(
    payload: _SetVoiceIn, db: AsyncSession = Depends(db_session)
) -> dict:
    onnx_path, cfg_path = _voice_paths(payload.voice)
    if not onnx_path.exists() or not cfg_path.exists():
        raise HTTPException(
            400,
            f"Voice '{payload.voice}' is not installed locally. Install it first.",
        )
    row = await db.scalar(select(Setting).where(Setting.key == "tts.voice"))
    if row is None:
        row = Setting(key="tts.voice", value=payload.voice)
        db.add(row)
    else:
        row.value = payload.voice
    await db.commit()
    logger.info("voice: default set to %s", payload.voice)
    return {"ok": True, "voice": payload.voice}


@router.post("/voices/install")
async def install_voice(payload: _SetVoiceIn) -> dict:
    """Download a curated voice from HuggingFace into the local models dir."""
    target = next(
        (v for v in _CURATED_FR_VOICES if v[0] == payload.voice), None
    )
    if target is None:
        raise HTTPException(404, f"Unknown voice id '{payload.voice}'.")
    voice_id, _gender, quality, speaker, _label = target
    onnx_path, cfg_path = _voice_paths(voice_id)
    onnx_url, cfg_url = _voice_download_urls(voice_id, speaker, quality)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(60.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for url, dst in ((cfg_url, cfg_path), (onnx_url, onnx_path)):
            if dst.exists():
                continue
            logger.info("voice: downloading %s -> %s", url, dst)
            r = await client.get(url)
            if r.status_code != 200:
                raise HTTPException(
                    502,
                    f"Download failed for {url} ({r.status_code}): {r.text[:200]}",
                )
            dst.write_bytes(r.content)
    return {"ok": True, "voice": voice_id, "path": str(onnx_path)}
