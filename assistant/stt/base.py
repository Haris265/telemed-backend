"""STT interface stub for Phase 2 voice notes."""

from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes, *, mime: str = "audio/ogg") -> str: ...


class StubSpeechToText:
    def transcribe(self, audio: bytes, *, mime: str = "audio/ogg") -> str:
        raise NotImplementedError("Speech-to-text is not enabled in Phase 1")


def get_stt() -> SpeechToText:
    return StubSpeechToText()
