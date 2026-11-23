"""One connected device ("body"): turn-taking state machine for a voice conversation.

    idle ──listen start──▶ listening ──VAD end / listen stop──▶ thinking ──first audio──▶ speaking
      ▲                        ▲                                                          │
      └──── (manual mode) ─────┴──────────────────── tts stop (auto mode) ◀──────────────┘

Barge-in: on devices with echo cancellation (the browser simulator), a stricter VAD
keeps listening while AIVA speaks; real speech interrupts her within ~lead_ms.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

from ..brain.events import FaceEvent, Notice, SpeakDirect, TextDelta, ToolFinished, ToolStarted, TurnFinished
from ..emotions import Emotion, EmotionTagParser
from ..text import SentenceChunker
from ..voice.audio import MIC_RATE, duration_s, peak_level
from ..voice.vad import VADSegmenter
from . import protocol
from .codec import DeviceCodec
from .protocol import DeviceHello
from .speaker import Speaker

if TYPE_CHECKING:
    from ..services import Services

State = Literal["idle", "listening", "thinking", "speaking"]

_STT_ERROR = {
    "hinglish": "<embarrassed> Sorry, मैं ठीक से सुन नहीं पाई। Speech-to-text अभी काम नहीं कर रहा।",
    "english": "<embarrassed> Sorry, I couldn't hear that properly. Speech-to-text isn't working right now.",
}
_WAKE_ACK = {"hinglish": "<happy> जी? बोलिए!", "english": "<happy> Yes? I'm listening!"}


class DeviceSession:
    def __init__(
        self,
        services: Services,
        hello: DeviceHello,
        *,
        device_id: str,
        client_id: str,
        send_text: Callable[[str], Awaitable[None]],
        send_bytes: Callable[[bytes], Awaitable[None]],
        kind: str,
    ) -> None:
        self.services = services
        self.hello = hello
        self.id = secrets.token_hex(6)
        self.device_id = device_id
        self.client_id = client_id
        self.kind = kind
        self.connected_at = time.time()
        self._send_text = send_text
        self._send_bytes = send_bytes
        self._send_lock = asyncio.Lock()
        self.codec = DeviceCodec(hello.audio, downlink_frame_ms=60)
        self.state: State = "idle"
        self.listen_mode = "auto"
        self.turns = 0
        self.last_user_text = ""
        self.last_reply = ""
        voice = services.config.voice
        self._normal_vad = VADSegmenter(
            voice.vad_threshold,
            voice.min_speech_ms,
            voice.end_silence_ms,
            voice.pre_roll_ms,
            voice.max_utterance_s,
        )
        self._bargein_vad = VADSegmenter(
            min(0.9, voice.vad_threshold + 0.2),
            max(400, voice.min_speech_ms + 150),
            voice.end_silence_ms,
            voice.pre_roll_ms,
            voice.max_utterance_s,
        )
        self._vad = self._normal_vad
        self._manual_audio = bytearray()
        self._turn: asyncio.Task[None] | None = None
        self._speaker: Speaker | None = None
        self._background: set[asyncio.Task[None]] = set()
        self._not_busy = asyncio.Event()
        self._not_busy.set()

    # ── transport ────────────────────────────────────────────────────────────
    async def send_json(self, message: dict[str, Any]) -> None:
        import json

        async with self._send_lock:
            await self._send_text(json.dumps(message, ensure_ascii=False))

    async def send_audio(self, frame: bytes) -> None:
        async with self._send_lock:
            await self._send_bytes(frame)

    async def aiva(self, kind: str, **data: Any) -> None:
        if self.hello.is_aiva:
            await self.send_json(protocol.aiva(self.id, kind, **data))

    @property
    def language(self) -> str:
        return "english" if self.services.config.assistant.language == "english" else "hinglish"

    def set_state(self, state: State) -> None:
        if state != self.state:
            self.state = state
            self.services.bus.publish("device.state", device=self.device_id, session=self.id, state=state)
            if state in ("thinking", "speaking"):
                self._not_busy.clear()
            else:
                self._not_busy.set()
            if self.hello.is_aiva:
                task = asyncio.create_task(self.aiva("state", state=state))
                self._background.add(task)
                task.add_done_callback(self._background.discard)

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        await self.send_json(protocol.server_hello(self.id, self.hello.audio.format, 24000, 60))
        self.services.bus.publish("device.connected", device=self.device_id, session=self.id, kind=self.kind)
        logger.info("device {} connected ({}, {} audio)", self.device_id, self.kind, self.hello.audio.format)

    async def close(self) -> None:
        await self._cancel_turn()
        self.services.bus.publish("device.disconnected", device=self.device_id, session=self.id)

    # ── inbound ──────────────────────────────────────────────────────────────
    async def on_json(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "listen":
            state = msg.get("state")
            if state == "start":
                self.listen_mode = msg.get("mode", "auto")
                await self._start_listening()
            elif state == "stop":
                await self._stop_listening()
            elif state == "detect":
                await self._on_detect(str(msg.get("text", "")))
        elif kind == "abort":
            await self.interrupt(reason=str(msg.get("reason", "abort")))
        elif kind == "chat":
            text = str(msg.get("text", "")).strip()
            if text:
                await self.interrupt(reason="new text input", resume_listening=False)
                self._spawn_turn(text=text)
        elif kind == "mcp":
            logger.debug("device MCP message: {}", msg.get("payload"))
        elif kind == "hello":
            pass
        else:
            logger.debug("unhandled device message: {}", msg)

    async def on_audio(self, payload: bytes) -> None:
        try:
            pcm = self.codec.decode(payload)
        except Exception as exc:
            logger.warning("bad audio frame: {}", exc)
            return
        if self.state == "listening":
            if self.listen_mode == "manual":
                self._manual_audio += pcm
                self._vad.feed(pcm)  # only for the level meter
                return
            for event in self._vad.feed(pcm):
                if event.kind == "start":
                    await self.aiva("vad", speaking=True)
                    self.services.bus.publish("vad.start", device=self.device_id)
                elif event.kind == "end":
                    await self.aiva("vad", speaking=False)
                    self._spawn_turn(audio=event.audio)
        elif self.state == "speaking" and self._barge_in_enabled():
            for event in self._vad.feed(pcm):
                if event.kind == "start":
                    logger.info("barge-in: user interrupted AIVA")
                    self.services.bus.publish("turn.barge_in", device=self.device_id)
                    await self.interrupt(reason="barge-in", keep_vad=True)
                    await self.aiva("vad", speaking=True)

    def _barge_in_enabled(self) -> bool:
        return (
            self.services.config.voice.barge_in
            and self.hello.has_aec
            and self.listen_mode in ("auto", "realtime")
        )

    async def _start_listening(self) -> None:
        if self.state in ("thinking", "speaking"):
            await self.interrupt(reason="listen start", resume_listening=False)
        self._manual_audio.clear()
        self._vad = self._normal_vad
        self._vad.reset()
        self.set_state("listening")
        if self.hello.is_aiva:
            await self.send_json(protocol.emotion(self.id, Emotion.NEUTRAL))

    async def _stop_listening(self) -> None:
        if self.state != "listening":
            return
        if self.listen_mode == "manual":
            audio = bytes(self._manual_audio)
            self._manual_audio.clear()
            if duration_s(audio, MIC_RATE) >= 0.3:
                self._spawn_turn(audio=audio)
                return
        else:
            event = self._vad.force_end()
            if event and duration_s(event.audio, MIC_RATE) >= 0.3:
                self._spawn_turn(audio=event.audio)
                return
        self.set_state("idle")

    async def _on_detect(self, text: str) -> None:
        if len(text.strip().split()) <= 3:
            # a wake word (e.g. "Hey AIVA" from the firmware's detector): acknowledge, then listen
            await self.interrupt(reason="wake word", resume_listening=False)
            await self.speak(_WAKE_ACK[self.language])
            return
        await self.interrupt(reason="text command", resume_listening=False)
        self._spawn_turn(text=text)

    # ── turns ────────────────────────────────────────────────────────────────
    def _spawn_turn(self, *, audio: bytes | None = None, text: str | None = None) -> None:
        self._turn = asyncio.create_task(self._run_turn(audio=audio, text=text), name=f"turn-{self.id}")

    async def interrupt(self, *, reason: str, resume_listening: bool = True, keep_vad: bool = False) -> None:
        """Stop thinking/speaking immediately (barge-in, abort, new input)."""
        if self._turn is None or self._turn.done():
            return
        logger.info("interrupt ({}) while {}", reason, self.state)
        await self._cancel_turn()
        await self.send_json(protocol.tts(self.id, "stop"))
        await self.aiva("flush")
        if keep_vad:  # the barge-in segmenter is mid-utterance: keep collecting with it
            self.set_state("listening")
        elif resume_listening:
            self._vad = self._normal_vad
            self._vad.reset()
            self.set_state("listening")

    async def _cancel_turn(self) -> None:
        turn, self._turn = self._turn, None
        if turn and not turn.done():
            turn.cancel()
            with suppress(asyncio.CancelledError):
                await turn

    def _new_speaker(self) -> Speaker:
        def first_audio() -> None:
            self.set_state("speaking")
            if self._barge_in_enabled():
                self._vad = self._bargein_vad
                self._vad.reset()

        return Speaker(
            session_id=self.id,
            tts=self.services.tts,
            codec=self.codec,
            send_json=self.send_json,
            send_bytes=self.send_audio,
            lead_ms=self.services.config.voice.playback_lead_ms,
            on_first_audio=first_audio,
        )

    async def speak(self, text_with_tags: str, lang: str | None = None) -> None:
        """Say something outside a brain turn (wake acknowledgement, reminders)."""
        speaker = self._new_speaker()
        parser = EmotionTagParser()
        for seg in [*parser.feed(text_with_tags), *parser.flush()]:
            if seg.emotion:
                speaker.emotion(seg.emotion)
            if seg.text.strip():
                speaker.say(seg.text, lang)
        try:
            await speaker.finish()
        finally:
            self._after_speaking()

    async def announce(self, text: str) -> None:
        """Speak a reminder/timer as soon as AIVA is not busy."""
        await self._not_busy.wait()
        await self.speak(text)

    def _after_speaking(self) -> None:
        self._vad = self._normal_vad
        self._vad.reset()
        self.set_state("listening" if self.listen_mode in ("auto", "realtime") else "idle")

    async def _run_turn(self, *, audio: bytes | None, text: str | None) -> None:
        services = self.services
        timings: dict[str, float] = {}
        started = time.monotonic()
        self.set_state("thinking")
        await self.send_json(protocol.emotion(self.id, Emotion.THINKING))
        speaker: Speaker | None = None
        try:
            if audio is not None:
                if peak_level(audio) < 0.015 or duration_s(audio, MIC_RATE) < 0.3:
                    self._after_speaking()
                    return
                try:
                    transcript = await services.stt.transcribe(audio)
                except Exception as exc:
                    logger.error("STT failed: {}", exc)
                    services.bus.publish("error", where="stt", message=str(exc))
                    await self.speak(_STT_ERROR[self.language])
                    return
                timings["stt_ms"] = transcript.latency_ms
                text = transcript.text
                if not text:
                    await self.send_json(protocol.emotion(self.id, Emotion.CONFUSED))
                    self._after_speaking()
                    return
                await self.send_json(protocol.stt(self.id, text))
            assert text is not None
            self.last_user_text = text
            self.turns += 1
            services.bus.publish("turn.user", device=self.device_id, session=self.id, text=text)

            speaker = self._speaker = self._new_speaker()
            await self._stream_brain(text, speaker, timings, started)
            await speaker.finish()
            timings["total_ms"] = (time.monotonic() - started) * 1000
        except asyncio.CancelledError:
            if speaker:
                await speaker.abort()
            raise
        finally:
            self._speaker = None
        self._after_speaking()

    async def _stream_brain(
        self, text: str, speaker: Speaker, timings: dict[str, float], started: float
    ) -> None:
        services = self.services
        parser = EmotionTagParser()
        chunker = SentenceChunker()
        tools: list[str] = []
        first_token: float | None = None

        def push_text(segment_text: str) -> None:
            for sentence in chunker.feed(segment_text):
                speaker.say(sentence)

        def flush_text() -> None:
            for seg in parser.flush():
                if seg.emotion:
                    speaker.emotion(seg.emotion)
                push_text(seg.text)
            for sentence in chunker.flush():
                speaker.say(sentence)

        async for event in services.brain.run_turn(self.id, text, has_face=True):
            if isinstance(event, TextDelta):
                if first_token is None:
                    first_token = time.monotonic()
                    timings["llm_first_token_ms"] = (first_token - started) * 1000
                for seg in parser.feed(event.text):
                    if seg.emotion:
                        for sentence in chunker.flush():  # emotion changes at a sentence boundary
                            speaker.say(sentence)
                        speaker.emotion(seg.emotion)
                    push_text(seg.text)
            elif isinstance(event, SpeakDirect):
                flush_text()
                if event.emotion:
                    speaker.emotion(event.emotion)
                speaker.say(event.text, event.lang)
            elif isinstance(event, FaceEvent):
                flush_text()
                speaker.face(event)
            elif isinstance(event, ToolStarted):
                tools.append(event.name)
                services.bus.publish("tool.start", device=self.device_id, name=event.name, args=event.args)
                await self.aiva("tool", name=event.name, status="start")
                if not speaker.started:
                    await self.send_json(protocol.emotion(self.id, Emotion.THINKING))
            elif isinstance(event, ToolFinished):
                services.bus.publish(
                    "tool.end", device=self.device_id, name=event.name, ok=event.ok, summary=event.summary
                )
                await self.aiva("tool", name=event.name, status="end", ok=event.ok)
            elif isinstance(event, Notice):
                flush_text()
                await self.aiva("notice", text=event.text, level=event.level)
                speaker.say(event.text)
            elif isinstance(event, TurnFinished):
                flush_text()
                self.last_reply = event.reply_text
                if speaker.first_audio_at:
                    timings["first_audio_ms"] = (speaker.first_audio_at - started) * 1000
                services.db.log_turn(self.id, text, event.reply_text, event.deployment, event.tools, timings)
                services.bus.publish(
                    "turn.assistant",
                    device=self.device_id,
                    session=self.id,
                    text=event.reply_text,
                    model=event.model,
                    deployment=event.deployment,
                    tools=event.tools,
                    error=event.error,
                    timings={k: round(v) for k, v in timings.items()},
                    tokens={"in": event.input_tokens, "out": event.output_tokens},
                )
        flush_text()
