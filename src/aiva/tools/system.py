"""Small async helpers around macOS command-line tools (``open``, ``osascript``…)."""

from __future__ import annotations

import asyncio
import sys


async def run(*args: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a command without a shell (no injection); returns (code, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return 124, "", "timed out"
    return proc.returncode or 0, out.decode(errors="replace").strip(), err.decode(errors="replace").strip()


async def open_target(target: str, app: str | None = None) -> tuple[bool, str]:
    """Open a URL or file with the default (or given) macOS app."""
    if sys.platform != "darwin":
        return False, "opening apps is only supported on macOS"
    args = ["open", "-a", app, target] if app else ["open", target]
    code, _, err = await run(*args)
    return code == 0, err


async def osascript(script: str, timeout: float = 10.0) -> tuple[bool, str]:
    code, out, err = await run("osascript", "-e", script, timeout=timeout)
    return code == 0, out if code == 0 else err


def applescript_string(value: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
