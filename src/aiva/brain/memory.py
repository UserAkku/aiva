"""Short-term conversation memory and history trimming.

Long-term facts live in SQLite (``remember_fact``). This module keeps the recent
message history per session and trims what is sent to the model: whole user turns
only (never splitting a tool call from its result), with bulky tool outputs from
older turns shortened.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field

from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

_OLD_TOOL_OUTPUT_CHARS = 280


def _turn_starts(messages: list[ModelMessage]) -> list[int]:
    return [
        i
        for i, m in enumerate(messages)
        if isinstance(m, ModelRequest) and any(isinstance(p, UserPromptPart) for p in m.parts)
    ]


def trim_history(messages: list[ModelMessage], keep_turns: int) -> list[ModelMessage]:
    """Keep the last ``keep_turns`` user turns plus the current one; shrink old tool outputs."""
    starts = _turn_starts(messages)
    if len(starts) > keep_turns + 1:
        messages = messages[starts[-(keep_turns + 1)] :]
        starts = _turn_starts(messages)
    current = starts[-1] if starts else 0
    out: list[ModelMessage] = []
    for i, message in enumerate(messages):
        if i < current and isinstance(message, ModelRequest):
            parts = []
            changed = False
            for part in message.parts:
                if (
                    isinstance(part, ToolReturnPart)
                    and isinstance(part.content, str)
                    and len(part.content) > _OLD_TOOL_OUTPUT_CHARS
                ):
                    part = dataclasses.replace(part, content=part.content[:_OLD_TOOL_OUTPUT_CHARS] + " …")
                    changed = True
                parts.append(part)
            if changed:
                message = dataclasses.replace(message, parts=parts)
        out.append(message)
    return out


@dataclass
class Conversation:
    session_id: str
    messages: list[ModelMessage] = field(default_factory=list)
    #: categories used per recent turn, newest last (for sticky routing)
    recent_categories: list[set[str]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def sticky_categories(self, turns: int = 2) -> set[str]:
        out: set[str] = set()
        for cats in self.recent_categories[-turns:]:
            out |= cats
        return out

    def record(self, messages: list[ModelMessage], used_categories: set[str], keep_turns: int) -> None:
        self.messages = trim_history(messages, keep_turns)
        self.recent_categories = [*self.recent_categories[-4:], used_categories]
        self.updated_at = time.time()

    def record_interrupted(self, user_text: str, partial_reply: str) -> None:
        """Remember an interrupted exchange so the model knows what was said."""
        self.messages = [
            *self.messages,
            ModelRequest(parts=[UserPromptPart(user_text)]),
            ModelResponse(parts=[TextPart((partial_reply.strip() + " …(interrupted by the user)").strip())]),
        ]
        self.updated_at = time.time()


class ConversationStore:
    def __init__(self, keep_turns: int = 6, idle_reset_s: float = 30 * 60) -> None:
        self.keep_turns = keep_turns
        self.idle_reset_s = idle_reset_s
        self._items: dict[str, Conversation] = {}

    def get(self, session_id: str) -> Conversation:
        conv = self._items.get(session_id)
        if conv is None or time.time() - conv.updated_at > self.idle_reset_s:
            conv = Conversation(session_id)
            self._items[session_id] = conv
        return conv

    def reset(self, session_id: str) -> None:
        self._items.pop(session_id, None)

    def history_processor(self):
        keep = self.keep_turns

        def process(ctx: RunContext, messages: list[ModelMessage]) -> list[ModelMessage]:
            return trim_history(messages, keep)

        return process
