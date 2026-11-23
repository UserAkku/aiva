"""Device layer: the xiaozhi-compatible WebSocket gateway and per-device voice sessions.

Any "body" for AIVA — the browser simulator now, an ESP32-S3 running the
xiaozhi-esp32 firmware later — connects to ``/xiaozhi/v1/`` and speaks the same
protocol (see docs/PROTOCOL.md). Swapping the laptop for the hardware therefore
needs no server changes.
"""

from .registry import DeviceRegistry
from .session import DeviceSession

__all__ = ["DeviceRegistry", "DeviceSession"]
