"""In-process event bus.

Everything interesting (a turn starting, a tool call, a quota warning, a device
connecting…) is published here. The dashboard subscribes over a WebSocket and the
Activity page renders the recent history, so the whole system is observable live.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from loguru import logger


class EventBus:
    def __init__(self, history: int = 400, queue_size: int = 256) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._queue_size = queue_size

    def publish(self, type_: str, **data: Any) -> dict[str, Any]:
        """Fire-and-forget publish; never blocks the caller (slow subscribers drop old events)."""
        event = {"type": type_, "ts": time.time(), **data}
        self._history.append(event)
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - race
                    pass
            queue.put_nowait(event)
        return event

    def recent(self, limit: int = 200, types: set[str] | None = None) -> list[dict[str, Any]]:
        items = [e for e in self._history if types is None or e["type"] in types]
        return items[-limit:]

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        logger.debug("event subscriber added ({} total)", len(self._subscribers))
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
