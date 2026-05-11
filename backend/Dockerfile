# Pin to bookworm (Debian 12 stable) — trixie's libnss3 is a linker script,
# not a real ELF shared library, which breaks Playwright Chromium at runtime.
FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-Playwright system deps (ffmpeg, audio, build tools, xvfb for headful browser-login).
# Playwright Chromium dependencies are handled by --with-deps below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libsndfile1 \
    curl \
    ca-certificates \
    wget \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Install Playwright Chromium + all its system dependencies (libnss3, libatk, etc.).
# --with-deps is reliable on Debian bookworm unlike trixie.
RUN python -m playwright install --with-deps chromium

COPY app ./app

RUN mkdir -p /app/data /app/models/piper

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers"]
