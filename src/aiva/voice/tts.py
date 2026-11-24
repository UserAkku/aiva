"""Text-to-speech with a chain of engines and emotion-aware delivery.

Engines (tried in order, each with its own circuit breaker):

* **Sarvam Bulbul v4 Flash** — Indian voices built for code-mixed Hinglish, with
  "companion" personas; the most human-sounding option (needs ``SARVAM_API_KEY``,
  free credits on sign-up). Streams raw PCM.
* **Microsoft Edge neural voices** (via edge-tts) — free, no key; streamed MP3 decoded
  progressively so the first audio arrives in ~1 s.
* **macOS ``say``** — offline last resort.

Every sentence carries the emotion AIVA chose for it; engines turn that into delivery:
happy is brighter and a little quicker, sad slower and lower, angry louder, sleepy soft.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import miniaudio
from loguru import logger

from ..config import Secrets, TTSConfig
from ..text import clean_for_tts, has_devanagari
from .audio import SPEAKER_RATE, read_wav, resample

_MP3_MARGIN = 2 * 1152  # samples held back: the last frames of a partial MP3 may be incomplete
SARVAM_STREAM_URL = "https://api.sarvam.ai/text-to-speech/stream"

# emotion → (rate %, pitch Hz, volume %) offsets for Edge
EDGE_PROSODY: dict[str, tuple[int, int, int]] = {
    "happy": (8, 12, 0),
    "laughing": (12, 22, 5),
    "funny": (10, 18, 0),
    "sad": (-12, -14, -10),
    "angry": (6, -6, 10),
    "crying": (-10, -8, -5),
    "loving": (-4, 8, -5),
    "embarrassed": (-4, 6, -10),
    "surprised": (8, 28, 5),
    "shocked": (10, 30, 10),
    "thinking": (-8, -4, -5),
    "winking": (6, 14, 0),
    "cool": (-4, -8, 0),
    "relaxed": (-8, -2, -5),
    "delicious": (4, 10, 0),
    "kissy": (-6, 10, -10),
    "confident": (2, -4, 5),
    "sleepy": (-18, -18, -15),
    "silly": (10, 24, 0),
    "confused": (-4, 8, 0),
}
# emotion → (pace, pitch, loudness, temperature) for Sarvam (neutral = 1.0, 0, 1.0, 0.6)
SARVAM_PROSODY: dict[str, tuple[float, float, float, float]] = {
    "happy": (1.05, 0.06, 1.05, 0.75),
    "laughing": (1.1, 0.1, 1.1, 0.85),
    "funny": (1.08, 0.08, 1.05, 0.85),
    "sad": (0.9, -0.08, 0.9, 0.5),
    "angry": (1.05, -0.04, 1.25, 0.7),
    "crying": (0.88, -0.06, 0.95, 0.6),
    "loving": (0.95, 0.04, 0.95, 0.7),
    "embarrassed": (0.95, 0.05, 0.85, 0.6),
    "surprised": (1.06, 0.12, 1.1, 0.8),
    "shocked": (1.08, 0.14, 1.2, 0.8),
    "thinking": (0.94, -0.02, 0.95, 0.55),
    "winking": (1.05, 0.07, 1.0, 0.75),
    "cool": (0.97, -0.05, 1.0, 0.6),
    "relaxed": (0.92, -0.02, 0.95, 0.55),
    "delicious": (1.0, 0.06, 1.0, 0.7),
    "kissy": (0.95, 0.06, 0.9, 0.7),
    "confident": (1.0, -0.03, 1.08, 0.65),
    "sleepy": (0.85, -0.08, 0.8, 0.5),
    "silly": (1.1, 0.1, 1.05, 0.9),
    "confused": (0.96, 0.05, 0.95, 0.65),
}


def _num(value: str, default: int = 0) -> int:
    match = re.search(r"[-+]?\d+", value or "")
    return int(match.group()) if match else default


def _decode_mp3(data: bytes):
    return miniaudio.decode(
        data, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=SPEAKER_RATE
    ).samples


class _Breaker:
    """Skip an engine for a while after repeated failures (so a demo never stalls on it)."""

    def __init__(self, threshold: int = 2, cooldown_s: float = 60.0) -> None:
        self.failures = 0
        self.until = 0.0
        self.threshold = threshold
        self.cooldown_s = cooldown_s

    @property
    def open(self) -> bool:
        return time.monotonic() < self.until

    def ok(self) -> None:
        self.failures = 0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.until = time.monotonic() + self.cooldown_s


class TTSService:
    def __init__(self, config: TTSConfig, language: str, secrets: Secrets | None = None) -> None:
        self.config = config
        self.language = language
        self.secrets = secrets or Secrets()
        self._cache: OrderedDict[tuple[str, str, str, str], bytes] = OrderedDict()
        self._breakers = {"sarvam": _Breaker(), "edge": _Breaker()}
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        self.last_engine = ""

    def reconfigure(self, config: TTSConfig, language: str, secrets: Secrets | None = None) -> None:
        self.config, self.language = config, language
        if secrets is not None:
            self.secrets = secrets
        self._cache.clear()
        for breaker in self._breakers.values():
            breaker.until, breaker.failures = 0.0, 0

    # ── engine selection ─────────────────────────────────────────────────────
    def is_hindi(self, text: str, lang: str | None) -> bool:
        """One consistent voice per mode; only switch when the text or a hint demands it."""
        if lang:
            return lang.startswith("hi")
        if has_devanagari(text):
            return True  # the English voice cannot read Devanagari
        return self.language in ("hinglish", "hindi")

    def engines(self) -> list[str]:
        sarvam_ready = bool(self.secrets.key_for("sarvam"))
        order = {
            "auto": ["sarvam", "edge", "say"] if sarvam_ready else ["edge", "say"],
            "sarvam": ["sarvam", "edge", "say"],
            "edge": ["edge", "say"],
            "say": ["say"],
        }[self.config.engine]
        return [e for e in order if not (e in self._breakers and self._breakers[e].open)] or ["say"]

    @property
    def primary(self) -> str:
        return self.engines()[0]

    # ── public API ───────────────────────────────────────────────────────────
    async def synthesize(
        self,
        text: str,
        lang: str | None = None,
        voice: str | None = None,
        emotion: str | None = None,
        engine: str | None = None,
    ) -> bytes:
        """Whole utterance as mono PCM16 at :data:`SPEAKER_RATE` (24 kHz). Empty text → empty audio."""
        return b"".join([chunk async for chunk in self.stream(text, lang, voice, emotion, engine)])

    async def stream(
        self,
        text: str,
        lang: str | None = None,
        voice: str | None = None,
        emotion: str | None = None,
        engine: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield PCM16 @ 24 kHz as soon as it is synthesised, trying engines in order."""
        text = clean_for_tts(text)
        if not text:
            return
        hindi = self.is_hindi(text, lang)
        mood = (emotion or "neutral") if self.config.emotion_prosody else "neutral"
        for name in [engine, "say"] if engine else self.engines():
            key = (name, voice or "", mood, text)
            if cached := self._cache.get(key):
                self._cache.move_to_end(key)
                self.last_engine = name
                yield cached
                return
            collected = bytearray()
            try:
                async with asyncio.timeout(14):
                    async for pcm in self._run(name, text, hindi, voice, mood):
                        collected += pcm
                        yield pcm
                if not collected:
                    raise RuntimeError(f"{name} produced no audio")
            except Exception as exc:
                if name in self._breakers:
                    self._breakers[name].fail()
                logger.warning("TTS engine {} failed: {!r}", name, exc)
                if collected:  # part of the sentence was already spoken: just stop here
                    return
                continue
            if name in self._breakers:
                self._breakers[name].ok()
            self.last_engine = name
            if len(text) <= 80:
                self._cache[key] = bytes(collected)
                while len(self._cache) > 96:
                    self._cache.popitem(last=False)
            return

    def _run(self, engine: str, text: str, hindi: bool, voice: str | None, mood: str) -> AsyncIterator[bytes]:
        if engine == "sarvam":
            return self._sarvam(text, hindi, voice, mood)
        if engine == "edge":
            edge_voice = voice if voice and "Neural" in voice else None
            return self._edge(
                text, edge_voice or (self.config.voice_hindi if hindi else self.config.voice_english), mood
            )
        return self._say_stream(text, self.config.say_voice_hindi if hindi else self.config.say_voice_english)

    # ── Sarvam Bulbul (HTTP stream, raw PCM) ─────────────────────────────────
    async def _sarvam(self, text: str, hindi: bool, voice: str | None, mood: str) -> AsyncIterator[bytes]:
        key = self.secrets.key_for("sarvam")
        if not key:
            raise RuntimeError("no SARVAM_API_KEY")
        pace, pitch, loudness, temperature = SARVAM_PROSODY.get(mood, (1.0, 0.0, 1.0, 0.6))
        body = {
            "text": text[:3400],
            "language_code": "hi-IN" if hindi or has_devanagari(text) else "en-IN",
            "model": self.config.sarvam_model,
            "speaker": voice if voice and "Neural" not in voice else self.config.sarvam_speaker,
            "output_audio_codec": "linear16",
            "speech_sample_rate": SPEAKER_RATE,
            "pace": pace,
            "pitch": pitch,
            "loudness": loudness,
            "temperature": temperature,
        }
        async with self._http.stream(
            "POST", SARVAM_STREAM_URL, json=body, headers={"api-subscription-key": key}
        ) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread())[:300].decode(errors="replace")
                raise RuntimeError(f"Sarvam HTTP {resp.status_code}: {detail}")
            pending = b""
            async for chunk in resp.aiter_bytes():
                data = pending + chunk
                cut = len(data) - len(data) % 2  # keep 16-bit samples whole
                pending = data[cut:]
                if cut:
                    yield data[:cut]

    # ── Edge neural voices (progressive MP3 decode) ──────────────────────────
    async def _edge(self, text: str, voice: str, mood: str) -> AsyncIterator[bytes]:
        """Stream Edge TTS, decoding the growing MP3 progressively.

        MP3 decoding is deterministic from the start of the stream, so re-decoding the
        buffer and emitting only samples older than the last two frames is glitch-free.
        """
        import edge_tts

        d_rate, d_pitch, d_volume = EDGE_PROSODY.get(mood, (0, 0, 0))
        rate = _num(self.config.rate) + d_rate
        pitch = _num(self.config.pitch) + d_pitch
        communicate = edge_tts.Communicate(
            text, voice, rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz", volume=f"{d_volume:+d}%"
        )
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

    # ── macOS say (offline) ──────────────────────────────────────────────────
    async def _say_stream(self, text: str, voice: str) -> AsyncIterator[bytes]:
        pcm = await self._say(text, voice)
        if pcm:
            yield pcm

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
