"""Immutable turn context and channel message contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from catalog.models import Clinic

from .models import AssistantPlan, ClinicAssistantConfig


@dataclass(frozen=True)
class InboundMessage:
    clinic_id: int
    phone: str
    message_id: str
    kind: Literal["text", "voice"]
    text: str
    profile_name: str = ""
    received_at: float = 0.0


@dataclass(frozen=True)
class ClinicContext:
    clinic: Clinic
    config: ClinicAssistantConfig
    plan: AssistantPlan
    phone: str
    patient_name: str = ""

    @property
    def clinic_id(self) -> int:
        return self.clinic.id


@dataclass
class TurnResult:
    reply: str
    session_id: str = ""
    quota: dict[str, Any] = field(default_factory=dict)
    notice: str | None = None
    outcome: str = "ok"
    status: int = 200
