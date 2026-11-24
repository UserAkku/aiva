"""Composition root: builds every service once and wires them together."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from .brain import Brain
from .brain.confirm import ConfirmationGate
from .brain.toolsets import ToolRegistry
from .config import AppConfig, ConfigStore, Secrets
from .connectors import ConnectorRegistry
from .devices import DeviceRegistry
from .events import EventBus
from .llm import LLMRouter, QuotaGuard
from .scheduler import Scheduler
from .storage import Database
from .tools import build_registry
from .tools.system import applescript_string, osascript
from .voice import STTService, TTSService


@dataclass
class Services:
    store: ConfigStore
    config: AppConfig
    secrets: Secrets
    db: Database
    bus: EventBus
    quota: QuotaGuard
    router: LLMRouter
    tools: ToolRegistry
    connectors: ConnectorRegistry
    confirmations: ConfirmationGate
    scheduler: Scheduler
    stt: STTService
    tts: TTSService
    devices: DeviceRegistry
    brain: Brain = None  # type: ignore[assignment]  # set right after construction (needs services)

    @classmethod
    def build(cls, root: Path | None = None) -> Services:
        store = ConfigStore(root)
        config = store.load()
        secrets = store.load_secrets()
        db = Database(store.data_dir / "aiva.db")
        bus = EventBus()
        quota = QuotaGuard(db, bus, config.llm.warn_at)
        tools = build_registry(config.tools.disabled)
        services = cls(
            store=store,
            config=config,
            secrets=secrets,
            db=db,
            bus=bus,
            quota=quota,
            router=LLMRouter(config, secrets, quota),
            tools=tools,
            connectors=ConnectorRegistry(store.data_dir, tools),
            confirmations=ConfirmationGate(),
            scheduler=Scheduler(db, bus),
            stt=STTService(config.stt, secrets, quota, bus),
            tts=TTSService(config.tts, config.assistant.language, secrets),
            devices=DeviceRegistry(),
        )
        services.brain = Brain(services)
        services.scheduler.on_due = services._on_reminder_due
        return services

    # ── hot reload after dashboard edits ─────────────────────────────────────
    def reload(self) -> None:
        """Re-read config + secrets and rebuild what depends on them (no restart needed)."""
        self.config = self.store.load()
        self.secrets = self.store.load_secrets()
        self.quota.warn_at = sorted(self.config.llm.warn_at, reverse=True)
        self.router.reconfigure(self.config, self.secrets)
        self.tools.disabled = set(self.config.tools.disabled)
        self.stt.reconfigure(self.config.stt, self.secrets)
        self.tts.reconfigure(self.config.tts, self.config.assistant.language, self.secrets)
        self.connectors.mcp.build()
        self.brain.rebuild()
        self.bus.publish("config.reloaded")
        logger.info("configuration reloaded")

    def update_config(self, patch: dict[str, Any]) -> AppConfig:
        self.store.save_overrides(patch)
        self.reload()
        return self.config

    def set_secret(self, name: str, value: str) -> None:
        self.store.set_secret(name, value)
        self.reload()

    # ── reminders → speech ───────────────────────────────────────────────────
    async def _on_reminder_due(self, item: dict[str, Any]) -> None:
        hinglish = self.config.assistant.language != "english"
        if item["kind"] == "timer":
            label = item["text"] if item["text"] != "timer" else ""
            text = (
                f"<happy> Ding ding! आपका {label} timer पूरा हो गया!"
                if hinglish
                else f"<happy> Ding ding! Your {label} timer is done!"
            )
        else:
            text = (
                f"<happy> Reminder: {item['text']}" if not hinglish else f"<happy> याद दिला दूँ: {item['text']}"
            )
        reached = await self.devices.announce(text.replace("  ", " "))
        if reached == 0:  # nobody connected: fall back to a macOS notification
            await osascript(
                f"display notification {applescript_string(item['text'])} with title {applescript_string('AIVA')}"
            )
