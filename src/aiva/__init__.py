"""AIVA — a voice-first AI desk companion.

The brain (this package) runs on the Mac; the body is any device that speaks the
xiaozhi-compatible WebSocket protocol: the browser simulator today, an ESP32-S3
with a mic, a speaker and an OLED face tomorrow.
"""

import os

# Keep third-party startup banners out of the logs.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

__version__ = "0.1.0"
