"""``aiva`` command line: serve, doctor, chat, say."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__

app = typer.Typer(add_completion=False, help="AIVA — voice-first AI desk companion.", no_args_is_help=False)
console = Console()


def _services():
    from .config import ConfigStore
    from .logging_setup import setup_logging
    from .services import Services

    store = ConfigStore()
    setup_logging(store.data_dir)
    return Services.build(store.root)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        serve()


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind address (default from config: 0.0.0.0)."),
    port: int | None = typer.Option(None, help="Port (default from config: 8000)."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open the web app."),
) -> None:
    """Start the AIVA server (device gateway + dashboard + simulator)."""
    import uvicorn

    from .app import create_app

    services = _services()
    host = host or services.config.server.host
    port = port or services.config.server.port
    url = f"http://localhost:{port}"
    console.print(f"[bold magenta]AIVA {__version__}[/] → [link={url}]{url}[/link]  (Ctrl+C to stop)")
    if services.config.server.open_browser and not no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(services), host=host, port=port, log_level="warning", ws_ping_interval=20)


@app.command()
def doctor(
    deep: bool = typer.Option(False, "--deep", help="Also send a tiny test prompt to every LLM."),
) -> None:
    """Check keys, models, voice and connectors before a demo."""
    from .doctor import run_checks

    services = _services()
    checks = asyncio.run(run_checks(services, deep=deep))
    table = Table(title="AIVA readiness", show_lines=False)
    table.add_column("")
    table.add_column("Check", style="bold")
    table.add_column("Detail")
    icons = {"ok": "[green]✔[/]", "warn": "[yellow]![/]", "fail": "[red]✘[/]"}
    for check in checks:
        table.add_row(icons[check.status], check.name, check.detail)
    console.print(table)
    if any(c.status == "fail" for c in checks):
        raise typer.Exit(1)


@app.command()
def chat() -> None:
    """Text chat with AIVA's brain in the terminal (no audio)."""
    from .brain.events import Notice, SpeakDirect, TextDelta, ToolStarted, TurnFinished
    from .emotions import EmotionTagParser

    services = _services()
    console.print("[dim]Type a message, or 'exit'.[/]")

    async def loop() -> None:
        while True:
            try:
                text = await asyncio.to_thread(console.input, "[bold cyan]you ›[/] ")
            except (EOFError, KeyboardInterrupt):
                return
            if text.strip().lower() in {"exit", "quit"}:
                return
            if not text.strip():
                continue
            parser = EmotionTagParser()
            console.print("[bold magenta]aiva ›[/] ", end="")
            started = time.monotonic()
            async for event in services.brain.run_turn("terminal", text, has_face=False):
                if isinstance(event, TextDelta):
                    for seg in parser.feed(event.text):
                        if seg.emotion:
                            console.print(f"[dim]({seg.emotion.value})[/] ", end="")
                        console.print(seg.text, end="", markup=False, highlight=False)
                elif isinstance(event, SpeakDirect):
                    console.print(event.text, end=" ", markup=False)
                elif isinstance(event, ToolStarted):
                    console.print(f"\n  [yellow]⚙ {event.name}[/] [dim]{event.args}[/]")
                elif isinstance(event, Notice):
                    console.print(f"\n  [red]⚠ {event.text}[/]")
                elif isinstance(event, TurnFinished):
                    ms = (time.monotonic() - started) * 1000
                    console.print(
                        f"\n  [dim]{event.deployment or '-'} · {ms:.0f} ms · tokens {event.input_tokens}/{event.output_tokens}[/]"
                    )

    asyncio.run(loop())


@app.command()
def say(
    text: str, voice: str | None = typer.Option(None, help="Edge voice, e.g. hi-IN-SwaraNeural.")
) -> None:
    """Speak a sentence through the Mac speakers with AIVA's voice."""
    import subprocess

    from .config import ConfigStore
    from .voice.audio import SPEAKER_RATE, wav_bytes
    from .voice.tts import TTSService

    config = ConfigStore().load()
    tts = TTSService(config.tts, config.assistant.language)
    pcm = asyncio.run(tts.synthesize(text, voice=voice))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "say.wav"
        path.write_bytes(wav_bytes(pcm, SPEAKER_RATE))
        subprocess.run(["afplay", str(path)], check=False)
    console.print(f"[dim]engine: {tts.last_engine}[/]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
