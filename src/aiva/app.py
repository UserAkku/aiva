"""FastAPI application: device gateway + dashboard API + the web app (simulator & dashboard)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from . import __version__
from .api import build_router as build_api
from .devices.gateway import build_router as build_gateway
from .services import Services

_NO_WEB = """<!doctype html><meta charset=utf-8><title>AIVA</title>
<body style="font-family:system-ui;background:#0b0b14;color:#e5e7eb;display:grid;place-items:center;height:100vh">
<div style="max-width:560px"><h1>AIVA server is running 🎉</h1>
<p>The web app isn't built yet. Run <code>make web</code> (or <code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>)
and reload. API docs: <a style="color:#a5b4fc" href="/docs">/docs</a></p></div>"""


def create_app(services: Services | None = None) -> FastAPI:
    services = services or Services.build()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services.scheduler.start()
        logger.info("AIVA {} ready — {} LLM deployment(s)", __version__, len(services.router.models))
        yield
        await services.scheduler.stop()
        services.db.close()

    app = FastAPI(title="AIVA", version=__version__, lifespan=lifespan)
    app.state.services = services
    # The Vite dev server (npm run dev) talks to the API from another port.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_gateway(services))
    app.include_router(build_api(services))

    dist = services.store.root / "web" / "dist"
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate)
            # index.html must never be cached, or a rebuilt UI keeps loading old asset hashes
            return FileResponse(
                dist / "index.html", headers={"Cache-Control": "no-cache"}
            )  # client-side routing
    else:

        @app.get("/", include_in_schema=False)
        async def no_web() -> HTMLResponse:
            return HTMLResponse(_NO_WEB)

    return app
