"""Always-on core skills: time, maths, memory, face, counting, web search, quota."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime
from typing import Literal

from pydantic_ai import RunContext
from simpleeval import EvalWithCompoundTypes

from ..brain.deps import AgentDeps
from ..brain.events import FaceEvent, SpeakDirect
from ..brain.toolsets import ToolRegistry
from ..emotions import Emotion, parse_emotion
from ..llm.catalog import PROVIDERS

FaceAnimation = Literal[
    "dance", "wink", "blink", "look_around", "nod", "shake_head", "laugh", "love", "sleep", "wake_up", "dizzy"
]

_MATH_FUNCS = {
    name: getattr(math, name)
    for name in (
        "sqrt",
        "sin",
        "cos",
        "tan",
        "log",
        "log10",
        "log2",
        "exp",
        "floor",
        "ceil",
        "factorial",
        "radians",
        "degrees",
        "gcd",
    )
}
_MATH_FUNCS.update(abs=abs, round=round, min=min, max=max, pow=pow)
_MATH_NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau}


def register(reg: ToolRegistry) -> None:
    @reg.tool("core")
    def get_datetime() -> str:
        """Current local date, day and time."""
        now = datetime.now().astimezone()
        return now.strftime("%A, %d %B %Y, %I:%M %p ") + (now.tzname() or "")

    @reg.tool("core")
    def calculate(expression: str) -> str:
        """Evaluate a maths expression exactly, e.g. '23*47', 'sqrt(144)+2**10', '15/100*2400'.

        Args:
            expression: Python-style arithmetic using + - * / ** % and functions like sqrt, sin, log, factorial.
        """
        evaluator = EvalWithCompoundTypes(functions=_MATH_FUNCS, names=_MATH_NAMES)
        try:
            value = evaluator.eval(expression.replace("^", "**").replace("×", "*").replace("÷", "/"))
        except Exception as exc:
            return f"Could not evaluate: {exc}"
        if isinstance(value, float):
            value = round(value, 6)
            if value.is_integer():
                value = int(value)
        return f"{expression} = {value}"

    @reg.tool("core")
    def remember_fact(ctx: RunContext[AgentDeps], fact: str) -> str:
        """Save a lasting fact about the user or their world (name, likes, important people, plans).

        Args:
            fact: One short self-contained sentence, e.g. "User's name is Riya; she studies B.Tech CSE".
        """
        ctx.deps.services.db.add_fact(fact)
        return "Saved to long-term memory."

    @reg.tool("core")
    def forget_fact(ctx: RunContext[AgentDeps], about: str) -> str:
        """Forget saved facts containing a word or phrase.

        Args:
            about: Word or phrase to match in saved facts.
        """
        removed = ctx.deps.services.db.forget_facts_matching(about)
        return f"Forgot {removed} fact(s)." if removed else "Nothing matched."

    @reg.tool("core")
    async def count_numbers(
        ctx: RunContext[AgentDeps],
        start: int,
        end: int,
        step: int = 1,
        language: Literal["english", "hindi"] = "english",
    ) -> str:
        """Count aloud from start to end (also backwards or by steps). Speaks directly; do not repeat the numbers.

        Args:
            start: First number.
            end: Last number (inclusive).
            step: Step size (sign is fixed automatically).
            language: Say the numbers in English or Hindi.
        """
        step = abs(step) or 1
        step = step if end >= start else -step
        numbers = list(range(start, end + (1 if step > 0 else -1), step))
        if len(numbers) > 1000:
            return "That's more than 1000 numbers; ask the user for a smaller range."
        lang = "hi" if language == "hindi" else "en"
        chunk = 10 if len(numbers) <= 30 else 20
        for i in range(0, len(numbers), chunk):
            part = ", ".join(str(n) for n in numbers[i : i + chunk])
            await ctx.deps.emit(SpeakDirect(part + ("." if i + chunk >= len(numbers) else ","), lang=lang))
        return f"Counted aloud from {start} to {end} ({len(numbers)} numbers). Now add just one short, fun closing line."

    @reg.tool("core")
    async def set_face(
        ctx: RunContext[AgentDeps], emotion: str = "", animation: FaceAnimation | None = None
    ) -> str:
        """Change your OLED face: show an emotion and/or play an animation (dance, wink, laugh, sleep…).

        Args:
            emotion: One of your emotion names, e.g. happy, angry, loving, cool, sleepy.
            animation: Optional face animation to play.
        """
        parsed = parse_emotion(emotion) if emotion else None
        if parsed is None and animation is None:
            return f"Unknown emotion. Use one of: {', '.join(e.value for e in Emotion)}"
        await ctx.deps.emit(FaceEvent(emotion=parsed, animation=animation))
        return "Face updated." if ctx.deps.has_face else "This device has no face screen."

    @reg.tool("core")
    def load_skills(ctx: RunContext[AgentDeps], skills: list[str]) -> str:
        """Switch on more skill groups for this conversation so their tools become available.

        Args:
            skills: Skill names, e.g. ["gmail"], ["pdf", "files"].
        """
        known = ctx.deps.services.tools.categories
        loaded = [s for s in skills if s in known]
        ctx.deps.active_categories.update(loaded)
        unknown = [s for s in skills if s not in known]
        msg = f"Loaded: {', '.join(loaded)}." if loaded else "Nothing loaded."
        return msg + (f" Unknown: {', '.join(unknown)}." if unknown else "") + " Use the new tools now."

    @reg.tool("core")
    def get_quota_status(ctx: RunContext[AgentDeps]) -> str:
        """How much free AI quota is left today on each provider."""
        rows = []
        for row in ctx.deps.services.quota.snapshot():
            if not row["has_key"]:
                continue
            frac = row["daily_fraction"]
            left = f"{round(frac * 100)}% of today's quota left" if frac is not None else "plenty left"
            if row["status"] == "cooldown":
                left += f", resting for {int(row['cooldown_s'])}s"
            rows.append(f"{PROVIDERS[row['provider']].label} {row['model']}: {left}")
        return "; ".join(rows) or "No providers configured."

    @reg.tool("core")
    async def web_search(query: str, max_results: int = 4) -> str:
        """Search the web (DuckDuckGo) for fresh facts, prices, scores, people, events.

        Args:
            query: Search query in English works best.
            max_results: 1 to 8.
        """
        from ddgs import DDGS

        def run() -> list[dict]:
            return list(DDGS().text(query, max_results=max(1, min(max_results, 8))))

        try:
            results = await asyncio.wait_for(asyncio.to_thread(run), timeout=12)
        except Exception as exc:
            return f"Search failed: {exc}"
        if not results:
            return "No results."
        return "\n".join(f"- {r.get('title')}: {r.get('body')} ({r.get('href')})" for r in results)
