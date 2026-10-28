"""Parent (multi-clinic) session JSON in Redis, keyed by phone only."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from . import settings_access as sa
from .redis_client import require_redis
from .session_store import delete_session, load_session, save_session, set_pending

logger = logging.getLogger(__name__)

# Synthetic clinic id for parent-level dedupe / rate / lock keys.
PARENT_GUARD_ID = 0


def parent_session_key(phone: str) -> str:
    return f"{sa.KEY_PREFIX}psess:{phone}"


def _now_ts() -> int:
    return int(time.time())


def new_parent_session(phone: str, *, patient_name: str = "") -> dict:
    return {
        "v": 1,
        "session_id": str(uuid.uuid4()),
        "phone": phone,
        "patient_name": patient_name or "",
        "selected_clinic_id": None,
        "turn_no": 0,
        "summary": "",
        "messages": [],
        "refs": [],
        "updated_at": _now_ts(),
    }


def load_parent_session(phone: str) -> dict:
    client = require_redis()
    raw = client.get(parent_session_key(phone))
    if not raw:
        return new_parent_session(phone)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Corrupt parent session phone=***; resetting")
        return new_parent_session(phone)
    if data.get("v") != 1:
        return new_parent_session(phone)
    if int(data.get("turn_no") or 0) >= sa.max_session_turns():
        rotated = new_parent_session(
            phone,
            patient_name=data.get("patient_name") or "",
        )
        rotated["summary"] = data.get("summary") or ""
        rotated["selected_clinic_id"] = data.get("selected_clinic_id")
        return rotated
    return data


def save_parent_session(session: dict) -> None:
    client = require_redis()
    session["updated_at"] = _now_ts()
    key = parent_session_key(session["phone"])
    client.set(key, json.dumps(session, ensure_ascii=False), ex=sa.session_ttl_seconds())


def delete_parent_session(phone: str) -> None:
    require_redis().delete(parent_session_key(phone))


def clear_clinic_pending(clinic_id: int | None, phone: str) -> None:
    """Drop pending action on a clinic session without deleting chat history."""
    if not clinic_id:
        return
    clinic_sess = load_session(int(clinic_id), phone)
    if clinic_sess.get("pending"):
        set_pending(clinic_sess, None)
        save_session(clinic_sess)


def select_clinic_on_parent(
    parent: dict,
    clinic_id: int,
    *,
    clear_previous: bool = True,
) -> None:
    phone = parent["phone"]
    previous = parent.get("selected_clinic_id")
    if clear_previous and previous and int(previous) != int(clinic_id):
        clear_clinic_pending(int(previous), phone)
    parent["selected_clinic_id"] = int(clinic_id)
    parent["refs"] = []


def clear_selected_clinic(parent: dict) -> None:
    phone = parent["phone"]
    previous = parent.get("selected_clinic_id")
    if previous:
        clear_clinic_pending(int(previous), phone)
    parent["selected_clinic_id"] = None
    parent["refs"] = []


def reset_parent_and_bound_clinic(phone: str) -> dict[str, Any]:
    """Delete parent session and the last selected clinic session (if any)."""
    parent = load_parent_session(phone)
    clinic_id = parent.get("selected_clinic_id")
    delete_parent_session(phone)
    if clinic_id:
        delete_session(int(clinic_id), phone)
    return {"ok": True, "cleared_clinic_id": clinic_id}


def set_parent_refs(parent: dict, refs: list[dict]) -> None:
    parent["refs"] = refs or []


def resolve_parent_ref(parent: dict, n: int) -> dict | None:
    for ref in parent.get("refs") or []:
        if int(ref.get("n") or 0) == int(n):
            return ref
    return None
