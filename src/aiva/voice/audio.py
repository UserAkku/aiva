"""PCM helpers. Internally audio is mono signed 16-bit little-endian PCM."""

from __future__ import annotations

import io
import wave

import numpy as np
import soxr

MIC_RATE = 16000  # what VAD + STT expect
SPEAKER_RATE = 24000  # what TTS produces and devices play (xiaozhi downlink default)


def pcm16_to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def resample(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not pcm:
        return pcm
    return float_to_pcm16(soxr.resample(pcm16_to_float(pcm), src_rate, dst_rate, quality="HQ"))


def wav_bytes(pcm: bytes, rate: int = MIC_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def read_wav(data: bytes) -> tuple[bytes, int]:
    """Return (mono pcm16, sample_rate) from WAV bytes."""
    with wave.open(io.BytesIO(data), "rb") as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("only 16-bit WAV is supported")
    if channels > 1:
        samples = np.frombuffer(frames, dtype="<i2").reshape(-1, channels).mean(axis=1)
        frames = samples.astype("<i2").tobytes()
    return frames, rate


def duration_s(pcm: bytes, rate: int) -> float:
    return len(pcm) / 2 / rate


def peak_level(pcm: bytes) -> float:
    """0..1 peak amplitude (used to reject near-silent 'utterances')."""
    if not pcm:
        return 0.0
    return float(np.abs(np.frombuffer(pcm, dtype="<i2")).max()) / 32768.0


def silence(ms: int, rate: int = SPEAKER_RATE) -> bytes:
    return b"\x00\x00" * int(rate * ms / 1000)
