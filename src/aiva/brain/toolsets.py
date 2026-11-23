"""Tool registry with *skill categories* and per-turn tool routing.

Free tiers allow ~8K tokens/minute on Groq, and every tool schema costs tokens on
every request. So the model never sees all ~45 tools at once: each turn it gets the
always-on core skills, plus categories whose keywords appear in what the user
said, plus categories used in the last couple of turns (follow-ups like "haan,
bhej do"), plus anything it asks for with ``load_skills``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset

from .deps import AgentDeps


@dataclass
class Category:
    name: str
    description: str
    keywords: tuple[str, ...] = ()
    always: bool = False
    tools: list[str] = field(default_factory=list)

    def matches(self, text: str) -> bool:
        return any(_keyword_in(k, text) for k in self.keywords)


def _keyword_in(keyword: str, text: str) -> bool:
    if not keyword.isascii():
        return keyword in text  # Devanagari etc.: plain substring
    return re.search(rf"(?<![a-z]){re.escape(keyword)}", text) is not None


class ToolRegistry:
    def __init__(self) -> None:
        self.toolset: FunctionToolset[AgentDeps] = FunctionToolset(id="aiva")
        self.categories: dict[str, Category] = {}
        self.disabled: set[str] = set()
        self.confirm_tools: set[str] = set()
        #: extra toolsets (MCP servers) keyed by toolset id → category name
        self.external_categories: dict[str, str] = {}

    # ── registration ─────────────────────────────────────────────────────────
    def category(
        self, name: str, description: str, keywords: tuple[str, ...] = (), always: bool = False
    ) -> None:
        self.categories[name] = Category(name, description, tuple(k.lower() for k in keywords), always)

    def tool(self, category: str, *, name: str | None = None, confirm: bool = False) -> Callable[[Any], Any]:
        """Decorator: register a tool function under a category (docstring = description)."""

        def decorator(func: Any) -> Any:
            tool_name = name or func.__name__
            self.toolset.add_function(
                func,
                name=tool_name,
                metadata={"category": category},
                docstring_format="google",
                require_parameter_descriptions=False,
            )
            self.categories[category].tools.append(tool_name)
            if confirm:
                self.confirm_tools.add(tool_name)
            return func

        return decorator

    def register_external(
        self, toolset_id: str, category: str, description: str, keywords: tuple[str, ...]
    ) -> None:
        self.category(category, description, keywords)
        self.external_categories[toolset_id] = category

    def unregister_external(self, toolset_id: str) -> None:
        category = self.external_categories.pop(toolset_id, None)
        if category:
            self.categories.pop(category, None)

    # ── routing ──────────────────────────────────────────────────────────────
    def route(self, text: str, sticky: set[str] | None = None) -> set[str]:
        lowered = text.lower()
        active = {c.name for c in self.categories.values() if c.always or c.matches(lowered)}
        return active | (sticky or set())

    def skills_summary(self) -> str:
        return ", ".join(f"{c.name} ({c.description})" for c in self.categories.values() if not c.always)

    def category_of(self, tool_def: ToolDefinition) -> str | None:
        meta = tool_def.metadata or {}
        if "category" in meta:
            return meta["category"]
        if tool_def.toolset_id and tool_def.toolset_id in self.external_categories:
            return self.external_categories[tool_def.toolset_id]
        return None

    async def prepare(
        self, ctx: RunContext[AgentDeps], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        """``PrepareTools`` hook: only expose the tools of the active categories."""
        active = ctx.deps.active_categories
        return [
            td
            for td in tool_defs
            if td.name not in self.disabled
            and (self.category_of(td) in active or self.category_of(td) is None)
        ]

    def catalog(self) -> list[dict[str, Any]]:
        """Everything for the dashboard Tools page."""
        out = []
        for cat in self.categories.values():
            out.append(
                {
                    "name": cat.name,
                    "description": cat.description,
                    "always": cat.always,
                    "keywords": list(cat.keywords[:12]),
                    "tools": [
                        {
                            "name": t,
                            "enabled": t not in self.disabled,
                            "confirm": t in self.confirm_tools,
                            "description": self._description(t),
                        }
                        for t in cat.tools
                    ],
                }
            )
        return out

    def _description(self, tool_name: str) -> str:
        tool = self.toolset.tools.get(tool_name)
        if tool is None:
            return ""
        return (tool.description or "").split("\n")[0]
