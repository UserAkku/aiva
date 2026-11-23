"""Speech-to-text: Groq Whisper (primary) → Mistral Voxtral (fallback). Both have free tiers.

Whisper hallucinates on silence/noise ("Thank you.", "Thanks for watching!"), so
segments with a high no-speech probability and known junk phrases are dropped.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx
from loguru import logger

from ..config import DeploymentConfig, Limits, Secrets, STTConfig
from ..events import EventBus
from ..llm.quota import QuotaGuard
from .audio import MIC_RATE, duration_s, wav_bytes

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MISTRAL_URL = "https://api.mistral.ai/v1/audio/transcriptions"
MISTRAL_STT_MODEL = "voxtral-mini-latest"

_JUNK = re.compile(
    r"^\W*(thank(s| you)( so much)?( for watching)?|thanks for watching|subtitles by.*|you|bye|"
    r"please subscribe.*|amara\.org.*|transcribed by.*|उपशीर्षक.*|धन्यवाद|शुक्रिया|ٹھیک ہے|سبسکرائب.*)\W*$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Transcript:
    text: str
    language: str | None = None
    audio_s: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""


class STTService:
    def __init__(self, config: STTConfig, secrets: Secrets, quota: QuotaGuard, bus: EventBus) -> None:
        self.config = config
        self.secrets = secrets
        self.quota = quota
        self.bus = bus
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
        self.quota.register(
            DeploymentConfig(
                id="groq-whisper",
                provider="groq",
                model=config.model,
                priority=1,
                limits=Limits(rpm=20, rpd=2000),
            ),
            has_key=bool(secrets.key_for("groq")),
        )

    def reconfigure(self, config: STTConfig, secrets: Secrets) -> None:
        self.config, self.secrets = config, secrets
        self.quota.states["groq-whisper"].has_key = bool(secrets.key_for("groq"))

    @property
    def available(self) -> bool:
        return bool(self.secrets.key_for("groq") or self.secrets.key_for("mistral"))

    async def transcribe(self, pcm16: bytes, sample_rate: int = MIC_RATE) -> Transcript:
        audio = wav_bytes(pcm16, sample_rate)
        seconds = duration_s(pcm16, sample_rate)
        errors: list[str] = []
        if (key := self.secrets.key_for("groq")) and self.quota.fits("groq-whisper", 0)[0]:
            try:
                return await self._groq(audio, seconds, key)
            except Exception as exc:
                errors.append(f"groq: {exc}")
                logger.warning("Groq STT failed, trying fallback: {}", exc)
        if key := self.secrets.key_for("mistral"):
            try:
                return await self._mistral(audio, seconds, key)
            except Exception as exc:
                errors.append(f"mistral: {exc}")
                logger.warning("Mistral STT failed: {}", exc)
        raise RuntimeError("speech-to-text unavailable: " + ("; ".join(errors) or "no Groq/Mistral API key"))

    async def _groq(self, audio: bytes, seconds: float, key: str) -> Transcript:
        started = time.monotonic()
        data = {"model": self.config.model, "response_format": "verbose_json", "temperature": "0"}
        if self.config.language:
            data["language"] = self.config.language
        if self.config.prompt:
            data["prompt"] = self.config.prompt
        resp = await self._client.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {key}"},
            data=data,
            files={"file": ("speech.wav", audio, "audio/wav")},
        )
        self.quota.on_headers("groq-whisper", resp.status_code, resp.headers)
        if resp.status_code >= 400:
            kind = (
                "rate_limit"
                if resp.status_code == 429
                else ("auth" if resp.status_code in (401, 403) else "server")
            )
            self.quota.on_failure("groq-whisper", kind, resp.text[:200])
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        latency = (time.monotonic() - started) * 1000
        self.quota.on_success("groq-whisper", 0, 0, latency)
        segments = payload.get("segments") or []
        if segments:
            kept = [
                s["text"]
                for s in segments
                if not (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -0.7)
            ]
            text = "".join(kept)
        else:
            text = payload.get("text", "")
        return Transcript(self._clean(text), payload.get("language"), seconds, latency, "groq")

    async def _mistral(self, audio: bytes, seconds: float, key: str) -> Transcript:
        started = time.monotonic()
        data = {"model": MISTRAL_STT_MODEL}
        if self.config.language:
            data["language"] = self.config.language
        resp = await self._client.post(
            MISTRAL_URL,
            headers={"Authorization": f"Bearer {key}"},
            data=data,
            files={"file": ("speech.wav", audio, "audio/wav")},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        latency = (time.monotonic() - started) * 1000
        return Transcript(
            self._clean(payload.get("text", "")), payload.get("language"), seconds, latency, "mistral"
        )

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return "" if _JUNK.match(text) else text
