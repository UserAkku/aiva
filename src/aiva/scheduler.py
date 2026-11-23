"""Timers and reminders that survive restarts (stored in SQLite).

When one is due the scheduler calls ``on_due`` — wired to make every connected
device speak it (or, with no device online, to post a macOS notification).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from loguru import logger

from .events import EventBus
from .storage import Database

DueCallback = Callable[[dict[str, Any]], Awaitable[None]]


class Scheduler:
    def __init__(self, db: Database, bus: EventBus) -> None:
        self.db = db
        self.bus = bus
        self.on_due: DueCallback | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="scheduler")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def add(self, text: str, due_at: float, kind: str = "reminder") -> int:
        reminder_id = self.db.add_reminder(text, due_at, kind)
        self.bus.publish("reminder.added", id=reminder_id, text=text, due_at=due_at, kind=kind)
        self._wake.set()
        return reminder_id

    def cancel(self, reminder_id: int) -> bool:
        ok = self.db.cancel_reminder(reminder_id)
        self._wake.set()
        return ok

    def pending(self) -> list[dict[str, Any]]:
        return self.db.pending_reminders()

    async def _loop(self) -> None:
        while True:
            self._wake.clear()
            now = time.time()
            pending = self.db.pending_reminders()
            for item in [r for r in pending if r["due_at"] <= now]:
                self.db.mark_reminder_fired(item["id"])
                self.bus.publish("reminder.due", **item)
                if self.on_due:
                    try:
                        await self.on_due(item)
                    except Exception:
                        logger.exception("reminder callback failed")
            upcoming = [r["due_at"] for r in self.db.pending_reminders()]
            wait = min(upcoming) - time.time() if upcoming else 3600.0
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=max(0.2, min(wait, 3600.0)))
