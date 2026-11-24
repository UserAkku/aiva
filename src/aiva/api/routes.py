"""REST + WebSocket endpoints for the dashboard (connectors, settings, usage, memory, chat)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..brain.events import FaceEvent, Notice, SpeakDirect, TextDelta, ToolFinished, ToolStarted, TurnFinished
from ..config import PROVIDER_KEY_ENV
from ..connectors.google import GoogleAuthError
from ..devices.gateway import lan_ip
from ..doctor import run_checks, summarize
from ..emotions import EmotionTagParser
from ..llm.catalog import PROVIDERS
from ..voice.audio import SPEAKER_RATE, wav_bytes

if TYPE_CHECKING:
    from ..services import Services

STARTED_AT = time.time()


class KeyBody(BaseModel):
    key: str = Field(min_length=8, max_length=300)


class GmailBody(BaseModel):
    address: str
    app_password: str


class GoogleClientBody(BaseModel):
    config: str = Field(min_length=10, max_length=20000)


class MCPBody(BaseModel):
    name: str
    config: dict[str, Any]


class ToggleBody(BaseModel):
    enabled: bool


class DeploymentPatch(BaseModel):
    enabled: bool | None = None
    priority: int | None = None


class TextBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    session_id: str = "dashboard"


class TTSPreview(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    voice: str | None = None


def _mask(key: str | None) -> str | None:
    return None if not key else f"{key[:4]}…{key[-4:]}"


def build_router(services: Services) -> APIRouter:
    api = APIRouter(prefix="/api")

    # ── status & observability ───────────────────────────────────────────────
    @api.get("/status")
    async def status() -> dict[str, Any]:
        cfg = services.config
        return {
            "version": __version__,
            "uptime_s": round(time.time() - STARTED_AT),
            "assistant": cfg.assistant.model_dump(),
            "llm_ready": services.router.available,
            "stt_ready": services.stt.available,
            "pool_fraction": services.quota.pool_fraction(),
            "deployments": services.quota.snapshot(),
            "devices": services.devices.status(),
            "connectors": services.connectors.status(),
            "esp32": {
                "websocket": f"ws://{lan_ip()}:{cfg.server.port}/xiaozhi/v1/",
                "ota": f"http://{lan_ip()}:{cfg.server.port}/xiaozhi/ota/",
            },
        }

    @api.get("/doctor")
    async def doctor(deep: bool = False) -> dict[str, Any]:
        return summarize(await run_checks(services, deep=deep))

    @api.get("/usage")
    async def usage() -> dict[str, Any]:
        return {
            "deployments": services.quota.snapshot(),
            "pool_fraction": services.quota.pool_fraction(),
            "history": services.db.usage_history(7),
            "turns": services.db.recent_turns(40),
        }

    @api.get("/activity")
    async def activity(limit: int = 200) -> list[dict[str, Any]]:
        return services.bus.recent(limit)

    @api.websocket("/events")
    async def events(ws: WebSocket) -> None:
        await ws.accept()
        async with services.bus.subscribe() as queue:
            try:
                await ws.send_text(
                    json.dumps({"type": "hello", "recent": services.bus.recent(100)}, default=str)
                )
                while True:
                    event = await queue.get()
                    await ws.send_text(json.dumps(event, default=str, ensure_ascii=False))
            except (WebSocketDisconnect, RuntimeError):
                return

    # ── settings ─────────────────────────────────────────────────────────────
    @api.get("/settings")
    async def get_settings() -> dict[str, Any]:
        return {"config": services.config.model_dump(), "overrides": services.store.overrides()}

    @api.put("/settings")
    async def put_settings(patch: dict[str, Any]) -> dict[str, Any]:
        if isinstance(patch.get("llm"), dict):
            patch["llm"].pop("deployments", None)  # deployments have their own endpoint
        try:
            config = services.update_config(patch)
        except Exception as exc:
            raise HTTPException(400, f"invalid settings: {exc}") from exc
        return {"config": config.model_dump()}

    # ── LLM providers & keys ─────────────────────────────────────────────────
    @api.get("/providers")
    async def providers() -> list[dict[str, Any]]:
        deployments = {row["id"]: row for row in services.quota.snapshot()}
        out = []
        for name, info in PROVIDERS.items():
            key = services.secrets.key_for(name)
            out.append(
                {
                    "name": name,
                    "label": info.label,
                    "key_env": PROVIDER_KEY_ENV[name][0],
                    "key_set": bool(key),
                    "key_hint": _mask(key),
                    "signup_url": info.signup_url,
                    "free_tier": info.free_tier,
                    "kind": info.kind,
                    "deployments": [
                        {
                            **d.model_dump(),
                            "state": deployments.get(d.id),
                            "build_error": services.router.build_errors.get(d.id),
                        }
                        for d in services.config.llm.deployments
                        if d.provider == name
                    ],
                }
            )
        return out

    @api.put("/providers/{provider}/key")
    async def set_key(provider: str, body: KeyBody) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise HTTPException(404, "unknown provider")
        services.set_secret(PROVIDER_KEY_ENV[provider][0], body.key.strip())
        if PROVIDERS[provider].kind == "voice":
            pcm = await services.tts.synthesize("नमस्ते! मैं AIVA हूँ।", engine=provider, emotion="happy")
            ok = bool(pcm) and services.tts.last_engine == provider
            message = (
                "Voice works — AIVA now speaks with Sarvam."
                if ok
                else "Sarvam rejected the key or has no credits (see the server log)."
            )
            return {"ok": ok, "message": message}
        from ..doctor import _provider_models

        models, message = await _provider_models(provider, body.key.strip())
        return {
            "ok": models is not None,
            "message": message if models is None else f"Key works — {len(models)} models available.",
        }

    @api.delete("/providers/{provider}/key")
    async def delete_key(provider: str) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise HTTPException(404, "unknown provider")
        services.set_secret(PROVIDER_KEY_ENV[provider][0], "")
        return {"ok": True}

    @api.patch("/deployments/{dep_id}")
    async def patch_deployment(dep_id: str, body: DeploymentPatch) -> dict[str, Any]:
        deployments = [d.model_dump() for d in services.config.llm.deployments]
        for dep in deployments:
            if dep["id"] == dep_id:
                if body.enabled is not None:
                    dep["enabled"] = body.enabled
                if body.priority is not None:
                    dep["priority"] = body.priority
                break
        else:
            raise HTTPException(404, "unknown deployment")
        services.update_config({"llm": {"deployments": deployments}})
        return {"ok": True}

    # ── tools ────────────────────────────────────────────────────────────────
    @api.get("/tools")
    async def tools() -> list[dict[str, Any]]:
        return services.tools.catalog()

    @api.put("/tools/{name}")
    async def toggle_tool(name: str, body: ToggleBody) -> dict[str, Any]:
        disabled = set(services.config.tools.disabled)
        disabled.discard(name) if body.enabled else disabled.add(name)
        services.update_config({"tools": {"disabled": sorted(disabled)}})
        return {"ok": True}

    # ── connectors ───────────────────────────────────────────────────────────
    @api.get("/connectors")
    async def connectors() -> dict[str, Any]:
        return services.connectors.status()

    @api.post("/connectors/gmail")
    async def connect_gmail(body: GmailBody) -> dict[str, Any]:
        gmail = services.connectors.gmail
        try:
            message = await gmail.try_connect(body.address, body.app_password)
        except ValueError as exc:  # rejected before contacting Google
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(400, gmail.explain(exc)) from exc
        services.bus.publish("connector.connected", name="gmail")
        return {"ok": True, "message": message}

    @api.post("/connectors/google/client")
    async def google_client(body: GoogleClientBody) -> dict[str, Any]:
        try:
            services.connectors.gmail.google.set_client(body.config)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(400, f"That doesn't look like Google OAuth client details: {exc}") from exc
        return services.connectors.gmail.google.status()

    @api.post("/connectors/google/start")
    async def google_start(request: Request) -> dict[str, Any]:
        # Google redirects back to this app's root on the loopback address (Desktop-app clients allow it)
        redirect_uri = f"{request.url.scheme}://{request.url.netloc}/"
        try:
            return {"url": services.connectors.gmail.google.start(redirect_uri)}
        except GoogleAuthError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.delete("/connectors/google")
    async def google_disconnect() -> dict[str, Any]:
        await services.connectors.gmail.disconnect_google()
        return {"ok": True}

    @api.delete("/connectors/gmail")
    async def disconnect_gmail() -> dict[str, Any]:
        services.connectors.gmail.disconnect()
        return {"ok": True}

    @api.post("/connectors/mcp")
    async def add_mcp(body: MCPBody) -> dict[str, Any]:
        try:
            name = services.connectors.mcp.save_server(body.name, body.config)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        services.connectors.mcp.build()
        services.brain.rebuild()
        return {"ok": True, "name": name}

    @api.post("/connectors/mcp/{name}/test")
    async def test_mcp(name: str) -> dict[str, Any]:
        try:
            tools = await services.connectors.mcp.probe(name)
        except Exception as exc:
            raise HTTPException(400, f"{type(exc).__name__}: {exc}") from exc
        return {"ok": True, "tools": tools}

    @api.delete("/connectors/mcp/{name}")
    async def remove_mcp(name: str) -> dict[str, Any]:
        services.connectors.mcp.remove_server(name)
        services.connectors.mcp.build()
        services.brain.rebuild()
        return {"ok": True}

    # ── memory ───────────────────────────────────────────────────────────────
    @api.get("/memory")
    async def memory() -> dict[str, Any]:
        db = services.db
        return {
            "facts": db.facts(100),
            "notes": db.notes(50),
            "todos": db.todos(include_done=True),
            "reminders": db.pending_reminders(),
        }

    @api.post("/memory/facts")
    async def add_fact(body: TextBody) -> dict[str, Any]:
        return {"id": services.db.add_fact(body.text)}

    @api.delete("/memory/{kind}/{item_id}")
    async def delete_item(kind: str, item_id: int) -> dict[str, Any]:
        db = services.db
        actions = {
            "facts": db.delete_fact,
            "notes": db.delete_note,
            "todos": db.delete_todo,
            "reminders": services.scheduler.cancel,
        }
        if kind not in actions:
            raise HTTPException(404, "unknown memory kind")
        return {"ok": actions[kind](item_id)}

    @api.post("/memory/todos/{item_id}/done")
    async def done_todo(item_id: int) -> dict[str, Any]:
        return {"ok": services.db.complete_todo(item_id)}

    @api.post("/conversation/reset")
    async def reset_conversation(session_id: str | None = None) -> dict[str, Any]:
        ids = [session_id] if session_id else [*services.devices.sessions, "dashboard"]
        for sid in ids:
            services.brain.conversations.reset(sid)
        return {"ok": True}

    # ── text chat (Server-Sent Events) ───────────────────────────────────────
    @api.post("/chat")
    async def chat(body: TextBody) -> StreamingResponse:
        async def stream():
            parser = EmotionTagParser()
            async for event in services.brain.run_turn(body.session_id, body.text, has_face=False):
                if isinstance(event, TextDelta):
                    for seg in parser.feed(event.text):
                        if seg.emotion:
                            yield _sse({"type": "emotion", "emotion": seg.emotion.value})
                        if seg.text:
                            yield _sse({"type": "text", "text": seg.text})
                elif isinstance(event, SpeakDirect):
                    yield _sse({"type": "text", "text": "\n" + event.text + "\n"})
                elif isinstance(event, ToolStarted):
                    yield _sse({"type": "tool", "name": event.name, "status": "start", "args": event.args})
                elif isinstance(event, ToolFinished):
                    yield _sse({"type": "tool", "name": event.name, "status": "end", "ok": event.ok})
                elif isinstance(event, Notice):
                    yield _sse({"type": "notice", "text": event.text, "level": event.level})
                elif isinstance(event, FaceEvent):
                    yield _sse(
                        {
                            "type": "face",
                            "emotion": event.emotion and event.emotion.value,
                            "animation": event.animation,
                        }
                    )
                elif isinstance(event, TurnFinished):
                    for seg in parser.flush():
                        if seg.text:
                            yield _sse({"type": "text", "text": seg.text})
                    services.bus.publish(
                        "turn.assistant",
                        device="dashboard",
                        session=body.session_id,
                        text=event.reply_text,
                        deployment=event.deployment,
                        tools=event.tools,
                        error=event.error,
                        tokens={"in": event.input_tokens, "out": event.output_tokens},
                    )
                    yield _sse(
                        {
                            "type": "done",
                            "deployment": event.deployment,
                            "model": event.model,
                            "tools": event.tools,
                            "error": event.error,
                        }
                    )

        services.bus.publish("turn.user", device="dashboard", session=body.session_id, text=body.text)
        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    # ── voices ───────────────────────────────────────────────────────────────
    voices_cache: dict[str, Any] = {}

    @api.get("/tts/voices")
    async def voices() -> list[dict[str, str]]:
        if "list" not in voices_cache:
            import edge_tts

            try:
                all_voices = await asyncio.wait_for(edge_tts.list_voices(), timeout=10)
            except Exception as exc:
                raise HTTPException(502, f"could not list voices: {exc}") from exc
            order = {"hi-IN": 0, "en-IN": 1}
            voices_cache["list"] = sorted(
                (
                    {"name": v["ShortName"], "locale": v["Locale"], "gender": v["Gender"]}
                    for v in all_voices
                    if v["Locale"] in ("hi-IN", "en-IN", "en-US", "en-GB") or "Multilingual" in v["ShortName"]
                ),
                key=lambda v: (order.get(v["locale"], 2 if "Multilingual" in v["name"] else 3), v["name"]),
            )
        return voices_cache["list"]

    @api.post("/tts/preview")
    async def preview(body: TTSPreview) -> Response:
        engine = ("edge" if "Neural" in body.voice else "sarvam") if body.voice else None
        pcm = await services.tts.synthesize(body.text, voice=body.voice, engine=engine, emotion="happy")
        return Response(wav_bytes(pcm, SPEAKER_RATE), media_type="audio/wav")

    return api


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
