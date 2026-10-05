"""Strict Fernet helpers for Meta secrets stored on ClinicAssistantConfig."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class SecretDecryptionError(Exception):
    """Raised when a stored secret cannot be decrypted with the current key."""


def _fernet() -> Fernet:
    raw = (getattr(settings, "META_TOKEN_FERNET_KEY", "") or "").strip()
    if raw:
        try:
            return Fernet(raw.encode("utf-8"))
        except (ValueError, TypeError):
            digest = hashlib.sha256(raw.encode("utf-8")).digest()
            return Fernet(base64.urlsafe_b64encode(digest))

    secret = settings.SECRET_KEY
    digest = hashlib.sha256(str(secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher: str) -> str:
    """Decrypt a secret; raise SecretDecryptionError on failure (never return ciphertext)."""
    if not cipher:
        return ""
    try:
        return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptionError("Unable to decrypt secret with current key") from exc
