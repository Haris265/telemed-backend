"""Deterministic chat model that replays scripted AIMessages."""

from __future__ import annotations

from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class ScriptedChatModel(BaseChatModel):
    """Replays scripted AIMessage responses; records received message lists."""

    _scripts: list[AIMessage] = PrivateAttr(default_factory=list)
    _calls: list[list[BaseMessage]] = PrivateAttr(default_factory=list)
    _index: int = PrivateAttr(default=0)

    def __init__(self, scripts: Sequence[AIMessage] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._scripts = list(scripts or [])
        self._calls = []
        self._index = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._calls.append(list(messages))
        if self._index >= len(self._scripts):
            msg = AIMessage(content="Fallback scripted reply.")
        else:
            msg = self._scripts[self._index]
            self._index += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def calls(self) -> list[list[BaseMessage]]:
        return self._calls
