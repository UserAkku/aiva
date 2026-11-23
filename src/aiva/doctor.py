"""Demo-readiness checks ("aiva doctor" and the dashboard's Readiness card).

Validates keys against each provider's ``/models`` endpoint, confirms the configured
model ids still exist (free-tier catalogs change often!), optionally pings every
deployment with a 1-token request, and checks voice + workspace + Gmail.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx

from .devices.gateway import lan_ip
from .llm.catalog import PROVIDERS
from .voice.vad import MODEL_PATH

if TYPE_CHECKING:
    from .services import Services

Status = Literal["ok", "warn", "fail"]


@dataclass
class Check:
    name: str
    status: Status
    detail: str
    group: str = "general"


async def _provider_models(provider: str, key: str) -> tuple[set[str] | None, str]:
    info = PROVIDERS[provider]
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(info.models_url, headers=headers)
    except Exception as exc:
        return None, f"network error: {exc}"
    if resp.status_code in (401, 403):
        return None, "API key rejected (401/403)"
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text[:120]}"
    data = resp.json().get("data", [])
    return {str(m.get("id", "")).removeprefix("models/") for m in data}, "ok"


async def _ping_deployment(services: Services, dep_id: str) -> Check:
    from pydantic_ai import Agent

    model = services.router.models[dep_id]
    started = time.monotonic()
    try:
        agent = Agent(model, instructions="Reply with exactly: OK")
        result = await asyncio.wait_for(agent.run("ping", model_settings={"max_tokens": 16}), timeout=25)
        ms = (time.monotonic() - started) * 1000
        return Check(f"LLM {dep_id}", "ok", f"answered '{result.output.strip()[:20]}' in {ms:.0f} ms", "llm")
    except Exception as exc:
        return Check(f"LLM {dep_id}", "fail", f"{type(exc).__name__}: {str(exc)[:160]}", "llm")


async def run_checks(services: Services, *, deep: bool = False) -> list[Check]:
    checks: list[Check] = []
    config, secrets = services.config, services.secrets

    # ── LLM providers ────────────────────────────────────────────────────────
    used = {d.provider for d in config.llm.deployments if d.enabled}
    keyed = [p for p in used if secrets.key_for(p)]
    if not keyed:
        checks.append(Check("LLM providers", "fail", "No API keys. Add at least a free Groq key.", "llm"))
    results = await asyncio.gather(*(_provider_models(p, secrets.key_for(p) or "") for p in keyed))
    for provider, (models, message) in zip(keyed, results, strict=True):
        label = PROVIDERS[provider].label
        if models is None:
            checks.append(Check(f"{label} key", "fail", message, "llm"))
            continue
        configured = [d for d in config.llm.deployments if d.provider == provider and d.enabled]
        missing = [d.model for d in configured if d.model not in models and not d.model.endswith("-latest")]
        status: Status = "warn" if missing else "ok"
        detail = f"key valid, {len(models)} models available"
        if missing:
            detail += f"; not found (retired?): {', '.join(missing)}"
        checks.append(Check(f"{label} key", status, detail, "llm"))
    for provider in sorted(used - set(keyed)):
        checks.append(
            Check(
                f"{PROVIDERS[provider].label} key",
                "warn",
                f"not set — optional backup ({PROVIDERS[provider].signup_url})",
                "llm",
            )
        )
    if deep and services.router.models:
        checks.extend(await asyncio.gather(*(_ping_deployment(services, d) for d in services.router.models)))

    # ── voice ────────────────────────────────────────────────────────────────
    checks.append(
        Check(
            "Speech-to-text",
            "ok" if services.stt.available else "fail",
            "Groq Whisper" + (" + Mistral Voxtral fallback" if secrets.key_for("mistral") else "")
            if services.stt.available
            else "needs a Groq (or Mistral) key",
            "voice",
        )
    )
    checks.append(
        Check("Voice activity model", "ok" if MODEL_PATH.exists() else "fail", str(MODEL_PATH.name), "voice")
    )
    started = time.monotonic()
    try:
        pcm = await asyncio.wait_for(services.tts.synthesize("Testing one two three", "en"), timeout=15)
        engine = services.tts.last_engine
        ms = (time.monotonic() - started) * 1000
        checks.append(
            Check(
                "Text-to-speech",
                "ok" if engine == "edge" else "warn",
                f"{engine} voice OK ({ms:.0f} ms)"
                + ("" if engine == "edge" else " — Edge TTS unreachable, using offline voice"),
                "voice",
            )
            if pcm
            else Check("Text-to-speech", "fail", "no audio produced", "voice")
        )
    except Exception as exc:
        checks.append(Check("Text-to-speech", "fail", str(exc), "voice"))
    checks.append(
        Check(
            "Offline voice (say)",
            "ok" if shutil.which("say") else "warn",
            "macOS say available" if shutil.which("say") else "not on macOS",
            "voice",
        )
    )

    # ── connectors & system ──────────────────────────────────────────────────
    gmail = services.connectors.gmail
    if gmail.configured:
        try:
            checks.append(Check("Gmail", "ok", await gmail.test(), "connectors"))
        except Exception as exc:
            checks.append(Check("Gmail", "fail", str(exc)[:160], "connectors"))
    else:
        checks.append(Check("Gmail", "warn", "not connected (optional)", "connectors"))
    for server in services.connectors.mcp.status():
        checks.append(
            Check(
                f"MCP {server['name']}",
                "fail" if server["error"] else "ok",
                server["error"] or server["target"],
                "connectors",
            )
        )
    try:
        probe = services.config.workspace_path / ".aiva-write-test"
        probe.write_text("ok")
        probe.unlink()
        checks.append(Check("Workspace", "ok", str(services.config.workspace_path), "system"))
    except Exception as exc:
        checks.append(Check("Workspace", "fail", str(exc), "system"))
    checks.append(
        Check(
            "ESP32 endpoint",
            "ok",
            f"ws://{lan_ip()}:{config.server.port}/xiaozhi/v1/  ·  OTA http://{lan_ip()}:{config.server.port}/xiaozhi/ota/",
            "system",
        )
    )
    return checks


def summarize(checks: list[Check]) -> dict[str, Any]:
    worst = (
        "fail"
        if any(c.status == "fail" for c in checks)
        else ("warn" if any(c.status == "warn" for c in checks) else "ok")
    )
    return {"status": worst, "checks": [asdict(c) for c in checks]}
