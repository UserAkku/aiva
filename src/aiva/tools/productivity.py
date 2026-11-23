"""Productivity skills: timers, reminders, notes and a to-do list."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from pydantic_ai import RunContext

from ..brain.deps import AgentDeps
from ..brain.toolsets import ToolRegistry


def _when(ts: float) -> str:
    dt = datetime.fromtimestamp(ts).astimezone()
    today = datetime.now().astimezone().date()
    day = (
        "today"
        if dt.date() == today
        else ("tomorrow" if dt.date() == today + timedelta(days=1) else dt.strftime("%d %b"))
    )
    return f"{day} at {dt:%I:%M %p}"


def _parse_time(at: str) -> float | None:
    """Accept ISO datetimes ('2026-11-24T17:30') or clock times ('17:30', '5:30 pm')."""
    text = at.strip().lower().replace(".", "")
    now = datetime.now().astimezone()
    try:
        dt = datetime.fromisoformat(text)
        return (dt if dt.tzinfo else dt.astimezone()).timestamp()
    except ValueError:
        pass
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            t = datetime.strptime(text, fmt).time()
        except ValueError:
            continue
        dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        return dt.timestamp()
    return None


def register(reg: ToolRegistry) -> None:
    @reg.tool("productivity")
    def set_timer(ctx: RunContext[AgentDeps], minutes: float = 0, seconds: int = 0, label: str = "") -> str:
        """Start a countdown timer; AIVA announces when it ends.

        Args:
            minutes: Minutes (may be fractional).
            seconds: Extra seconds.
            label: What it's for, e.g. "tea", "study break".
        """
        total = minutes * 60 + seconds
        if total <= 0:
            return "Timer length must be positive."
        due = time.time() + total
        rid = ctx.deps.services.scheduler.add(label or "timer", due, kind="timer")
        return f"Timer #{rid} set for {int(total // 60)} min {int(total % 60)} s (ends {_when(due)})."

    @reg.tool("productivity")
    def set_reminder(ctx: RunContext[AgentDeps], text: str, at: str = "", in_minutes: float = 0) -> str:
        """Remind the user about something at a time, or after some minutes.

        Args:
            text: What to remind about.
            at: Local time: ISO like "2026-11-24T17:30" or clock time like "17:30" / "5:30 pm".
            in_minutes: Alternatively, minutes from now.
        """
        if in_minutes > 0:
            due = time.time() + in_minutes * 60
        elif at:
            parsed = _parse_time(at)
            if parsed is None:
                return f"Couldn't understand the time '{at}'. Use HH:MM or an ISO datetime."
            due = parsed
        else:
            return "Need a time (at) or in_minutes."
        rid = ctx.deps.services.scheduler.add(text, due, kind="reminder")
        return f"Reminder #{rid} set for {_when(due)}: {text}"

    @reg.tool("productivity")
    def list_reminders(ctx: RunContext[AgentDeps]) -> str:
        """List running timers and upcoming reminders."""
        items = ctx.deps.services.scheduler.pending()
        if not items:
            return "No timers or reminders."
        return "\n".join(f"#{r['id']} {r['kind']} '{r['text']}' {_when(r['due_at'])}" for r in items)

    @reg.tool("productivity")
    def cancel_reminder(ctx: RunContext[AgentDeps], reminder_id: int) -> str:
        """Cancel a timer or reminder by its number.

        Args:
            reminder_id: The # number from list_reminders.
        """
        return "Cancelled." if ctx.deps.services.scheduler.cancel(reminder_id) else "No such pending item."

    @reg.tool("productivity")
    def add_note(ctx: RunContext[AgentDeps], text: str) -> str:
        """Save a quick note.

        Args:
            text: The note.
        """
        return f"Note #{ctx.deps.services.db.add_note(text)} saved."

    @reg.tool("productivity")
    def list_notes(ctx: RunContext[AgentDeps], limit: int = 5) -> str:
        """Read back the latest notes.

        Args:
            limit: How many.
        """
        notes = ctx.deps.services.db.notes(limit=max(1, min(limit, 20)))
        return "\n".join(f"#{n['id']}: {n['text']}" for n in notes) or "No notes yet."

    @reg.tool("productivity")
    def add_todo(ctx: RunContext[AgentDeps], task: str) -> str:
        """Add a task to the to-do list.

        Args:
            task: The task.
        """
        return f"Added to-do #{ctx.deps.services.db.add_todo(task)}."

    @reg.tool("productivity")
    def list_todos(ctx: RunContext[AgentDeps]) -> str:
        """Read the open to-do list."""
        todos = ctx.deps.services.db.todos()
        return "\n".join(f"#{t['id']}: {t['text']}" for t in todos) or "The to-do list is empty."

    @reg.tool("productivity")
    def complete_todo(ctx: RunContext[AgentDeps], todo: str) -> str:
        """Mark a to-do as done, by its number or by words from it.

        Args:
            todo: "#3", "3" or part of the task text.
        """
        db = ctx.deps.services.db
        key = todo.strip().lstrip("#")
        if key.isdigit():
            return "Marked done." if db.complete_todo(int(key)) else "No such to-do."
        for t in db.todos():
            if key.lower() in t["text"].lower():
                db.complete_todo(t["id"])
                return f"Marked '{t['text']}' done."
        return "No matching to-do."
