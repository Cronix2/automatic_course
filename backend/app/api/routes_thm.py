"""TryHackMe routes: login (with optional 2FA), course fetch, suggestions."""
from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.config import get_settings
from app.db.session import SessionLocal
from app.schemas.course import CourseContent
from app.services.secrets_service import get_secret, set_secret
from app.services.thm_client import (
    THMCaptchaBlocked,
    THMClient,
    THMSession,
    THMTwoFactorRequired,
    get_last_snapshot,
    normalize_room_ref,
)

# ---- In-memory store for browser-login jobs --------------------------------
# Keys: job_id (str)  Values: {"status": "pending"|"done"|"error", "error": str|None}
_browser_jobs: Dict[str, dict] = {}

router = APIRouter(prefix="/api/thm", tags=["tryhackme"])


# ---------- 2FA-aware login -------------------------------------------------
class _LoginIn(BaseModel):
    force: bool = False


class _TwoFAIn(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=4, max_length=12)


class _LoginOut(BaseModel):
    ok: bool
    requires_2fa: bool = False
    challenge_id: Optional[str] = None


class _SessionCookieIn(BaseModel):
    """Manual cookie import payload.

    Accept either:
      * ``cookies``: a JSON list of Playwright-style cookie dicts
        (``{name, value, domain, path, ...}``).
      * ``cookie_header``: the raw ``Cookie:`` header value copied from the
        browser (``name1=value1; name2=value2; ...``). We split it and assume
        ``.tryhackme.com`` as the domain.
      * ``connect_sid``: just the value of the ``connect.sid`` session cookie.
    """

    cookies: Optional[List[dict]] = None
    cookie_header: Optional[str] = None
    connect_sid: Optional[str] = None


def _build_cookies_from_payload(payload: _SessionCookieIn) -> List[dict]:
    if payload.cookies:
        # Trust the caller's structure but ensure required fields exist.
        out: List[dict] = []
        for c in payload.cookies:
            if not isinstance(c, dict) or "name" not in c or "value" not in c:
                continue
            cc = dict(c)
            cc.setdefault("domain", ".tryhackme.com")
            cc.setdefault("path", "/")
            out.append(cc)
        if not out:
            raise HTTPException(400, "No usable cookies in payload.")
        return out
    if payload.cookie_header:
        out = []
        for chunk in payload.cookie_header.split(";"):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            name, _, value = chunk.partition("=")
            out.append(
                {
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".tryhackme.com",
                    "path": "/",
                }
            )
        if not out:
            raise HTTPException(400, "Cookie header is empty or malformed.")
        return out
    if payload.connect_sid:
        return [
            {
                "name": "connect.sid",
                "value": payload.connect_sid.strip(),
                "domain": ".tryhackme.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }
        ]
    raise HTTPException(
        400,
        "Provide one of: cookies, cookie_header, connect_sid.",
    )


async def _do_login(db: AsyncSession) -> _LoginOut:
    email = await get_secret(db, "thm.email")
    password = await get_secret(db, "thm.password")
    if not email or not password:
        raise HTTPException(400, "TryHackMe credentials are not configured.")
    # NOTE: THMClient.login() spins up its OWN Playwright instance because
    # the browser must outlive the request when 2FA is required. We do NOT
    # need an outer `async with THMClient()` here (it would create another
    # short-lived browser for nothing and slow the request down).
    thm = THMClient()
    try:
        sess = await thm.login(email, password)
    except THMTwoFactorRequired as e:
        return _LoginOut(ok=False, requires_2fa=True, challenge_id=e.challenge_id)
    except THMCaptchaBlocked as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "thm_captcha_blocked",
                "message": str(e),
                "hint": (
                    "TryHackMe affiche un CAPTCHA. Soit relance le backend "
                    "avec THM_HEADFUL=1 pour le résoudre manuellement, soit "
                    "importe ton cookie de session via /api/thm/session-cookies."
                ),
            },
        )
    await set_secret(db, "thm.session_cookie", sess.to_json())
    return _LoginOut(ok=True)


async def _ensure_session(db: AsyncSession) -> THMSession:
    """Return a valid session or raise 401 with 2FA payload if needed."""
    cookie_json = await get_secret(db, "thm.session_cookie")
    if cookie_json:
        sess = THMSession.from_json(cookie_json)
        async with THMClient() as thm:
            if await thm.is_session_valid(sess):
                return sess
        # Cookie exists but is invalid/expired.  Only fall back to
        # email+password login if the credentials are actually configured;
        # otherwise tell the user to re-import their cookie.
        has_creds = await get_secret(db, "thm.email") and await get_secret(
            db, "thm.password"
        )
        if not has_creds:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "thm_session_expired",
                    "message": (
                        "Votre session TryHackMe a expiré. "
                        "Reconnectez-vous sur tryhackme.com et ré-importez "
                        "votre cookie de session dans Réglages → TryHackMe."
                    ),
                },
            )
    result = await _do_login(db)
    if result.requires_2fa:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "thm_2fa_required",
                "challenge_id": result.challenge_id,
                "message": "TryHackMe demande un code de double authentification.",
            },
        )
    cookie_json = await get_secret(db, "thm.session_cookie")
    return THMSession.from_json(cookie_json or "[]")


@router.post("/login", response_model=_LoginOut)
async def login(
    _payload: Optional[_LoginIn] = None,
    db: AsyncSession = Depends(db_session),
) -> _LoginOut:
    return await _do_login(db)


@router.post("/login/2fa", response_model=_LoginOut)
async def submit_two_factor(
    payload: _TwoFAIn, db: AsyncSession = Depends(db_session)
) -> _LoginOut:
    thm = THMClient()
    try:
        sess = await thm.submit_2fa(payload.challenge_id, payload.code)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    await set_secret(db, "thm.session_cookie", sess.to_json())
    return _LoginOut(ok=True)


# ---------- Manual session import (CAPTCHA bypass) -------------------------
@router.post("/session-cookies", response_model=_LoginOut)
async def import_session_cookies(
    payload: _SessionCookieIn, db: AsyncSession = Depends(db_session)
) -> _LoginOut:
    """Persist a manually-supplied set of TryHackMe cookies.

    When TryHackMe gates the login behind a CAPTCHA, the recommended workflow
    is:
      1. Log in on tryhackme.com from your normal browser.
      2. Open DevTools → Application → Cookies → ``https://tryhackme.com``.
      3. Copy the ``connect.sid`` cookie value (or all cookies).
      4. POST it here.

    We validate the cookies by hitting the THM dashboard; if the session is
    not actually logged in we reject the payload.
    """
    cookies = _build_cookies_from_payload(payload)
    session = THMSession(cookies=cookies)
    async with THMClient() as thm:
        if not await thm.is_session_valid(session):
            raise HTTPException(
                400,
                "These cookies do not correspond to a logged-in TryHackMe "
                "session. Re-export them from your browser after logging in.",
            )
    await set_secret(db, "thm.session_cookie", session.to_json())
    return _LoginOut(ok=True)


@router.delete("/session-cookies", status_code=204, response_class=Response)
async def clear_session_cookies(db: AsyncSession = Depends(db_session)) -> Response:
    from app.services.secrets_service import delete_secret

    await delete_secret(db, "thm.session_cookie")
    return Response(status_code=204)


# ---------- Browser-login (headful manual flow) -----------------------------

async def _run_browser_login_task(job_id: str) -> None:
    """Background task: open headful Playwright, wait for user to log in."""
    try:
        thm = THMClient()
        session = await thm.await_manual_login(timeout_s=300)
        async with SessionLocal() as db:
            await set_secret(db, "thm.session_cookie", session.to_json())
            await db.commit()
        _browser_jobs[job_id] = {"status": "done", "error": None}
    except Exception as exc:
        _browser_jobs[job_id] = {"status": "error", "error": str(exc)}


@router.post("/browser-login/start")
async def start_browser_login(
    background_tasks: BackgroundTasks,
) -> dict:
    """Start a headful browser login.  Returns a job_id to poll."""
    # Only one concurrent job allowed
    for job in _browser_jobs.values():
        if job["status"] == "pending":
            raise HTTPException(
                409, "Un navigateur est déjà ouvert. Connectez-vous dans la fenêtre."
            )
    job_id = secrets.token_urlsafe(16)
    _browser_jobs[job_id] = {"status": "pending", "error": None}
    background_tasks.add_task(_run_browser_login_task, job_id)
    return {"job_id": job_id}


@router.get("/browser-login/status/{job_id}")
async def browser_login_status(job_id: str) -> dict:
    job = _browser_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job inconnu.")
    return job


@router.delete("/browser-login/{job_id}", status_code=204, response_class=Response)
async def cancel_browser_login(job_id: str) -> Response:
    _browser_jobs.pop(job_id, None)
    return Response(status_code=204)


# ---------- Suggested rooms -------------------------------------------------
class SuggestedRoom(BaseModel):
    room_code: str
    title: str
    description: str
    difficulty: str  # info | easy | medium | hard
    tags: List[str] = Field(default_factory=list)


_SUGGESTED: List[SuggestedRoom] = [
    SuggestedRoom(
        room_code="introtocyber",
        title="Intro to Cyber Security",
        description="Vue d'ensemble des carrières et concepts en cybersécurité.",
        difficulty="info",
        tags=["intro"],
    ),
    SuggestedRoom(
        room_code="introtonetworking",
        title="Intro to Networking",
        description="Bases TCP/IP, ports, modèle OSI.",
        difficulty="easy",
        tags=["network", "fondamentaux"],
    ),
    SuggestedRoom(
        room_code="linuxfundamentalspart1",
        title="Linux Fundamentals 1",
        description="Premiers pas sur le terminal Linux.",
        difficulty="easy",
        tags=["linux"],
    ),
    SuggestedRoom(
        room_code="nmap",
        title="Nmap",
        description="Découverte hôte/service et fingerprinting.",
        difficulty="easy",
        tags=["recon"],
    ),
    SuggestedRoom(
        room_code="owasptop10",
        title="OWASP Top 10",
        description="Les 10 vulnérabilités web les plus courantes.",
        difficulty="easy",
        tags=["web"],
    ),
    SuggestedRoom(
        room_code="burpsuitebasics",
        title="Burp Suite: The Basics",
        description="Interception et manipulation de requêtes HTTP.",
        difficulty="easy",
        tags=["web", "outils"],
    ),
    SuggestedRoom(
        room_code="metasploitintro",
        title="Metasploit: Introduction",
        description="Framework d'exploitation.",
        difficulty="medium",
        tags=["pentest"],
    ),
    SuggestedRoom(
        room_code="windowsfundamentals1xbx",
        title="Windows Fundamentals 1",
        description="Bases Windows pour la sécurité défensive.",
        difficulty="easy",
        tags=["windows"],
    ),
    SuggestedRoom(
        room_code="introtocrypto",
        title="Cryptography for Dummies",
        description="Bases de la cryptographie moderne.",
        difficulty="easy",
        tags=["crypto"],
    ),
    SuggestedRoom(
        room_code="phishing",
        title="Phishing",
        description="Analyse d'emails de phishing.",
        difficulty="easy",
        tags=["blueteam"],
    ),
]


@router.get("/suggested", response_model=List[SuggestedRoom])
async def list_suggested() -> List[SuggestedRoom]:
    return _SUGGESTED


# ---------- Learning paths --------------------------------------------------
class _PathSummary(BaseModel):
    slug: str
    title: str
    description: str = ""
    difficulty: str = "info"
    rooms_count: int = 0


class _PathRoom(BaseModel):
    room_code: str
    title: str
    module: str = ""


class _PathDetail(BaseModel):
    slug: str
    title: str
    description: str = ""
    rooms: List[_PathRoom] = []


# Curated catalogue. Slugs are the ones used by TryHackMe in
# https://tryhackme.com/path/outline/<slug>
_PATHS: List[_PathSummary] = [
    _PathSummary(
        slug="presecurity",
        title="Pre Security",
        description="Bases réseau, web, Linux & Windows avant d'attaquer la cyber.",
        difficulty="easy",
        rooms_count=29,
    ),
    _PathSummary(
        slug="introtocyber",
        title="Introduction à la Cyber Sécurité",
        description="Vue d'ensemble red / blue / digital forensics.",
        difficulty="easy",
        rooms_count=8,
    ),
    _PathSummary(
        slug="beginner",
        title="Complete Beginner",
        description="Démarrer en sécurité offensive depuis zéro.",
        difficulty="easy",
        rooms_count=40,
    ),
    _PathSummary(
        slug="jrpentester",
        title="Jr Penetration Tester",
        description="Préparation au métier de pentester junior.",
        difficulty="medium",
        rooms_count=33,
    ),
    _PathSummary(
        slug="webfundamentals",
        title="Web Fundamentals",
        description="OWASP, attaques web, Burp Suite.",
        difficulty="medium",
        rooms_count=12,
    ),
    _PathSummary(
        slug="cyberdefense",
        title="Cyber Defense",
        description="SOC, blue team, threat intelligence.",
        difficulty="medium",
        rooms_count=26,
    ),
    _PathSummary(
        slug="soclevel1",
        title="SOC Level 1",
        description="Analyse d'incidents, SIEM, EDR.",
        difficulty="medium",
        rooms_count=30,
    ),
]


@router.get("/paths", response_model=List[_PathSummary])
async def list_paths() -> List[_PathSummary]:
    """Curated list of TryHackMe learning paths shown on the home/paths page."""
    return _PATHS


@router.get("/paths/{slug}", response_model=_PathDetail)
async def get_path(
    slug: str, db: AsyncSession = Depends(db_session)
) -> _PathDetail:
    """Live-scrape a TryHackMe learning path and return its room list.

    Uses the configured TryHackMe session, so private/in-progress data is
    visible only if the underlying account has access.
    """
    sess = await _ensure_session(db)
    async with THMClient() as thm:
        data = await thm.fetch_path(sess, slug)
    return _PathDetail(
        slug=data["slug"],
        title=data["title"],
        description=data.get("description", ""),
        rooms=[_PathRoom(**r) for r in data.get("rooms", [])],
    )


# ---------- Fetch -----------------------------------------------------------
class _FetchIn(BaseModel):
    """Accept either a room code or a full TryHackMe URL."""

    room_code: Optional[str] = None
    url: Optional[str] = None


@router.post("/fetch", response_model=CourseContent)
async def fetch_course(
    ref: _FetchIn, db: AsyncSession = Depends(db_session)
) -> CourseContent:
    raw = ref.url or ref.room_code or ""
    try:
        code = normalize_room_ref(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    sess = await _ensure_session(db)
    async with THMClient() as thm:
        return await thm.fetch_room(sess, code)


@router.get("/normalize")
async def normalize(ref: str) -> dict:
    try:
        return {"room_code": normalize_room_ref(ref)}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- Debug -----------------------------------------------------------
@router.get("/debug/last-login")
async def debug_last_login() -> dict:
    """Return diagnostic info on the last login attempt.

    Includes the URL Playwright landed on after submit, how many OTP-shaped
    inputs were on the page, and the paths to the saved screenshot / HTML.
    Useful when 2FA detection misbehaves.
    """
    snap = get_last_snapshot()
    settings = get_settings()
    snap["headful"] = settings.thm_headful
    snap["slow_mo_ms"] = settings.thm_slow_mo_ms
    snap["debug_dir"] = str(Path(settings.thm_debug_dir).resolve())
    return snap


@router.get("/debug/screenshot")
async def debug_screenshot() -> FileResponse:
    snap = get_last_snapshot()
    path = snap.get("screenshot")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "No screenshot available — try logging in first.")
    return FileResponse(path, media_type="image/png", filename=os.path.basename(path))


@router.get("/debug/html")
async def debug_html() -> FileResponse:
    snap = get_last_snapshot()
    path = snap.get("html")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "No HTML dump available — try logging in first.")
    return FileResponse(path, media_type="text/html", filename=os.path.basename(path))
