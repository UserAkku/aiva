"""Run-time dependencies handed to every tool call (``RunContext[AgentDeps]``)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .events import BrainEvent

if TYPE_CHECKING:
    from ..services import Services


@dataclass
class AgentDeps:
    services: Services
    session_id: str
    turn_id: str
    user_text: str
    emit: Callable[[BrainEvent], Awaitable[None]]
    #: skill categories switched on for this turn (keyword match + ``load_skills``)
    active_categories: set[str] = field(default_factory=set)
    #: the device has a face we can animate
    has_face: bool = True
    #: tools called so far in this turn
    tools_used: list[str] = field(default_factory=list)
