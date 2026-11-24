"""Ordered speech output for one turn: TTS prefetch + real-time paced audio + face cues.

Items (sentences, emotion changes, face animations) are played strictly in the
order they were produced. Up to ``PREFETCH`` sentences are synthesised ahead of the
one being played, so after the first sentence there are no gaps. Audio is sent at
real-time speed with a small lead, which keeps the device buffer tiny: an
interruption stops AIVA within ~``lead_ms``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from ..brain.events import FaceEvent
from ..emotions import Emotion
from ..text import strip_markdown
from ..voice.tts import TTSService
from . import protocol
from .codec import DeviceCodec

PREFETCH = 2


@dataclass
class _Speech:
    text: str
    lang: str | None
    emotion: str | None = None
    audio: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None


@dataclass
class _Cue:
    message: dict[str, Any]


class Speaker:
    def __init__(
        self,
        *,
        session_id: str,
        tts: TTSService,
        codec: DeviceCodec,
        send_json: Callable[[dict[str, Any]], Awaitable[None]],
        send_bytes: Callable[[bytes], Awaitable[None]],
        lead_ms: int,
        on_first_audio: Callable[[], None] | None = None,
    ) -> None:
        self.session_id = session_id
        self.tts = tts
        self.codec = codec
        self.send_json = send_json
        self.send_bytes = send_bytes
        self.lead_s = lead_ms / 1000
        self.on_first_audio = on_first_audio
        self._items: asyncio.Queue[_Speech | _Cue | None] = asyncio.Queue()
        self._prefetch = asyncio.Semaphore(PREFETCH)
        self._play_until = 0.0
        self._started = False
        self.spoken: list[str] = []
        self._emotion: str | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self.first_audio_at: float | None = None
        self._runner = asyncio.create_task(self._run(), name=f"speaker-{session_id}")

    # ── producer side (called by the session while the brain streams) ─────────
    def say(self, text: str, lang: str | None = None) -> None:
        text = strip_markdown(text)
        if not text:
            return
        item = _Speech(text, lang, self._emotion)
        item.task = asyncio.create_task(self._synthesize(item))
        self._tasks.append(item.task)
        self._items.put_nowait(item)

    def emotion(self, value: Emotion) -> None:
        self._emotion = value.value  # sentences queued after this are spoken in this mood
        self._items.put_nowait(_Cue(protocol.emotion(self.session_id, value)))

    def face(self, event: FaceEvent) -> None:
        if event.emotion:
            self.emotion(event.emotion)
        if event.animation:
            self._items.put_nowait(
                _Cue(
                    protocol.aiva(
                        self.session_id, "face", animation=event.animation, duration=event.duration_s
                    )
                )
            )

    async def finish(self) -> None:
        """No more items: wait until everything is spoken and played, then end TTS."""
        self._items.put_nowait(None)
        await self._runner

    async def abort(self) -> None:
        self._runner.cancel()
        with suppress(asyncio.CancelledError):
            await self._runner
        for task in self._tasks:
            task.cancel()
        self.codec.reset_output()

    @property
    def started(self) -> bool:
        return self._started

    # ── synthesis (prefetched) ───────────────────────────────────────────────
    async def _synthesize(self, item: _Speech) -> None:
        async with self._prefetch:
            try:
                async for pcm in self.tts.stream(item.text, item.lang, emotion=item.emotion):
                    item.audio.put_nowait(pcm)
            except Exception:
                logger.exception("TTS failed for {!r}", item.text[:60])
            finally:
                item.audio.put_nowait(None)

    # ── playback (strictly ordered) ──────────────────────────────────────────
    async def _run(self) -> None:
        try:
            while (item := await self._items.get()) is not None:
                if isinstance(item, _Cue):
                    await self.send_json(item.message)
                    continue
                await self._play(item)
            for frame in self.codec.frames(b"", final=True):
                await self._send_frame(frame)
            # let the device finish playing what it has buffered
            remaining = self._play_until - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
        finally:
            if self._started:
                await self.send_json(protocol.tts(self.session_id, "stop"))

    async def _play(self, item: _Speech) -> None:
        announced = False
        while (pcm := await item.audio.get()) is not None:
            if not self._started:
                self._started = True
                self.first_audio_at = time.monotonic()
                if self.on_first_audio:
                    self.on_first_audio()
                await self.send_json(protocol.tts(self.session_id, "start"))
            if not announced:
                announced = True
                self.spoken.append(item.text)
                await self.send_json(protocol.tts(self.session_id, "sentence_start", item.text))
            for frame in self.codec.frames(pcm):
                await self._send_frame(frame)

    async def _send_frame(self, frame: bytes) -> None:
        now = time.monotonic()
        ahead = self._play_until - now
        if ahead > self.lead_s:
            await asyncio.sleep(ahead - self.lead_s)
            now = time.monotonic()
        await self.send_bytes(frame)
        self._play_until = max(self._play_until, now) + self.codec.frame_ms / 1000
