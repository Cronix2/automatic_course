"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api import (
    routes_ai,
    routes_oauth,
    routes_settings,
    routes_thm,
    routes_voice,
)
from app.config import get_settings
from app.db.session import init_db


limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "microphone=(self), camera=(), geolocation=()"
        )
        if get_settings().is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Fail-fast on critical config
    _ = settings.master_key_bytes  # raises if missing/invalid
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET is not configured.")
    await init_db()
    logger.info("Backend ready.")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Automatic Course API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):  # noqa: ARG001
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(routes_settings.router)
    app.include_router(routes_thm.router)
    app.include_router(routes_ai.router)
    app.include_router(routes_voice.router)
    app.include_router(routes_oauth.router)

    return app


app = create_app()
