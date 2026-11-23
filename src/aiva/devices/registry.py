"""Tracks connected devices; broadcasts announcements (timers/reminders) to them."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from .session import DeviceSession


def _log_failure(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.warning("announcement failed: {}", task.exception())


class DeviceRegistry:
    def __init__(self) -> None:
        self.sessions: dict[str, DeviceSession] = {}

    def add(self, session: DeviceSession) -> None:
        self.sessions[session.id] = session

    def remove(self, session: DeviceSession) -> None:
        self.sessions.pop(session.id, None)

    def __len__(self) -> int:
        return len(self.sessions)

    async def announce(self, text: str) -> int:
        """Make every connected device say ``text``; returns how many devices were reached."""
        sessions = list(self.sessions.values())
        for session in sessions:
            asyncio.create_task(session.announce(text)).add_done_callback(_log_failure)
        return len(sessions)

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "session": s.id,
                "device_id": s.device_id,
                "kind": s.kind,
                "state": s.state,
                "listen_mode": s.listen_mode,
                "audio": s.hello.audio.format,
                "aec": s.hello.has_aec,
                "connected_at": s.connected_at,
                "turns": s.turns,
                "last_user_text": s.last_user_text,
                "last_reply": s.last_reply,
            }
            for s in self.sessions.values()
        ]
