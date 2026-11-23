"""Shared fixtures: a fully wired AIVA with fake LLM / STT / TTS (no network, no keys)."""

from __future__ import annotations

import shutil
import struct
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from aiva.config import DeploymentConfig
from aiva.llm.models import GuardedModel
from aiva.services import Services
from aiva.voice.stt import Transcript

ROOT = Path(__file__).resolve().parent.parent


async def fake_llm_stream(messages: list[ModelMessage], info: AgentInfo):
    """Script: 'count …' → call count_numbers then a closing line; anything else → greeting."""
    last = messages[-1]
    if any(isinstance(p, ToolReturnPart) for p in last.parts):
        yield "<laughing> Ho gaya! "
        yield "Kaisa laga?"
        return
    user = " ".join(str(getattr(p, "content", "")) for p in last.parts).lower()
    if "count" in user and any(t.name == "count_numbers" for t in info.function_tools):
        yield {0: DeltaToolCall(name="count_numbers", json_args='{"start": 1, "end": 5}', tool_call_id="c1")}
        return
    for chunk in ["<happy> Namaste! ", "Main AIVA hoon. ", "<winking> Aapki ", "desk buddy."]:
        yield chunk


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Services]:
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "aiva.yaml", tmp_path / "config" / "aiva.yaml")
    monkeypatch.setenv("AIVA_HOME", str(tmp_path))
    for env in ("GROQ_API_KEY", "MISTRAL_API_KEY", "GEMINI_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    svc = Services.build(tmp_path)
    svc.config.workspace = str(tmp_path / "workspace")
    svc.config.voice.playback_lead_ms = 60_000  # don't pace audio in tests

    # fake LLM through the real router machinery
    dep = DeploymentConfig(id="fake", provider="groq", model="fake-model", priority=1)
    svc.quota.register(dep, has_key=True)
    svc.router.models = {"fake": GuardedModel(FunctionModel(stream_function=fake_llm_stream, model_name="fake-model"), dep, svc.quota)}
    svc.brain.rebuild()

    # fake speech services
    async def transcribe(pcm16: bytes, sample_rate: int = 16000) -> Transcript:
        return Transcript("count from one to five", "en", len(pcm16) / 32000, 5.0, "fake")

    async def tts_stream(text: str, lang: str | None = None, voice: str | None = None) -> AsyncIterator[bytes]:
        yield struct.pack("<h", 1000) * 1200  # 50 ms of a tiny tone-ish value

    monkeypatch.setattr(svc.stt, "transcribe", transcribe)
    monkeypatch.setattr(svc.tts, "stream", tts_stream)
    yield svc
    svc.db.close()
