"""Dashboard REST/WebSocket API (everything under ``/api``)."""

from .routes import build_router

__all__ = ["build_router"]
