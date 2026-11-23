"""Events a brain turn streams to whoever is listening (a device session, the text chat…)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..emotions import Emotion


@dataclass(slots=True)
class TextDelta:
    """A piece of the reply as the model streams it (may contain ``<emotion>`` tags)."""

    text: str


@dataclass(slots=True)
class SpeakDirect:
    """Speech produced by a tool (e.g. counting 1→100) that bypasses the LLM entirely."""

    text: str
    emotion: Emotion | None = None
    #: "hi" / "en" to force the voice language (e.g. counting in English in Hinglish mode)
    lang: str | None = None


@dataclass(slots=True)
class FaceEvent:
    """Ask the device face to show an emotion or play a named animation."""

    emotion: Emotion | None = None
    animation: str | None = None
    duration_s: float | None = None


@dataclass(slots=True)
class ToolStarted:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolFinished:
    name: str
    ok: bool
    summary: str = ""


@dataclass(slots=True)
class Notice:
    """System information AIVA should say out loud (quota warnings, errors…)."""

    text: str
    level: Literal["info", "warning", "critical"] = "info"


@dataclass(slots=True)
class TurnFinished:
    reply_text: str
    model: str | None = None
    deployment: str | None = None
    tools: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


BrainEvent = TextDelta | SpeakDirect | FaceEvent | ToolStarted | ToolFinished | Notice | TurnFinished
