"""Encrypt/decrypt WhatsApp access tokens at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    raw = (getattr(settings, "META_TOKEN_FERNET_KEY", "") or "").strip()
    if raw:
        try:
            return Fernet(raw.encode("utf-8"))
        except (ValueError, TypeError):
            digest = hashlib.sha256(raw.encode("utf-8")).digest()
            return Fernet(base64.urlsafe_b64encode(digest))

    secret = (
        getattr(settings, "META_APP_SECRET", "")
        or getattr(settings, "META_WA_APP_SECRET", "")
        or settings.SECRET_KEY
    )
    digest = hashlib.sha256(str(secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(cipher: str) -> str:
    if not cipher:
        return ""
    try:
        return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return cipher
