"""WebSocket + OTA endpoints that devices talk to.

* ``WS  /xiaozhi/v1/``  — the voice session (xiaozhi protocol).
* ``ANY /xiaozhi/ota/`` — xiaozhi firmware boot check-in: tells the ESP32 where the
  WebSocket is (this Mac's LAN IP) and the token to use.
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from loguru import logger

from .protocol import DeviceHello
from .session import DeviceSession

if TYPE_CHECKING:
    from ..services import Services


def lan_ip() -> str:
    """Best guess of this Mac's IP on the local network (what the ESP32 should connect to)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def build_router(services: Services) -> APIRouter:
    router = APIRouter()

    @router.websocket("/xiaozhi/v1/")
    @router.websocket("/xiaozhi/v1")
    async def device_socket(ws: WebSocket) -> None:
        # Browsers can't set WebSocket headers, so query parameters are accepted too.
        q, h = ws.query_params, ws.headers
        device_id = h.get("device-id") or q.get("device-id") or "unknown-device"
        client_id = h.get("client-id") or q.get("client-id") or ""
        token = (h.get("authorization") or "").removeprefix("Bearer ").strip() or q.get("token", "")
        expected = services.config.server.device_token
        await ws.accept()
        if expected and token != expected:
            logger.warning("device {} rejected: bad token", device_id)
            await ws.close(code=4401, reason="invalid token")
            return
        try:
            first = await asyncio.wait_for(ws.receive_text(), timeout=10)
            hello_msg = json.loads(first)
            if hello_msg.get("type") != "hello":
                raise ValueError("first message must be hello")
        except Exception as exc:
            logger.warning("device {} handshake failed: {}", device_id, exc)
            await ws.close(code=4400, reason="expected hello")
            return

        hello = DeviceHello.parse(hello_msg)
        kind = "simulator" if hello.is_aiva else "esp32"
        try:
            session = DeviceSession(
                services,
                hello,
                device_id=device_id,
                client_id=client_id,
                send_text=ws.send_text,
                send_bytes=ws.send_bytes,
                kind=kind,
            )
        except RuntimeError as exc:  # e.g. Opus device without libopus installed
            logger.error("{}", exc)
            await ws.send_text(
                json.dumps({"type": "alert", "status": "Error", "message": str(exc), "emotion": "sad"})
            )
            await ws.close(code=4500, reason="audio codec unavailable")
            return
        services.devices.add(session)
        await session.start()
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if (data := message.get("bytes")) is not None:
                    await session.on_audio(data)
                elif (text := message.get("text")) is not None:
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    await session.on_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            services.devices.remove(session)
            await session.close()
            logger.info("device {} disconnected", device_id)

    @router.api_route("/xiaozhi/ota/", methods=["GET", "POST"])
    @router.api_route("/xiaozhi/ota", methods=["GET", "POST"])
    async def ota(request: Request) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                body = {}
        version = ((body.get("application") or {}).get("version")) or "1.0.0"
        port = services.config.server.port
        now = time.time()
        offset_min = int(time.localtime().tm_gmtoff / 60)
        services.bus.publish("device.ota", device=request.headers.get("device-id", "?"), version=version)
        return {
            "server_time": {"timestamp": int(now * 1000), "timezone_offset": offset_min},
            "firmware": {"version": version, "url": ""},
            "websocket": {
                "url": f"ws://{lan_ip()}:{port}/xiaozhi/v1/",
                "token": services.config.server.device_token,
            },
        }

    return router
