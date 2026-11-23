"""Text-to-speech: Microsoft Edge neural voices (free, via edge-tts) → macOS ``say`` (offline).

Voice choice per sentence: explicit language hint > Devanagari script → Hindi voice >
assistant language. A small circuit breaker switches to ``say`` for a minute after
repeated Edge failures, so a flaky network never leaves AIVA mute mid-demo.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from pathlib import Path

import miniaudio
from loguru import logger

from ..config import TTSConfig
from ..text import clean_for_tts, has_devanagari
from .audio import SPEAKER_RATE, read_wav, resample

_MP3_MARGIN = 2 * 1152  # samples held back: the last frames of a partial MP3 may be incomplete


def _decode_mp3(data: bytes):
    return miniaudio.decode(
        data, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=SPEAKER_RATE
    ).samples


class TTSService:
    def __init__(self, config: TTSConfig, language: str) -> None:
        self.config = config
        self.language = language
        self._cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._edge_failures = 0
        self._edge_disabled_until = 0.0
        self.last_engine = ""

    def reconfigure(self, config: TTSConfig, language: str) -> None:
        self.config, self.language = config, language
        self._cache.clear()

    def is_hindi(self, text: str, lang: str | None) -> bool:
        """One consistent voice per mode; only switch when the text or a hint demands it."""
        if lang:
            return lang.startswith("hi")
        if has_devanagari(text):
            return True  # the English voice cannot read Devanagari
        return self.language in ("hinglish", "hindi")

    def _pick(self, text: str, lang: str | None, voice: str | None = None) -> tuple[bool, str, bool]:
        hindi = self.is_hindi(text, lang)
        use_edge = self.config.engine == "edge" and time.monotonic() >= self._edge_disabled_until
        if use_edge and voice:
            return use_edge, voice, hindi
        if use_edge:
            return use_edge, (self.config.voice_hindi if hindi else self.config.voice_english), hindi
        return use_edge, (self.config.say_voice_hindi if hindi else self.config.say_voice_english), hindi

    async def synthesize(self, text: str, lang: str | None = None, voice: str | None = None) -> bytes:
        """Whole utterance as mono PCM16 at :data:`SPEAKER_RATE` (24 kHz). Empty text → empty audio."""
        return b"".join([chunk async for chunk in self.stream(text, lang, voice)])

    async def stream(
        self, text: str, lang: str | None = None, voice: str | None = None
    ) -> AsyncIterator[bytes]:
        """Yield PCM16 @ 24 kHz as soon as it is decoded (first audio ≈ 1 s with Edge)."""
        text = clean_for_tts(text)
        if not text:
            return
        use_edge, voice, hindi = self._pick(text, lang, voice)
        key = (voice, text)
        if cached := self._cache.get(key):
            self._cache.move_to_end(key)
            yield cached
            return

        collected = bytearray()
        if use_edge:
            try:
                async with asyncio.timeout(12):
                    async for pcm in self._edge_stream(text, voice):
                        collected += pcm
                        yield pcm
                self._edge_failures = 0
                self.last_engine = "edge"
            except Exception as exc:
                self._edge_failures += 1
                logger.warning("edge-tts failed ({}x): {!r}", self._edge_failures, exc)
                if self._edge_failures >= 2:
                    self._edge_disabled_until = time.monotonic() + 60
                if collected:  # part of the sentence was already spoken: just stop here
                    return
                voice = self.config.say_voice_hindi if hindi else self.config.say_voice_english
                key = (voice, text)
        if not collected:
            pcm = await self._say(text, voice)
            self.last_engine = "say"
            collected += pcm
            if pcm:
                yield pcm
        if len(text) <= 80 and collected:
            self._cache[key] = bytes(collected)
            while len(self._cache) > 96:
                self._cache.popitem(last=False)

    async def _edge_stream(self, text: str, voice: str) -> AsyncIterator[bytes]:
        """Stream Edge TTS, decoding the growing MP3 progressively.

        MP3 decoding is deterministic from the start of the stream, so re-decoding the
        buffer and emitting only samples older than the last two frames is glitch-free.
        """
        import edge_tts

        communicate = edge_tts.Communicate(text, voice, rate=self.config.rate, pitch=self.config.pitch)
        mp3 = bytearray()
        emitted = 0
        next_decode_at = 4096  # ≈ 0.7 s of 48 kbps MP3
        async for chunk in communicate.stream():
            if chunk["type"] != "audio":
                continue
            mp3 += chunk["data"]
            if len(mp3) >= next_decode_at:
                samples = await asyncio.to_thread(_decode_mp3, bytes(mp3))
                safe = len(samples) - _MP3_MARGIN
                if safe > emitted:
                    yield samples[emitted:safe].tobytes()
                    emitted = safe
                next_decode_at = len(mp3) + 6000
        if not mp3:
            raise RuntimeError("edge-tts returned no audio")
        samples = await asyncio.to_thread(_decode_mp3, bytes(mp3))
        if len(samples) > emitted:
            yield samples[emitted:].tobytes()

    async def _say(self, text: str, voice: str) -> bytes:
        """Offline fallback using the built-in macOS synthesizer."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "say.wav"
            args = [
                "say",
                *(["-v", voice] if voice else []),
                "-o",
                str(out),
                f"--data-format=LEI16@{SPEAKER_RATE}",
                "--",
                text,
            ]
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
            )
            _, err = await proc.communicate()
            if proc.returncode != 0 or not out.exists():
                if voice:
                    logger.warning(
                        "say -v {} failed ({}); using the default voice", voice, err.decode()[:100]
                    )
                    return await self._say(text, "")
                return b""
            pcm, rate = read_wav(out.read_bytes())
        return resample(pcm, rate, SPEAKER_RATE)
