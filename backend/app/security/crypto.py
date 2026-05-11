"""AES-256-GCM encryption helpers for secrets at rest."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_NONCE_LEN = 12  # 96-bit nonce recommended for AES-GCM


@dataclass(frozen=True)
class EncryptedBlob:
    """A self-describing encrypted payload (nonce || ciphertext || tag)."""

    nonce: bytes
    ciphertext: bytes

    def to_b64(self) -> str:
        return base64.b64encode(self.nonce + self.ciphertext).decode("ascii")

    @classmethod
    def from_b64(cls, blob: str) -> "EncryptedBlob":
        raw = base64.b64decode(blob)
        if len(raw) < _NONCE_LEN + 16:
            raise ValueError("Encrypted blob too short.")
        return cls(nonce=raw[:_NONCE_LEN], ciphertext=raw[_NONCE_LEN:])


def _aead() -> AESGCM:
    return AESGCM(get_settings().master_key_bytes)


def encrypt(plaintext: str, *, associated_data: bytes | None = None) -> str:
    """Encrypt `plaintext` and return a base64 string."""
    if plaintext is None:
        raise ValueError("plaintext cannot be None")
    nonce = os.urandom(_NONCE_LEN)
    ct = _aead().encrypt(nonce, plaintext.encode("utf-8"), associated_data)
    return EncryptedBlob(nonce=nonce, ciphertext=ct).to_b64()


def decrypt(blob: str, *, associated_data: bytes | None = None) -> str:
    """Decrypt a base64 blob produced by `encrypt`."""
    parsed = EncryptedBlob.from_b64(blob)
    pt = _aead().decrypt(parsed.nonce, parsed.ciphertext, associated_data)
    return pt.decode("utf-8")
