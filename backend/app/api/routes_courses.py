"""Cached courses: read/write the local DB cache of fetched TryHackMe rooms
and their AI-enhanced versions.

This lets the UI display content instantly on revisit while still offering an
explicit "refresh from TryHackMe" / "re-enhance with AI" action.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.db.models import CachedCourse, ProviderConfig

router = APIRouter(prefix="/api/courses", tags=["courses"])


class CachedCourseOut(BaseModel):
    room_code: str
    title: str
    markdown: str
    sections: List[str] = []
    fetched_at: Optional[datetime] = None
    enhanced_markdown: Optional[str] = None
    enhanced_provider_kind: Optional[str] = None
    enhanced_provider_model: Optional[str] = None
    enhanced_style: Optional[str] = None
    enhanced_at: Optional[datetime] = None


class CachedCourseListItem(BaseModel):
    room_code: str
    title: str
    fetched_at: Optional[datetime] = None
    enhanced_at: Optional[datetime] = None
    markdown_length: int = 0


class _SaveCourseIn(BaseModel):
    """Persist the freshly-scraped raw course in cache."""
    room_code: str
    title: str
    markdown: str
    sections: List[str] = []


class _SaveEnhancedIn(BaseModel):
    """Persist the AI-enhanced version of a cached course."""
    room_code: str
    enhanced_markdown: str
    provider_id: Optional[int] = None
    style: Optional[str] = None


def _row_to_out(row: CachedCourse) -> CachedCourseOut:
    try:
        sections = json.loads(row.sections_json or "[]")
        if not isinstance(sections, list):
            sections = []
    except Exception:
        sections = []
    return CachedCourseOut(
        room_code=row.room_code,
        title=row.title or row.room_code,
        markdown=row.markdown or "",
        sections=sections,
        fetched_at=row.fetched_at,
        enhanced_markdown=row.enhanced_markdown,
        enhanced_provider_kind=row.enhanced_provider_kind,
        enhanced_provider_model=row.enhanced_provider_model,
        enhanced_style=row.enhanced_style,
        enhanced_at=row.enhanced_at,
    )


@router.get("", response_model=List[CachedCourseListItem])
async def list_cached_courses(
    db: AsyncSession = Depends(db_session),
) -> List[CachedCourseListItem]:
    rows = (
        await db.scalars(select(CachedCourse).order_by(CachedCourse.updated_at.desc()))
    ).all()
    return [
        CachedCourseListItem(
            room_code=r.room_code,
            title=r.title or r.room_code,
            fetched_at=r.fetched_at,
            enhanced_at=r.enhanced_at,
            markdown_length=len(r.markdown or ""),
        )
        for r in rows
    ]


@router.get("/{room_code}", response_model=CachedCourseOut)
async def get_cached_course(
    room_code: str, db: AsyncSession = Depends(db_session)
) -> CachedCourseOut:
    row = await db.get(CachedCourse, room_code)
    if row is None:
        raise HTTPException(404, "No cached version for this course.")
    return _row_to_out(row)


@router.put("/{room_code}", response_model=CachedCourseOut)
async def save_cached_course(
    room_code: str,
    payload: _SaveCourseIn,
    db: AsyncSession = Depends(db_session),
) -> CachedCourseOut:
    if payload.room_code != room_code:
        raise HTTPException(400, "room_code mismatch between URL and body.")
    row = await db.get(CachedCourse, room_code)
    now = datetime.utcnow()
    if row is None:
        row = CachedCourse(room_code=room_code)
        db.add(row)
    row.title = payload.title or room_code
    row.markdown = payload.markdown or ""
    row.sections_json = json.dumps(payload.sections or [], ensure_ascii=False)
    row.fetched_at = now
    await db.commit()
    await db.refresh(row)
    logger.info("courses: cached raw course %s (%d chars)", room_code, len(row.markdown))
    return _row_to_out(row)


@router.put("/{room_code}/enhanced", response_model=CachedCourseOut)
async def save_enhanced_course(
    room_code: str,
    payload: _SaveEnhancedIn,
    db: AsyncSession = Depends(db_session),
) -> CachedCourseOut:
    if payload.room_code != room_code:
        raise HTTPException(400, "room_code mismatch between URL and body.")
    row = await db.get(CachedCourse, room_code)
    if row is None:
        raise HTTPException(404, "Fetch the raw course first before saving an enhanced version.")
    row.enhanced_markdown = payload.enhanced_markdown or ""
    row.enhanced_style = payload.style
    row.enhanced_at = datetime.utcnow()
    if payload.provider_id is not None:
        provider = await db.get(ProviderConfig, payload.provider_id)
        if provider is not None:
            row.enhanced_provider_kind = provider.kind
            row.enhanced_provider_model = provider.model
    await db.commit()
    await db.refresh(row)
    logger.info(
        "courses: cached enhanced course %s (%d chars)",
        room_code, len(row.enhanced_markdown or ""),
    )
    return _row_to_out(row)


@router.delete("/{room_code}", status_code=204, response_class=Response)
async def delete_cached_course(
    room_code: str, db: AsyncSession = Depends(db_session)
) -> Response:
    await db.execute(delete(CachedCourse).where(CachedCourse.room_code == room_code))
    await db.commit()
    return Response(status_code=204)


@router.delete("/{room_code}/enhanced", status_code=204, response_class=Response)
async def delete_enhanced_course(
    room_code: str, db: AsyncSession = Depends(db_session)
) -> Response:
    row = await db.get(CachedCourse, room_code)
    if row is None:
        return Response(status_code=204)
    row.enhanced_markdown = None
    row.enhanced_at = None
    row.enhanced_provider_kind = None
    row.enhanced_provider_model = None
    row.enhanced_style = None
    await db.commit()
    return Response(status_code=204)
