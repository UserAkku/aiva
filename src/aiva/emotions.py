"""Emotions: one vocabulary shared by the LLM, the server and every device.

The names are exactly the 21 emotions understood by the xiaozhi-esp32 firmware
(``{"type": "llm", "emotion": ...}``), so the future ESP32 face works unchanged.
The LLM picks an emotion by starting its reply (or a sentence) with a tag such as
``<happy>``; :class:`EmotionTagParser` strips those tags out of the speech stream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Emotion(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    LAUGHING = "laughing"
    FUNNY = "funny"
    SAD = "sad"
    ANGRY = "angry"
    CRYING = "crying"
    LOVING = "loving"
    EMBARRASSED = "embarrassed"
    SURPRISED = "surprised"
    SHOCKED = "shocked"
    THINKING = "thinking"
    WINKING = "winking"
    COOL = "cool"
    RELAXED = "relaxed"
    DELICIOUS = "delicious"
    KISSY = "kissy"
    CONFIDENT = "confident"
    SLEEPY = "sleepy"
    SILLY = "silly"
    CONFUSED = "confused"


#: The subset offered to the LLM (keeps the prompt short; the rest are for animations).
LLM_EMOTIONS: tuple[Emotion, ...] = (
    Emotion.NEUTRAL,
    Emotion.HAPPY,
    Emotion.LAUGHING,
    Emotion.SAD,
    Emotion.ANGRY,
    Emotion.SURPRISED,
    Emotion.SHOCKED,
    Emotion.THINKING,
    Emotion.CONFUSED,
    Emotion.LOVING,
    Emotion.WINKING,
    Emotion.COOL,
    Emotion.SLEEPY,
    Emotion.EMBARRASSED,
    Emotion.SILLY,
    Emotion.CRYING,
    Emotion.CONFIDENT,
    Emotion.RELAXED,
)

#: Friendly synonyms the LLM might use anyway.
ALIASES: dict[str, Emotion] = {
    "love": Emotion.LOVING,
    "wink": Emotion.WINKING,
    "laugh": Emotion.LAUGHING,
    "lol": Emotion.LAUGHING,
    "excited": Emotion.HAPPY,
    "joy": Emotion.HAPPY,
    "smile": Emotion.HAPPY,
    "scared": Emotion.SHOCKED,
    "afraid": Emotion.SHOCKED,
    "shy": Emotion.EMBARRASSED,
    "think": Emotion.THINKING,
    "curious": Emotion.THINKING,
    "proud": Emotion.CONFIDENT,
    "calm": Emotion.RELAXED,
    "tired": Emotion.SLEEPY,
    "mad": Emotion.ANGRY,
    "cry": Emotion.CRYING,
    "wow": Emotion.SURPRISED,
}

#: xiaozhi devices also render an emoji in the ``text`` field of the ``llm`` message.
EMOJI: dict[Emotion, str] = {
    Emotion.NEUTRAL: "🙂",
    Emotion.HAPPY: "😊",
    Emotion.LAUGHING: "😆",
    Emotion.FUNNY: "😂",
    Emotion.SAD: "😔",
    Emotion.ANGRY: "😠",
    Emotion.CRYING: "😭",
    Emotion.LOVING: "😍",
    Emotion.EMBARRASSED: "😳",
    Emotion.SURPRISED: "😯",
    Emotion.SHOCKED: "😱",
    Emotion.THINKING: "🤔",
    Emotion.WINKING: "😉",
    Emotion.COOL: "😎",
    Emotion.RELAXED: "😌",
    Emotion.DELICIOUS: "🤤",
    Emotion.KISSY: "😘",
    Emotion.CONFIDENT: "😏",
    Emotion.SLEEPY: "😴",
    Emotion.SILLY: "😜",
    Emotion.CONFUSED: "🙄",
}


def parse_emotion(name: str | None) -> Emotion | None:
    if not name:
        return None
    key = name.strip().lower()
    try:
        return Emotion(key)
    except ValueError:
        return ALIASES.get(key)


@dataclass(slots=True)
class Segment:
    """A piece of speech text, optionally preceded by an emotion change."""

    text: str
    emotion: Emotion | None = None


_TAG = re.compile(r"<\s*/?\s*([a-zA-Z_]{2,16})\s*>")
_PARTIAL_TAG = re.compile(r"\s*<\s*/?\s*[a-zA-Z_]{0,16}\s*")


class EmotionTagParser:
    """Incrementally splits a streamed reply into speech text and emotion changes.

    ``feed("<hap")`` + ``feed("py> Hi!")`` → ``[Segment("Hi!", HAPPY)]``. Unknown
    tag-like tokens (``<b>``, ``</think>``…) are dropped so they are never spoken.
    """

    _MAX_PENDING = 24  # a '<' with no '>' within this many chars is plain text

    def __init__(self) -> None:
        self._pending = ""
        self._emotion: Emotion | None = None

    def feed(self, chunk: str) -> list[Segment]:
        self._pending += chunk
        out: list[Segment] = []
        while self._pending:
            start = self._pending.find("<")
            if start == -1:
                out.append(Segment(self._pending, self._take_emotion()))
                self._pending = ""
                break
            if start > 0:
                out.append(Segment(self._pending[:start], self._take_emotion()))
                self._pending = self._pending[start:]
            end = self._pending.find(">")
            if end == -1:
                if len(self._pending) > self._MAX_PENDING:  # not a tag after all
                    out.append(Segment(self._pending[0], self._take_emotion()))
                    self._pending = self._pending[1:]
                    continue
                break  # wait for more input
            match = _TAG.fullmatch(self._pending[: end + 1])
            if match:
                emotion = parse_emotion(match.group(1))
                if emotion is not None:
                    self._emotion = emotion
                self._pending = self._pending[end + 1 :]
            else:
                out.append(Segment(self._pending[0], self._take_emotion()))
                self._pending = self._pending[1:]
        return [s for s in out if s.text or s.emotion]

    def flush(self) -> list[Segment]:
        rest, self._pending = self._pending, ""
        if _PARTIAL_TAG.fullmatch(rest):  # a tag cut off by the end of the stream: never speak it
            rest = ""
        segment = Segment(rest, self._take_emotion())
        return [segment] if segment.text or segment.emotion else []

    def _take_emotion(self) -> Emotion | None:
        emotion, self._emotion = self._emotion, None
        return emotion
