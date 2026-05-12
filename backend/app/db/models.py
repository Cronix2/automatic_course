"""ORM models. All sensitive values are stored encrypted (AES-GCM) in the
`encrypted_value` column. The DB itself only stores ciphertext.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Secret(Base):
    """A generic encrypted key/value store.

    Examples of keys:
      - thm.email                         (encrypted)
      - thm.password                      (encrypted)
      - thm.session_cookie                (encrypted)
      - provider.<id>.api_key             (encrypted)
      - provider.<id>.oauth_access_token  (encrypted)
    """

    __tablename__ = "secrets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ProviderConfig(Base):
    """A user-configured AI provider entry."""

    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("name", name="uq_provider_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))  # user-friendly name
    kind: Mapped[str] = mapped_column(String(40))  # openrouter | openai | anthropic | github_models | ollama
    model: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auth_method: Mapped[str] = mapped_column(String(20))  # api_key | oauth | none
    is_default: Mapped[bool] = mapped_column(default=False)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Setting(Base):
    """Non-secret application settings (UI prefs, model choices, etc.)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    """Append-only log of sensitive actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )


class CachedCourse(Base):
    """Local cache of a fetched TryHackMe course + its AI-enhanced version.

    The room_code is the primary key. Each successful fetch overwrites the
    raw ``markdown`` + ``title``. Each successful enhancement overwrites
    ``enhanced_markdown`` + the provider snapshot. Timestamps let the UI
    show « scrappé il y a X » / « réécrit il y a Y ».
    """

    __tablename__ = "cached_courses"

    room_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    markdown: Mapped[str] = mapped_column(Text, default="")
    sections_json: Mapped[str] = mapped_column(Text, default="[]")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    enhanced_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    enhanced_provider_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    enhanced_provider_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enhanced_style: Mapped[str | None] = mapped_column(String(80), nullable=True)
    enhanced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
