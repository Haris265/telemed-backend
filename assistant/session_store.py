"""Session JSON stored in Redis for one patient at one clinic."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from . import settings_access as sa
from .redis_client import require_redis

logger = logging.getLogger(__name__)


def session_key(clinic_id: int, phone: str) -> str:
    return f"{sa.KEY_PREFIX}sess:{clinic_id}:{phone}"


def _now_ts() -> int:
    return int(time.time())


def new_session(clinic_id: int, phone: str, *, patient_name: str = "") -> dict:
    return {
        "v": 1,
        "session_id": str(uuid.uuid4()),
        "clinic_id": clinic_id,
        "phone": phone,
        "patient_name": patient_name or "",
        "turn_no": 0,
        "summary": "",
        "messages": [],
        "pending": None,
        "refs": [],
        "updated_at": _now_ts(),
    }


def load_session(clinic_id: int, phone: str) -> dict:
    client = require_redis()
    raw = client.get(session_key(clinic_id, phone))
    if not raw:
        return new_session(clinic_id, phone)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Corrupt session for clinic=%s phone=***; resetting", clinic_id)
        return new_session(clinic_id, phone)
    if data.get("v") != 1:
        return new_session(clinic_id, phone)
    # Rotate if turn cap exceeded while keeping summary + name.
    if int(data.get("turn_no") or 0) >= sa.max_session_turns():
        rotated = new_session(
            clinic_id,
            phone,
            patient_name=data.get("patient_name") or "",
        )
        rotated["summary"] = data.get("summary") or ""
        return rotated
    return data


def save_session(session: dict) -> None:
    client = require_redis()
    session["updated_at"] = _now_ts()
    key = session_key(int(session["clinic_id"]), session["phone"])
    client.set(key, json.dumps(session, ensure_ascii=False), ex=sa.session_ttl_seconds())


def delete_session(clinic_id: int, phone: str) -> None:
    require_redis().delete(session_key(clinic_id, phone))


def truncate_content(text: str) -> str:
    max_chars = sa.message_content_max_chars()
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def append_message(session: dict, role: str, content: str) -> None:
    session.setdefault("messages", []).append(
        {"r": role, "c": truncate_content(content), "t": _now_ts()}
    )


def set_pending(session: dict, pending: dict | None) -> None:
    session["pending"] = pending


def set_refs(session: dict, refs: list[dict]) -> None:
    session["refs"] = refs or []


def set_patient_name(session: dict, name: str) -> None:
    session["patient_name"] = name


def bump_turn(session: dict) -> int:
    session["turn_no"] = int(session.get("turn_no") or 0) + 1
    return session["turn_no"]


def needs_compaction(session: dict) -> bool:
    return len(session.get("messages") or []) > sa.max_session_messages()


def compact_messages(session: dict, new_summary: str) -> None:
    keep = sa.keep_after_compact()
    messages = session.get("messages") or []
    session["summary"] = (new_summary or "")[: sa.summary_max_chars()]
    session["messages"] = messages[-keep:]


def resolve_ref(session: dict, n: int) -> dict | None:
    for ref in session.get("refs") or []:
        if int(ref.get("n") or 0) == int(n):
            return ref
    return None
