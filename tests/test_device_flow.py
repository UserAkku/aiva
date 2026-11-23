"""End-to-end: a simulated device talks to AIVA over the xiaozhi WebSocket protocol."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiva.app import create_app
from aiva.services import Services
from aiva.voice.audio import read_wav, resample

HELLO = {
    "type": "hello",
    "version": 1,
    "transport": "websocket",
    "features": {"aiva": True, "aec": True},
    "audio_params": {"format": "pcm16", "sample_rate": 16000, "channels": 1, "frame_duration": 20},
}


def collect_until_tts_stop(ws, limit: int = 400) -> tuple[list[dict], int]:
    """Read messages until the final ``tts stop``; returns (json messages, number of audio frames)."""
    messages, frames = [], 0
    for _ in range(limit):
        msg = ws.receive()
        if msg.get("bytes") is not None:
            frames += 1
            continue
        data = json.loads(msg["text"])
        messages.append(data)
        if data.get("type") == "tts" and data.get("state") == "stop":
            break
    return messages, frames


def test_text_turn_with_tool_and_emotions(services: Services) -> None:
    client = TestClient(create_app(services))
    with client.websocket_connect("/xiaozhi/v1/?device-id=test-sim") as ws:
        ws.send_text(json.dumps(HELLO))
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello" and hello["audio_params"]["format"] == "pcm16"

        ws.send_text(json.dumps({"type": "chat", "text": "please count to five"}))
        messages, frames = collect_until_tts_stop(ws)

    kinds = [(m["type"], m.get("state") or m.get("kind") or m.get("emotion")) for m in messages]
    assert ("llm", "thinking") in kinds
    assert ("aiva", "tool") in kinds
    sentences = [m["text"] for m in messages if m["type"] == "tts" and m.get("state") == "sentence_start"]
    assert sentences[0].startswith("1, 2, 3, 4, 5")  # spoken directly by the tool, not the LLM
    assert any("Ho gaya" in s for s in sentences)
    assert ("llm", "laughing") in kinds  # emotion tag became a face change
    assert all("<" not in s for s in sentences)  # tags are never spoken
    assert frames >= len(sentences)


def test_emotion_changes_follow_sentence_order(services: Services) -> None:
    client = TestClient(create_app(services))
    with client.websocket_connect("/xiaozhi/v1/?device-id=test-sim") as ws:
        ws.send_text(json.dumps(HELLO))
        ws.receive_text()
        ws.send_text(json.dumps({"type": "chat", "text": "hello"}))
        messages, _ = collect_until_tts_stop(ws)
    order = [
        m.get("emotion") or m.get("text")
        for m in messages
        if (m["type"] == "llm" and m["emotion"] != "thinking") or m.get("state") == "sentence_start"
    ]
    assert order.index("happy") < order.index("Namaste!")
    assert order.index("winking") > order.index("Main AIVA hoon.")
    assert order.index("winking") < order.index("Aapki desk buddy.")


@pytest.mark.skipif(
    subprocess.run(["which", "say"], capture_output=True).returncode != 0, reason="needs macOS say"
)
def test_voice_turn_detected_by_vad(services: Services) -> None:
    """Real speech audio (macOS say) → Silero VAD → (fake) STT → reply."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        subprocess.run(
            ["say", "-o", str(wav), "--data-format=LEI16@16000", "Hey AIVA, please count from one to five"],
            check=True,
        )
        pcm, rate = read_wav(wav.read_bytes())
    pcm = resample(pcm, rate, 16000) + b"\x00\x00" * 16000  # + 1 s of silence to end the turn

    client = TestClient(create_app(services))
    with client.websocket_connect("/xiaozhi/v1/?device-id=test-sim") as ws:
        ws.send_text(json.dumps(HELLO))
        ws.receive_text()
        ws.send_text(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
        for i in range(0, len(pcm), 640):  # 20 ms frames
            ws.send_bytes(pcm[i : i + 640])
        messages, frames = collect_until_tts_stop(ws)

    vad = [m for m in messages if m.get("kind") == "vad"]
    assert vad and vad[0]["speaking"] is True
    assert any(m["type"] == "stt" and "count" in m["text"] for m in messages)
    assert frames > 0
