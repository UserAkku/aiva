"""MCP connector manager — plug any Model Context Protocol server into AIVA.

Config is stored in ``data/connectors/mcp.json`` in the same shape as Claude
Desktop / Cursor configs, so existing snippets can be pasted as-is::

    {"mcpServers": {
        "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]},
        "docs":       {"url": "https://example.com/mcp"}
    }}

Each enabled server becomes a pydantic-ai ``MCPToolset`` and a skill category
``mcp_<name>`` whose keywords trigger it (or the model can ``load_skills`` it).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger
from pydantic_ai.mcp import MCPToolset, StdioTransport

from ..brain.toolsets import ToolRegistry
from .store import JsonStore

#: Ready-made servers offered in the dashboard (one click to add).
PRESETS: dict[str, dict[str, Any]] = {
    "playwright": {
        "description": "Control a real browser: open pages, click, type, fill forms (Microsoft Playwright MCP).",
        "config": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
        "keywords": ["browser", "website", "click", "fill", "form", "login", "book", "automate", "page"],
    },
    "fetch": {
        "description": "Fetch any URL and convert it to markdown (official MCP reference server).",
        "config": {"command": "uvx", "args": ["mcp-server-fetch"]},
        "keywords": ["fetch", "url", "page", "website", "read"],
    },
    "memory": {
        "description": "Knowledge-graph memory (official MCP reference server).",
        "config": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]},
        "keywords": ["remember", "memory", "knowledge"],
    },
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "server"


class MCPManager:
    def __init__(self, store: JsonStore, registry: ToolRegistry) -> None:
        self.store = store
        self.registry = registry
        self.toolsets: dict[str, MCPToolset] = {}
        self.errors: dict[str, str] = {}
        self.tool_names: dict[str, list[str]] = {}

    # ── config ───────────────────────────────────────────────────────────────
    def config(self) -> dict[str, Any]:
        return self.store.load("mcp", {"mcpServers": {}}) or {"mcpServers": {}}

    def servers(self) -> dict[str, dict[str, Any]]:
        return dict(self.config().get("mcpServers", {}))

    def save_server(self, name: str, server: dict[str, Any]) -> str:
        if not (server.get("command") or server.get("url")):
            raise ValueError("an MCP server needs either 'command' (stdio) or 'url' (HTTP)")
        name = _slug(name)
        cfg = self.config()
        cfg.setdefault("mcpServers", {})[name] = server
        self.store.save("mcp", cfg)
        return name

    def remove_server(self, name: str) -> None:
        cfg = self.config()
        cfg.get("mcpServers", {}).pop(name, None)
        self.store.save("mcp", cfg)
        self.toolsets.pop(name, None)
        self.registry.unregister_external(f"mcp:{name}")

    # ── runtime ──────────────────────────────────────────────────────────────
    def build(self) -> None:
        """Create toolsets for all enabled servers (connections open lazily on first use)."""
        for name in list(self.toolsets):
            self.registry.unregister_external(f"mcp:{name}")
        self.toolsets.clear()
        self.errors.clear()
        for name, server in self.servers().items():
            if server.get("disabled"):
                continue
            try:
                if server.get("url"):
                    toolset = MCPToolset(server["url"], id=f"mcp:{name}", headers=server.get("headers"))
                else:
                    transport = StdioTransport(
                        command=server["command"],
                        args=list(server.get("args", [])),
                        env=server.get("env") or None,
                    )
                    toolset = MCPToolset(transport, id=f"mcp:{name}", init_timeout=60)
            except Exception as exc:
                self.errors[name] = str(exc)
                logger.error("MCP server {} could not be configured: {}", name, exc)
                continue
            self.toolsets[name] = toolset
            keywords = tuple(server.get("keywords") or PRESETS.get(name, {}).get("keywords") or [name])
            description = (
                server.get("description") or PRESETS.get(name, {}).get("description") or f"{name} tools"
            )
            self.registry.register_external(f"mcp:{name}", f"mcp_{name}", description[:80], keywords)

    async def probe(self, name: str) -> list[str]:
        """Connect once and list the server's tools (used by the dashboard 'Test' button)."""
        toolset = self.toolsets.get(name)
        if toolset is None:
            raise KeyError(f"MCP server '{name}' is not enabled")
        try:
            async with toolset:
                tools = await asyncio.wait_for(toolset.list_tools(), timeout=90)
        except Exception as exc:
            self.errors[name] = f"{type(exc).__name__}: {exc}"
            raise
        names = [t.name for t in tools]
        self.tool_names[name] = names
        self.errors.pop(name, None)
        return names

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "transport": "http" if server.get("url") else "stdio",
                "target": server.get("url") or " ".join([server.get("command", ""), *server.get("args", [])]),
                "enabled": not server.get("disabled"),
                "error": self.errors.get(name),
                "tools": self.tool_names.get(name, []),
            }
            for name, server in self.servers().items()
        ]
