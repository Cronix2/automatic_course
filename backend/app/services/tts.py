"""Local TTS via Piper.

Piper produces 16-bit PCM mono. We expose:
- `synthesize_to_wav(text)` -> bytes (a complete WAV file)
- `stream_pcm(text)` -> async iterator of raw 16-bit PCM chunks for low-latency
   playback / interruption.
"""
from __future__ import annotations

import asyncio
import io
import wave
from functools import lru_cache
from pathlib import Path
from typing import AsyncIterator

from loguru import logger

from app.config import get_settings


@lru_cache(maxsize=4)
def _get_voice(voice_name: str):  # pragma: no cover - heavy import
    from piper import PiperVoice

    s = get_settings()
    models_dir = Path(s.piper_models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    onnx = models_dir / f"{voice_name}.onnx"
    cfg = models_dir / f"{voice_name}.onnx.json"
    if not onnx.exists() or not cfg.exists():
        raise FileNotFoundError(
            f"Piper voice not found at {onnx}. "
            f"Download it from https://github.com/rhasspy/piper/releases "
            f"and place both .onnx and .onnx.json into {models_dir}."
        )
    logger.info(f"Loading Piper voice from {onnx}")
    return PiperVoice.load(str(onnx), config_path=str(cfg))


def _synth_sync(text: str, voice_name: str) -> tuple[bytes, int, int]:
    voice = _get_voice(voice_name)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize(text, wf)
    data = buf.getvalue()
    # Extract sample rate from header
    with wave.open(io.BytesIO(data), "rb") as wf:
        sr = wf.getframerate()
        channels = wf.getnchannels()
    return data, sr, channels


async def synthesize_to_wav(text: str, voice_name: str | None = None) -> bytes:
    voice = voice_name or get_settings().piper_voice
    data, _sr, _ch = await asyncio.to_thread(_synth_sync, text, voice)
    return data


async def stream_pcm(text: str, voice_name: str | None = None) -> AsyncIterator[bytes]:
    """Yield raw 16-bit PCM chunks. For now we synthesize the full WAV then
    yield the payload in slices; replace with sentence-level streaming for
    sub-100ms latency once we tokenize the text into sentences."""
    wav_bytes = await synthesize_to_wav(text, voice_name)
    # Strip the 44-byte WAV header for raw PCM
    header_len = 44
    chunk = 4096
    for i in range(header_len, len(wav_bytes), chunk):
        yield wav_bytes[i : i + chunk]
