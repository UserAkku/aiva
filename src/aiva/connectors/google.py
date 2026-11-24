"""'Continue with Google' — OAuth 2.0 for an installed (desktop) app, with PKCE.

The user registers a *Desktop app* OAuth client once (Google requires every app to be
registered; the dashboard walks through it), then connecting is one click: Google's
sign-in page → Allow → back to AIVA. Google redirects to this Mac's loopback address,
so nothing is exposed to the internet. Tokens live in ``data/connectors`` (mode 0600)
and are revoked on disconnect.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from .store import JsonStore

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = ("openid", "email", "https://www.googleapis.com/auth/gmail.modify")


class GoogleAuthError(RuntimeError):
    """Sign-in problem the user can fix (shown in the dashboard and spoken by AIVA)."""


@dataclass
class _Pending:
    verifier: str
    redirect_uri: str
    created: float


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwt_payload(token: str) -> dict[str, Any]:
    """Read the claims of a Google ID token (it came straight from Google over TLS, so no signature check)."""
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return {}


def parse_client(raw: str | dict[str, Any]) -> dict[str, str]:
    """Accept the downloaded client JSON ({"installed": {...}} / {"web": {...}}) or {client_id, client_secret}."""
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    data = data.get("installed") or data.get("web") or data
    client_id = str(data.get("client_id", "")).strip()
    client_secret = str(data.get("client_secret", "")).strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise ValueError("That isn't a Google OAuth client ID (it ends with .apps.googleusercontent.com).")
    if not client_secret:
        raise ValueError("The client secret is missing — paste the whole downloaded JSON.")
    return {"client_id": client_id, "client_secret": client_secret}


class GoogleAccount:
    def __init__(self, store: JsonStore, http: httpx.AsyncClient | None = None) -> None:
        self.store = store
        self.http = http or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0))
        self._pending: dict[str, _Pending] = {}
        self.expired = False

    # ── client registration ──────────────────────────────────────────────────
    def client(self) -> dict[str, str] | None:
        cid, secret = os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_SECRET", "")
        if cid and secret:
            return {"client_id": cid, "client_secret": secret}
        saved = self.store.load("google_client")
        return saved if saved and saved.get("client_id") else None

    def set_client(self, raw: str | dict[str, Any]) -> None:
        self.store.save("google_client", parse_client(raw))

    # ── tokens ───────────────────────────────────────────────────────────────
    def _tokens(self) -> dict[str, Any] | None:
        return self.store.load("google_token")

    @property
    def connected(self) -> bool:
        tokens = self._tokens()
        return bool(tokens and tokens.get("refresh_token")) and not self.expired

    @property
    def email(self) -> str:
        return (self._tokens() or {}).get("email", "")

    def status(self) -> dict[str, Any]:
        return {
            "client_configured": self.client() is not None,
            "connected": self.connected,
            "email": self.email,
            "expired": self.expired,
        }

    # ── the sign-in flow ─────────────────────────────────────────────────────
    def start(self, redirect_uri: str) -> str:
        client = self.client()
        if client is None:
            raise GoogleAuthError("Google sign-in isn't set up yet — finish the one-time setup first.")
        verifier = _b64url(secrets.token_bytes(48))
        state = secrets.token_urlsafe(24)
        now = time.time()
        self._pending = {k: v for k, v in self._pending.items() if now - v.created < 900}
        self._pending[state] = _Pending(verifier, redirect_uri, now)
        params = {
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",  # always return a refresh token
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
        }
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    def owns_state(self, state: str) -> bool:
        return state in self._pending

    async def finish(self, state: str, code: str) -> str:
        pending = self._pending.pop(state, None)
        client = self.client()
        if pending is None or client is None:
            raise GoogleAuthError("This sign-in link expired. Click 'Continue with Google' again.")
        resp = await self.http.post(
            TOKEN_URL,
            data={
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "code": code,
                "code_verifier": pending.verifier,
                "grant_type": "authorization_code",
                "redirect_uri": pending.redirect_uri,
            },
        )
        data = resp.json()
        if resp.status_code >= 400 or "access_token" not in data:
            raise GoogleAuthError(
                f"Google refused the sign-in: {data.get('error_description') or data.get('error')}"
            )
        if "gmail.modify" not in data.get("scope", ""):
            raise GoogleAuthError(
                "Gmail permission wasn't granted — tick the Gmail box on Google's consent screen."
            )
        email = _jwt_payload(data.get("id_token", "")).get("email", "")
        self.store.save(
            "google_token",
            {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token") or (self._tokens() or {}).get("refresh_token"),
                "expires_at": time.time() + int(data.get("expires_in", 3600)) - 60,
                "scope": data.get("scope", ""),
                "email": email,
            },
        )
        self.expired = False
        logger.info("Google account connected: {}", email)
        return email

    async def access_token(self) -> str:
        tokens = self._tokens()
        if not tokens or not tokens.get("refresh_token"):
            raise GoogleAuthError(
                "Gmail isn't connected — click 'Continue with Google' on the Connectors page."
            )
        if time.time() < float(tokens.get("expires_at", 0)):
            return str(tokens["access_token"])
        client = self.client()
        if client is None:
            raise GoogleAuthError("The Google client setup is missing.")
        resp = await self.http.post(
            TOKEN_URL,
            data={
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        data = resp.json()
        if resp.status_code >= 400 or "access_token" not in data:
            if data.get("error") == "invalid_grant":
                self.expired = True
                raise GoogleAuthError(
                    "The Google connection expired (apps in Testing mode must sign in again every 7 days). "
                    "Click 'Continue with Google' again."
                )
            raise GoogleAuthError(
                f"Couldn't refresh Google access: {data.get('error_description') or data.get('error')}"
            )
        tokens.update(
            access_token=data["access_token"], expires_at=time.time() + int(data.get("expires_in", 3600)) - 60
        )
        self.store.save("google_token", tokens)
        return str(tokens["access_token"])

    async def disconnect(self) -> None:
        tokens = self._tokens() or {}
        token = tokens.get("refresh_token") or tokens.get("access_token")
        if token:
            try:
                await self.http.post(REVOKE_URL, data={"token": token})
            except Exception as exc:  # revoking is best effort
                logger.warning("could not revoke Google token: {}", exc)
        self.store.delete("google_token")
        self.expired = False
