"""Audio framing for devices: raw PCM16 (browser simulator) or Opus (ESP32 / xiaozhi firmware).

Opus needs the system library (``brew install opus``) and ``uv sync --extra hardware``;
it's only imported when an Opus device actually connects.
"""

from __future__ import annotations

from ..voice.audio import MIC_RATE, SPEAKER_RATE, resample
from .protocol import AudioParams


class DeviceCodec:
    """Decode uplink frames to 16 kHz PCM16; split/encode 24 kHz PCM16 into downlink frames."""

    def __init__(self, uplink: AudioParams, downlink_frame_ms: int = 60) -> None:
        self.uplink = uplink
        self.format = uplink.format
        self.frame_ms = downlink_frame_ms
        self.out_frame_bytes = SPEAKER_RATE * downlink_frame_ms // 1000 * 2
        self._out_pending = b""
        self._decoder = self._encoder = None
        if self.format == "opus":
            try:
                import opuslib
            except Exception as exc:  # pragma: no cover - depends on system libopus
                raise RuntimeError(
                    "This device streams Opus audio. Install it with: brew install opus && uv sync --extra hardware"
                ) from exc
            self._decoder = opuslib.Decoder(uplink.sample_rate, 1)
            self._encoder = opuslib.Encoder(SPEAKER_RATE, 1, opuslib.APPLICATION_VOIP)
            self._in_frame_samples = uplink.sample_rate * uplink.frame_duration // 1000

    def decode(self, payload: bytes) -> bytes:
        if self.format == "opus":
            pcm = self._decoder.decode(payload, self._in_frame_samples)  # type: ignore[union-attr]
        else:
            pcm = payload
        return resample(pcm, self.uplink.sample_rate, MIC_RATE)

    def frames(self, pcm24k: bytes, final: bool = False) -> list[bytes]:
        """Split into fixed-size downlink frames (encoding to Opus if needed)."""
        data = self._out_pending + pcm24k
        size = self.out_frame_bytes
        cut = len(data) - len(data) % size
        chunks = [data[i : i + size] for i in range(0, cut, size)]
        self._out_pending = data[cut:]
        if final and self._out_pending:
            chunks.append(self._out_pending.ljust(size, b"\x00"))
            self._out_pending = b""
        if self.format == "opus":
            samples = size // 2
            return [self._encoder.encode(chunk, samples) for chunk in chunks]  # type: ignore[union-attr]
        return chunks

    def reset_output(self) -> None:
        self._out_pending = b""
