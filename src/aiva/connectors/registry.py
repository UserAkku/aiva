"""One place that owns every connector (for the brain, the tools and the dashboard)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..brain.toolsets import ToolRegistry
from .gmail import GmailConnector
from .mcp import PRESETS, MCPManager
from .store import JsonStore


class ConnectorRegistry:
    def __init__(self, data_dir: Path, registry: ToolRegistry) -> None:
        self.store = JsonStore(data_dir / "connectors")
        self.gmail = GmailConnector(self.store)
        self.mcp = MCPManager(self.store, registry)
        self.mcp.build()

    def mcp_toolsets(self) -> list[Any]:
        return list(self.mcp.toolsets.values())

    def status(self) -> dict[str, Any]:
        return {
            "gmail": self.gmail.status(),
            "mcp": self.mcp.status(),
            "mcp_presets": {
                k: {"description": v["description"], "config": v["config"]} for k, v in PRESETS.items()
            },
        }
