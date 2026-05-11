"""STT / TTS HTTP routes."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.services import stt as stt_service
from app.services import tts as tts_service

router = APIRouter(prefix="/api/voice", tags=["voice"])


class _TTSBody(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
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


@router.post("/tts")
async def synthesize_post(body: _TTSBody) -> Response:
    """Synthesize TTS from a JSON body (preferred for long texts)."""
    wav = await tts_service.synthesize_to_wav(body.text, voice_name=body.voice)
    return Response(content=wav, media_type="audio/wav")


@router.get("/tts")
async def synthesize(text: str, voice: str | None = None) -> Response:
    if not text.strip():
        raise HTTPException(400, "Empty text.")
    wav = await tts_service.synthesize_to_wav(text, voice_name=voice)
    return Response(content=wav, media_type="audio/wav")


@router.get("/tts/stream")
async def synthesize_stream(text: str, voice: str | None = None) -> StreamingResponse:
    if not text.strip():
        raise HTTPException(400, "Empty text.")

    async def gen():
        async for chunk in tts_service.stream_pcm(text, voice_name=voice):
            yield chunk

    return StreamingResponse(gen(), media_type="application/octet-stream")
