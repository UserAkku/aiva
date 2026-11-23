"""The Brain: one pydantic-ai agent + routing + memory, exposed as a stream of events.

``Brain.run_turn()`` is transport-agnostic: the device session turns its events into
speech and face animations, the dashboard chat turns them into text bubbles.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    RunContext,
)
from pydantic_ai.capabilities import PrepareTools, ProcessHistory
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import RetryPromptPart, TextPart, TextPartDelta

from .deps import AgentDeps
from .events import BrainEvent, Notice, TextDelta, ToolFinished, ToolStarted, TurnFinished
from .memory import ConversationStore
from .persona import build_instructions

if TYPE_CHECKING:
    from ..services import Services

_NO_LLM = {
    "hinglish": "<embarrassed> अभी मेरे दिमाग़ से कोई AI provider connected नहीं है। Dashboard के Connectors page पे "
    "Groq की free API key add कर दो, फिर मैं पूरी तरह ready हो जाऊँगी!",
    "english": "<embarrassed> I don't have any AI provider connected yet. Add a free Groq API key on the "
    "dashboard's Connectors page and I'll be fully ready!",
}
_ALL_FAILED = {
    "hinglish": "<sad> Sorry, अभी मेरे सारे AI providers busy हैं या आज की free limit ख़त्म हो गई है। "
    "थोड़ी देर बाद फिर try करो।",
    "english": "<sad> Sorry, all my AI providers are busy or today's free limit is used up. Please try again in a bit.",
}
_BAD_KEYS = {
    "hinglish": "<embarrassed> मेरी AI API key reject हो रही है। Dashboard के Connectors page पे key check कर दो।",
    "english": "<embarrassed> My AI API keys are being rejected. Please check them on the dashboard's Connectors page.",
}
_DONE = {"hinglish": "<happy> हो गया!", "english": "<happy> Done!"}


def _leaf_errors(exc: BaseException) -> list[BaseException]:
    """Flatten (nested) exception groups, e.g. pydantic-ai's FallbackExceptionGroup."""
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for sub in exc.exceptions for leaf in _leaf_errors(sub)]
    return [exc]


def _all_auth_errors(exc: BaseException) -> bool:
    leaves = _leaf_errors(exc)
    return bool(leaves) and all(getattr(e, "status_code", None) in (401, 403) for e in leaves)


def _lang(services: Services) -> str:
    return "english" if services.config.assistant.language == "english" else "hinglish"


class Brain:
    def __init__(self, services: Services) -> None:
        self.services = services
        self.conversations = ConversationStore(services.config.llm.history_turns)
        self.agent: Agent[AgentDeps, str] | None = None
        self.rebuild()

    def rebuild(self) -> None:
        """(Re)create the agent after keys, config or connected MCP servers change."""
        services = self.services
        self.conversations.keep_turns = services.config.llm.history_turns
        if not services.router.available:
            self.agent = None
            return
        toolsets: list[Any] = [services.tools.toolset, *services.connectors.mcp_toolsets()]
        self.agent = Agent(
            deps_type=AgentDeps,
            instructions=self._instructions,
            toolsets=toolsets,
            capabilities=[
                *services.router.capabilities(),
                PrepareTools(services.tools.prepare),
                ProcessHistory(self.conversations.history_processor()),
            ],
            retries=1,
            tool_timeout=45,
        )

    def _instructions(self, ctx: RunContext[AgentDeps]) -> str:
        services = self.services
        facts = [f["text"] for f in services.db.facts(limit=15)]
        return build_instructions(services.config, facts=facts, skills=services.tools.skills_summary())

    async def run_turn(
        self, session_id: str, user_text: str, *, has_face: bool = True
    ) -> AsyncIterator[BrainEvent]:
        """Run one user turn and stream :mod:`~aiva.brain.events` as they happen."""
        services = self.services
        lang = _lang(services)
        for warning in services.quota.pop_warnings():
            yield Notice(warning.text_hi if lang == "hinglish" else warning.text_en, warning.level)

        if self.agent is None:
            yield TextDelta(_NO_LLM[lang])
            yield TurnFinished(reply_text=_NO_LLM[lang], error="no LLM provider configured")
            return

        conversation = self.conversations.get(session_id)
        queue: asyncio.Queue[BrainEvent | None] = asyncio.Queue()

        async def emit(event: BrainEvent) -> None:
            await queue.put(event)

        deps = AgentDeps(
            services=services,
            session_id=session_id,
            turn_id=secrets.token_hex(4),
            user_text=user_text,
            emit=emit,
            active_categories=services.tools.route(user_text, conversation.sticky_categories()),
            has_face=has_face,
        )
        reply_parts: list[str] = []
        state: dict[str, Any] = {}
        agent = self.agent

        async def produce() -> None:
            started = time.monotonic()
            try:
                async with agent.run_stream_events(
                    user_text, deps=deps, message_history=list(conversation.messages)
                ) as stream:
                    async for event in stream:
                        for mapped in self._map(event, reply_parts, deps):
                            await queue.put(mapped)
                        if isinstance(event, AgentRunResultEvent):
                            state["result"] = event.result
                    conversation.record(
                        stream.all_messages(), set(deps.active_categories), self.conversations.keep_turns
                    )
            except asyncio.CancelledError:
                conversation.record_interrupted(user_text, "".join(reply_parts))
                raise
            except Exception as exc:
                leaves = _leaf_errors(exc)
                if all(isinstance(e, ModelAPIError) for e in leaves):
                    logger.error("every LLM deployment failed: {}", "; ".join(str(e)[:120] for e in leaves))
                else:
                    logger.exception("brain turn failed")
                state["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                if not reply_parts:
                    message = _BAD_KEYS[lang] if _all_auth_errors(exc) else _ALL_FAILED[lang]
                    reply_parts.append(message)
                    await queue.put(TextDelta(message))
            finally:
                state["latency_ms"] = (time.monotonic() - started) * 1000
                await queue.put(None)

        task = asyncio.create_task(produce(), name=f"brain-turn-{deps.turn_id}")
        try:
            while (item := await queue.get()) is not None:
                yield item
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        if not "".join(reply_parts).strip() and deps.tools_used:
            reply_parts.append(_DONE[lang])
            yield TextDelta(_DONE[lang])

        result = state.get("result")
        response = getattr(result, "response", None)
        usage = result.usage if result is not None else None
        yield TurnFinished(
            reply_text="".join(reply_parts),
            model=getattr(response, "model_name", None),
            deployment=services.router.deployment_for(getattr(response, "model_name", None)),
            tools=list(deps.tools_used),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            error=state.get("error"),
        )

    @staticmethod
    def _map(event: Any, reply_parts: list[str], deps: AgentDeps) -> list[BrainEvent]:
        if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
            if event.part.content:
                reply_parts.append(event.part.content)
                return [TextDelta(event.part.content)]
        elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            if event.delta.content_delta:
                reply_parts.append(event.delta.content_delta)
                return [TextDelta(event.delta.content_delta)]
        elif isinstance(event, FunctionToolCallEvent):
            deps.tools_used.append(event.part.tool_name)
            args = event.part.args_as_dict() if hasattr(event.part, "args_as_dict") else {}
            return [ToolStarted(event.part.tool_name, args)]
        elif isinstance(event, FunctionToolResultEvent):
            part = event.part
            ok = not isinstance(part, RetryPromptPart)
            content = getattr(part, "content", "")
            summary = content if isinstance(content, str) else str(content)
            return [ToolFinished(getattr(part, "tool_name", "") or "", ok, summary[:300])]
        return []
