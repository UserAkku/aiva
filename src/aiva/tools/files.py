"""File skills, sandboxed to a few well-known folders (AIVA workspace, Downloads, Documents, Desktop)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic_ai import RunContext

from ..brain.deps import AgentDeps
from ..brain.toolsets import ToolRegistry
from .system import open_target

Folder = Literal["workspace", "downloads", "documents", "desktop"]
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".py", ".html", ".css", ".js", ".log", ".yaml", ".yml"}


def roots(ctx: RunContext[AgentDeps]) -> dict[str, Path]:
    home = Path.home()
    return {
        "workspace": ctx.deps.services.config.workspace_path,
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "desktop": home / "Desktop",
    }


def resolve_path(ctx: RunContext[AgentDeps], name: str) -> Path | None:
    """Find a file by absolute path or by (partial) name inside the allowed folders."""
    allowed = list(roots(ctx).values())
    candidate = Path(name).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if resolved.exists() and any(resolved.is_relative_to(r.resolve()) for r in allowed):
            return resolved
        return None
    for root in allowed:
        direct = (root / name).resolve()
        if direct.exists() and direct.is_relative_to(root.resolve()):
            return direct
    needle = name.lower()
    matches = []
    for root in allowed:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and needle in path.name.lower():
                matches.append(path)
            if len(matches) > 50:
                break
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} TB"


def register(reg: ToolRegistry) -> None:
    @reg.tool("files")
    def list_files(ctx: RunContext[AgentDeps], folder: Folder = "workspace", contains: str = "") -> str:
        """List the most recent files in a folder.

        Args:
            folder: Which folder.
            contains: Optional text the file name must contain, e.g. ".pdf".
        """
        root = roots(ctx)[folder]
        if not root.exists():
            return f"{folder} folder not found."
        files = [p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")]
        if contains:
            files = [p for p in files if contains.lower() in p.name.lower()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return "No files."
        return "\n".join(
            f"{p.name} ({_human_size(p.stat().st_size)}, {datetime.fromtimestamp(p.stat().st_mtime):%d %b %H:%M})"
            for p in files[:15]
        )

    @reg.tool("files")
    async def open_file(ctx: RunContext[AgentDeps], name: str) -> str:
        """Open a file in its default Mac app (PDF in Preview, etc.).

        Args:
            name: File name or part of it, or a full path.
        """
        path = resolve_path(ctx, name)
        if path is None:
            return f"Couldn't find '{name}' in workspace, Downloads, Documents or Desktop."
        ok, err = await open_target(str(path))
        return f"Opened {path.name}." if ok else f"Couldn't open: {err}"

    @reg.tool("files")
    def read_text_file(ctx: RunContext[AgentDeps], name: str) -> str:
        """Read a text file (txt, md, csv, json, code).

        Args:
            name: File name or part of it, or a full path.
        """
        path = resolve_path(ctx, name)
        if path is None:
            return f"Couldn't find '{name}'."
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            return f"{path.name} isn't a plain text file. For PDFs use read_pdf."
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:3000] + (" …" if len(text) > 3000 else "")

    @reg.tool("files")
    def write_text_file(ctx: RunContext[AgentDeps], filename: str, content: str) -> str:
        """Create or overwrite a text file in the AIVA workspace folder.

        Args:
            filename: e.g. "shopping-list.txt".
            content: File content.
        """
        root = roots(ctx)["workspace"]
        path = (root / Path(filename).name).resolve()
        path.write_text(content, encoding="utf-8")
        return f"Saved {path.name} in the AIVA folder."
