"""macOS skills: apps, volume, battery, screenshots, media, notifications.

Everything goes through fixed command lines (``open``, ``osascript``, ``pmset``,
``screencapture``) with arguments passed as data — never a shell string.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic_ai import RunContext

from ..brain.deps import AgentDeps
from ..brain.toolsets import ToolRegistry
from .system import applescript_string, open_target, osascript, run

_APP_ALIASES = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "whatsapp": "WhatsApp",
    "settings": "System Settings",
    "system preferences": "System Settings",
    "terminal": "Terminal",
    "calculator": "Calculator",
    "notes": "Notes",
    "music": "Music",
    "spotify": "Spotify",
    "photos": "Photos",
    "calendar": "Calendar",
    "mail": "Mail",
    "maps": "Maps",
    "finder": "Finder",
    "preview": "Preview",
    "safari": "Safari",
}


def register(reg: ToolRegistry) -> None:
    @reg.tool("mac")
    async def open_app(name: str) -> str:
        """Open (or bring to front) an app on the Mac.

        Args:
            name: App name, e.g. "Spotify", "Notes", "Google Chrome", "VS Code".
        """
        app = _APP_ALIASES.get(name.strip().lower(), name.strip())
        code, _, err = await run("open", "-a", app)
        return f"Opened {app}." if code == 0 else f"Couldn't open {app}: {err or 'not installed?'}"

    @reg.tool("mac")
    async def set_volume(percent: int) -> str:
        """Set the Mac's speaker volume.

        Args:
            percent: 0 to 100.
        """
        level = max(0, min(100, percent))
        ok, out = await osascript(f"set volume output volume {level}")
        return f"Volume set to {level}%." if ok else f"Failed: {out}"

    @reg.tool("mac")
    async def get_battery() -> str:
        """Battery percentage and charging state of the Mac."""
        code, out, err = await run("pmset", "-g", "batt")
        if code != 0:
            return f"Couldn't read battery: {err}"
        match = re.search(r"(\d+)%;\s*([\w ]+);\s*([^\s;]+ remaining|\(no estimate\)|[^;]*)", out)
        return " ".join(match.groups()).strip() if match else out

    @reg.tool("mac")
    async def take_screenshot(ctx: RunContext[AgentDeps]) -> str:
        """Take a screenshot of the Mac screen and save it in the AIVA folder."""
        folder = ctx.deps.services.config.workspace_path / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"
        code, _, err = await run("screencapture", "-x", str(path))
        if code != 0 or not path.exists():
            return f"Screenshot failed: {err or 'grant Screen Recording permission to the terminal'}"
        await open_target(str(path))
        return f"Saved screenshot to {path.name} and opened it."

    @reg.tool("mac")
    async def media_control(action: Literal["play", "pause", "toggle", "next", "previous"]) -> str:
        """Control music playing in Spotify or Apple Music.

        Args:
            action: What to do.
        """
        verb = {
            "play": "play",
            "pause": "pause",
            "toggle": "playpause",
            "next": "next track",
            "previous": "previous track",
        }[action]
        for app in ("Spotify", "Music"):
            ok, running = await osascript(f'application "{app}" is running')
            if ok and running == "true":
                ok, out = await osascript(f'tell application "{app}" to {verb}')
                return f"{app}: {action}." if ok else f"{app} failed: {out}"
        return "Neither Spotify nor Music is running. Try play_youtube or open_app first."

    @reg.tool("mac")
    async def show_notification(title: str, message: str) -> str:
        """Show a macOS notification banner.

        Args:
            title: Short title.
            message: Body text.
        """
        ok, out = await osascript(
            f"display notification {applescript_string(message)} with title {applescript_string(title)}"
        )
        return "Notification shown." if ok else f"Failed: {out}"
