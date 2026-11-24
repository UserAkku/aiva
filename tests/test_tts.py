"""TTS engine chain: Sarvam request shape, emotion-aware delivery, fallback on failure."""

from __future__ import annotations

import json

import httpx
import pytest

from aiva.config import Secrets, TTSConfig
from aiva.voice.tts import SARVAM_PROSODY, TTSService


def make_service(handler, engine: str = "auto") -> TTSService:
    tts = TTSService(TTSConfig(engine=engine), "hinglish", Secrets(sarvam_api_key="sk_test_123"))
    tts._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return tts


async def test_sarvam_request_carries_voice_language_and_emotion() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["api-subscription-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"\x01\x00" * 2400)  # 100 ms of raw PCM16

    tts = make_service(handler)
    assert tts.engines()[0] == "sarvam"
    pcm = await tts.synthesize("अरे वाह, ये तो कमाल है!", emotion="laughing")

    assert len(pcm) == 4800 and tts.last_engine == "sarvam"
    assert seen["url"].endswith("/text-to-speech/stream") and seen["key"] == "sk_test_123"
    body = seen["body"]
    assert body["language_code"] == "hi-IN"
    assert body["model"] == "bulbul:v4-flash" and body["speaker"] == "ishita_enhi_companion"
    assert body["output_audio_codec"] == "linear16" and body["speech_sample_rate"] == 24000
    pace, pitch, loudness, temperature = SARVAM_PROSODY["laughing"]
    assert (body["pace"], body["pitch"], body["loudness"], body["temperature"]) == (
        pace,
        pitch,
        loudness,
        temperature,
    )


async def test_english_text_uses_en_in_and_odd_byte_chunks_stay_aligned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["language_code"] == "en-IN"
        return httpx.Response(200, content=b"\x02\x00" * 1001)

    tts = make_service(handler)
    tts.language = "english"
    pcm = await tts.synthesize("Hello there, nice to meet you!")
    assert len(pcm) % 2 == 0 and len(pcm) == 2002


async def test_sarvam_failure_falls_back_to_next_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "invalid key"}})

    tts = make_service(handler, engine="sarvam")

    async def fake_edge(text: str, voice: str, mood: str):
        yield b"\x03\x00" * 100

    monkeypatch.setattr(tts, "_edge", fake_edge)
    pcm = await tts.synthesize("नमस्ते")
    assert pcm == b"\x03\x00" * 100 and tts.last_engine == "edge"
    await tts.synthesize("नमस्ते दोबारा")  # second failure opens the breaker
    assert "sarvam" not in tts.engines()


def test_auto_without_key_starts_with_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    tts = TTSService(TTSConfig(engine="auto"), "hinglish", Secrets(_env_file=None))
    assert tts.engines() == ["edge", "say"]
