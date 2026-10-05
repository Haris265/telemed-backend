"""Canonical phone helpers for assistant sessions and patient lookup."""

from __future__ import annotations

from patients.serializers import normalize_phone


def canonical_phone(raw: str) -> str:
    """
    Digits-only canonical form for Redis keys and new PatientProfile rows.

    Pakistan mobile numbers typed as 03XXXXXXXXX become 92XXXXXXXXXX.
    """
    digits = normalize_phone(raw or "")
    if digits.startswith("0092"):
        digits = digits[2:]  # 0092... -> 92...
    if len(digits) == 11 and digits.startswith("0"):
        return "92" + digits[1:]
    if len(digits) == 10 and digits.startswith("3"):
        return "92" + digits
    return digits


def phone_variants(canonical: str) -> list[str]:
    """Lookup variants so legacy 03... / local 10-digit rows are found."""
    phone = canonical_phone(canonical)
    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            variants.append(value)

    add(phone)
    if phone.startswith("92") and len(phone) == 12:
        local10 = phone[2:]
        add("0" + local10)
        add(local10)
    return variants


def mask_phone(phone: str) -> str:
    digits = normalize_phone(phone or "")
    if len(digits) <= 4:
        return "****"
    return ("*" * (len(digits) - 4)) + digits[-4:]
