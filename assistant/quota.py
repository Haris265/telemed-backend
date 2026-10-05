"""Plan quota enforcement (fail-closed Redis)."""

from __future__ import annotations

from dataclasses import dataclass

from appointments.services import pakistan_now

from . import settings_access as sa
from .models import AssistantPlan
from .redis_client import require_redis

# Atomic reserve: INCR then compare; DECR back if over cap.
_RESERVE_LUA = """
local current = redis.call('INCR', KEYS[1])
if tonumber(ARGV[2]) > 0 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
if current > tonumber(ARGV[1]) then
  redis.call('DECR', KEYS[1])
  return 0
end
return 1
"""

_REFUND_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current > 0 then
  return redis.call('DECR', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class QuotaSnapshot:
    plan: str
    patient_replies_used: int
    patient_replies_max: int
    clinic_text_used_today: int
    clinic_text_max: int
    clinic_voice_used_today: int
    clinic_voice_max: int

    def as_dict(self) -> dict:
        return {
            "plan": self.plan,
            "patient_replies_used": self.patient_replies_used,
            "patient_replies_max": self.patient_replies_max,
            "clinic_text_used_today": self.clinic_text_used_today,
            "clinic_text_max": self.clinic_text_max,
            "clinic_voice_used_today": self.clinic_voice_used_today,
            "clinic_voice_max": self.clinic_voice_max,
        }


def _day_bucket() -> str:
    return pakistan_now().strftime("%Y%m%d")


def _month_bucket() -> str:
    return pakistan_now().strftime("%Y%m")


def _patient_key(clinic_id: int, phone: str) -> str:
    return f"{sa.KEY_PREFIX}q:mon:{clinic_id}:{phone}:{_month_bucket()}:replies"


def _day_key(clinic_id: int, kind: str) -> str:
    return f"{sa.KEY_PREFIX}q:day:{clinic_id}:{_day_bucket()}:{kind}"


def _notice_day_key(clinic_id: int, kind: str) -> str:
    return f"{sa.KEY_PREFIX}notice:day:{clinic_id}:{_day_bucket()}:{kind}"


def _notice_mon_key(clinic_id: int, phone: str) -> str:
    return f"{sa.KEY_PREFIX}notice:mon:{clinic_id}:{phone}:{_month_bucket()}"


def _get_int(key: str) -> int:
    raw = require_redis().get(key)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def patient_replies_used(clinic_id: int, phone: str) -> int:
    return _get_int(_patient_key(clinic_id, phone))


def patient_at_cap(clinic_id: int, phone: str, plan: AssistantPlan) -> bool:
    return patient_replies_used(clinic_id, phone) >= int(
        plan.max_bot_replies_per_patient_month
    )


def claim_patient_notice(clinic_id: int, phone: str) -> bool:
    """Return True the first time the monthly notice should be sent."""
    key = _notice_mon_key(clinic_id, phone)
    return bool(require_redis().set(key, "1", nx=True, ex=40 * 24 * 3600))


def claim_day_notice(clinic_id: int, kind: str) -> bool:
    key = _notice_day_key(clinic_id, kind)
    return bool(require_redis().set(key, "1", nx=True, ex=36 * 3600))


def reserve_day_slot(clinic_id: int, kind: str, plan: AssistantPlan) -> bool:
    """Reserve one clinic daily text/voice slot. Returns False if over cap."""
    cap = (
        int(plan.max_text_messages_per_day)
        if kind == "text"
        else int(plan.max_voice_notes_per_day)
    )
    if kind == "voice" and cap <= 0:
        return False
    client = require_redis()
    key = _day_key(clinic_id, kind)
    ok = client.eval(_RESERVE_LUA, 1, key, cap, 36 * 3600)
    return bool(int(ok))


def refund_day_slot(clinic_id: int, kind: str) -> None:
    require_redis().eval(_REFUND_LUA, 1, _day_key(clinic_id, kind))


def count_patient_reply(clinic_id: int, phone: str) -> int:
    client = require_redis()
    key = _patient_key(clinic_id, phone)
    value = int(client.incr(key))
    if value == 1:
        client.expire(key, 40 * 24 * 3600)
    return value


def snapshot(clinic_id: int, phone: str, plan: AssistantPlan) -> QuotaSnapshot:
    return QuotaSnapshot(
        plan=plan.code,
        patient_replies_used=patient_replies_used(clinic_id, phone),
        patient_replies_max=int(plan.max_bot_replies_per_patient_month),
        clinic_text_used_today=_get_int(_day_key(clinic_id, "text")),
        clinic_text_max=int(plan.max_text_messages_per_day),
        clinic_voice_used_today=_get_int(_day_key(clinic_id, "voice")),
        clinic_voice_max=int(plan.max_voice_notes_per_day),
    )
