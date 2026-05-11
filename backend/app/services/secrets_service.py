"""Secret storage: thin layer over the `secrets` table with AES-GCM."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Secret
from app.security.crypto import decrypt, encrypt


async def set_secret(db: AsyncSession, key: str, value: str) -> None:
    """Create or update an encrypted secret."""
    enc = encrypt(value, associated_data=key.encode("utf-8"))
    existing = await db.scalar(select(Secret).where(Secret.key == key))
    if existing:
        existing.encrypted_value = enc
    else:
        db.add(Secret(key=key, encrypted_value=enc))
    await db.commit()


async def get_secret(db: AsyncSession, key: str) -> Optional[str]:
    row = await db.scalar(select(Secret).where(Secret.key == key))
    if row is None:
        return None
    try:
        return decrypt(row.encrypted_value, associated_data=key.encode("utf-8"))
    except Exception:
        # Tampered or wrong master key
        return None


async def delete_secret(db: AsyncSession, key: str) -> None:
    row = await db.scalar(select(Secret).where(Secret.key == key))
    if row is not None:
        await db.delete(row)
        await db.commit()


async def has_secret(db: AsyncSession, key: str) -> bool:
    return (await db.scalar(select(Secret.id).where(Secret.key == key))) is not None
