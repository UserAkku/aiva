"""Silero VAD (ONNX, no torch) + a streaming segmenter that finds where each utterance ends.

The model file (MIT, snakers4/silero-vad) ships in ``aiva/assets/silero_vad.onnx``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import onnxruntime as ort

from .audio import MIC_RATE, pcm16_to_float

MODEL_PATH = Path(__file__).resolve().parent.parent / "assets" / "silero_vad.onnx"
FRAME_SAMPLES = 512  # 32 ms at 16 kHz (fixed by the model)
FRAME_BYTES = FRAME_SAMPLES * 2
_CONTEXT = 64


@lru_cache(maxsize=1)
def _session() -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    opts.log_severity_level = 3
    return ort.InferenceSession(str(MODEL_PATH), sess_options=opts, providers=["CPUExecutionProvider"])


class SileroVAD:
    """Stateful speech-probability model for 16 kHz audio, 512 samples per call."""

    def __init__(self) -> None:
        self.session = _session()
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, _CONTEXT), dtype=np.float32)

    def __call__(self, frame: np.ndarray) -> float:
        x = np.concatenate([self._context, frame.reshape(1, -1).astype(np.float32)], axis=1)
        out, self._state = self.session.run(
            None, {"input": x, "state": self._state, "sr": np.array(MIC_RATE, dtype=np.int64)}
        )
        self._context = x[:, -_CONTEXT:]
        return float(out[0][0])


@dataclass(slots=True)
class VADEvent:
    kind: Literal["start", "end"]
    audio: bytes = b""
    probability: float = 0.0


class VADSegmenter:
    """Feed arbitrary-sized 16 kHz PCM16 chunks; get ``start`` / ``end(audio)`` events.

    Hysteresis: speech starts after ``min_speech_ms`` above ``threshold`` and ends after
    ``end_silence_ms`` below ``threshold - 0.15``. ``pre_roll_ms`` of audio before the
    start is kept so the first syllable is never clipped.
    """

    def __init__(
        self,
        threshold: float = 0.55,
        min_speech_ms: int = 250,
        end_silence_ms: int = 650,
        pre_roll_ms: int = 300,
        max_utterance_s: float = 25.0,
    ) -> None:
        self.vad = SileroVAD()
        self.threshold = threshold
        self.neg_threshold = max(0.05, threshold - 0.15)
        frame_ms = FRAME_SAMPLES * 1000 / MIC_RATE
        self.min_speech_frames = max(1, int(min_speech_ms / frame_ms))
        self.end_silence_frames = max(1, int(end_silence_ms / frame_ms))
        self.max_frames = int(max_utterance_s * 1000 / frame_ms)
        self._pre_roll: deque[bytes] = deque(maxlen=max(1, int(pre_roll_ms / frame_ms)))
        self.reset()

    def reset(self) -> None:
        self.vad.reset()
        self._pending = b""
        self._pre_roll.clear()
        self._candidate: list[bytes] = []
        self._speech: list[bytes] = []
        self._silence_run = 0
        self.in_speech = False
        self.last_probability = 0.0

    def feed(self, pcm: bytes) -> list[VADEvent]:
        self._pending += pcm
        events: list[VADEvent] = []
        while len(self._pending) >= FRAME_BYTES:
            frame, self._pending = self._pending[:FRAME_BYTES], self._pending[FRAME_BYTES:]
            prob = self.vad(pcm16_to_float(frame))
            self.last_probability = prob
            event = self._step(frame, prob)
            if event:
                events.append(event)
        return events

    def _step(self, frame: bytes, prob: float) -> VADEvent | None:
        if not self.in_speech:
            if prob >= self.threshold:
                self._candidate.append(frame)
                if len(self._candidate) >= self.min_speech_frames:
                    self.in_speech = True
                    self._speech = [*self._pre_roll, *self._candidate]
                    self._candidate, self._silence_run = [], 0
                    self._pre_roll.clear()
                    return VADEvent("start", probability=prob)
            else:
                if self._candidate and prob < self.neg_threshold:
                    self._pre_roll.extend(self._candidate)
                    self._candidate = []
                elif self._candidate:
                    self._candidate.append(frame)
                    return None
                self._pre_roll.append(frame)
            return None

        self._speech.append(frame)
        self._silence_run = self._silence_run + 1 if prob < self.neg_threshold else 0
        if self._silence_run >= self.end_silence_frames or len(self._speech) >= self.max_frames:
            keep_tail = max(0, self._silence_run - 6)  # keep ~200 ms of trailing silence
            audio = b"".join(self._speech[: len(self._speech) - keep_tail] if keep_tail else self._speech)
            self.in_speech = False
            self._speech, self._silence_run = [], 0
            self.vad.reset()
            return VADEvent("end", audio=audio, probability=prob)
        return None

    def force_end(self) -> VADEvent | None:
        """Close an utterance in progress (manual 'stop listening')."""
        if not self.in_speech and not self._candidate:
            return None
        audio = b"".join(self._speech or self._candidate)
        self.reset()
        return VADEvent("end", audio=audio)
