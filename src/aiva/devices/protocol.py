"""Message builders/parsers for the xiaozhi WebSocket protocol (+ AIVA extensions).

Upstream reference: https://github.com/78/xiaozhi-esp32/blob/main/docs/websocket.md

AIVA extensions (only sent to devices whose hello has ``features.aiva = true``):
* ``audio_params.format = "pcm16"`` — raw little-endian PCM instead of Opus.
* ``{"type": "aiva", "kind": "tool" | "notice" | "face" | "vad" | "flush" | "state", ...}``.
* device → server ``{"type": "chat", "text": "..."}`` — typed input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..emotions import EMOJI, Emotion

AudioFormat = Literal["opus", "pcm16"]


@dataclass(slots=True)
class AudioParams:
    format: AudioFormat = "opus"
    sample_rate: int = 16000
    channels: int = 1
    frame_duration: int = 60

    @classmethod
    def parse(cls, raw: dict[str, Any] | None) -> AudioParams:
        raw = raw or {}
        fmt = str(raw.get("format", "opus")).lower()
        return cls(
            format="pcm16" if fmt in ("pcm16", "pcm", "s16le") else "opus",
            sample_rate=int(raw.get("sample_rate", 16000)),
            channels=int(raw.get("channels", 1)),
            frame_duration=int(raw.get("frame_duration", 60)),
        )


@dataclass(slots=True)
class DeviceHello:
    version: int = 1
    transport: str = "websocket"
    features: dict[str, Any] = field(default_factory=dict)
    audio: AudioParams = field(default_factory=AudioParams)

    @classmethod
    def parse(cls, msg: dict[str, Any]) -> DeviceHello:
        return cls(
            version=int(msg.get("version", 1)),
            transport=str(msg.get("transport", "websocket")),
            features=dict(msg.get("features") or {}),
            audio=AudioParams.parse(msg.get("audio_params")),
        )

    @property
    def is_aiva(self) -> bool:
        return bool(self.features.get("aiva"))

    @property
    def has_aec(self) -> bool:
        return bool(self.features.get("aec"))


def server_hello(session_id: str, fmt: AudioFormat, sample_rate: int, frame_ms: int) -> dict[str, Any]:
    return {
        "type": "hello",
        "transport": "websocket",
        "session_id": session_id,
        "audio_params": {
            "format": fmt,
            "sample_rate": sample_rate,
            "channels": 1,
            "frame_duration": frame_ms,
        },
    }


def stt(session_id: str, text: str) -> dict[str, Any]:
    return {"session_id": session_id, "type": "stt", "text": text}


def emotion(session_id: str, value: Emotion) -> dict[str, Any]:
    return {"session_id": session_id, "type": "llm", "emotion": value.value, "text": EMOJI.get(value, "🙂")}


def tts(
    session_id: str, state: Literal["start", "stop", "sentence_start"], text: str | None = None
) -> dict[str, Any]:
    msg: dict[str, Any] = {"session_id": session_id, "type": "tts", "state": state}
    if text is not None:
        msg["text"] = text
    return msg


def aiva(session_id: str, kind: str, **data: Any) -> dict[str, Any]:
    return {"session_id": session_id, "type": "aiva", "kind": kind, **data}
