"""Local STT via faster-whisper.

The model is loaded lazily (first request) and cached process-wide.
We expose a single `transcribe(audio_bytes)` async API.
"""
from __future__ import annotations

import asyncio
import io
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

from loguru import logger

from app.config import get_settings


@lru_cache(maxsize=1)
def _get_model():  # pragma: no cover - heavy import
    from faster_whisper import WhisperModel

    s = get_settings()
    device = s.whisper_device
    compute_type = s.whisper_compute_type
    if device == "auto":
        device = "cpu"
    if compute_type == "auto":
        compute_type = "int8" if device == "cpu" else "float16"
    logger.info(
        f"Loading faster-whisper model={s.whisper_model} device={device} compute={compute_type}"
    )
    return WhisperModel(s.whisper_model, device=device, compute_type=compute_type)


def _transcribe_sync(audio_path: str, language: Optional[str]) -> str:
    model = _get_model()
    segments, _info = model.transcribe(
        audio_path,
        language=language,
        vad_filter=True,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


async def transcribe(audio_bytes: bytes, language: Optional[str] = "fr") -> str:
    """Transcribe raw audio bytes (any format supported by ffmpeg)."""
    # faster-whisper wants a file path or a numpy array. We write a temp file
    # to keep things robust across codecs.
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        return await asyncio.to_thread(_transcribe_sync, tmp_path, language)
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
