"""Schemas for AI / course operations."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class CourseRef(BaseModel):
    """A reference to a TryHackMe room/task."""

    room_code: str
    task_index: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None


class CourseContent(BaseModel):
    room_code: str
    title: str
    markdown: str
    sections: List[str] = Field(default_factory=list)


class EnhanceRequest(BaseModel):
    content: CourseContent
    provider_id: int
    style: str = Field(default="concise_technical")


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    provider_id: int
    messages: List[ChatMessage]
    stream: bool = True
