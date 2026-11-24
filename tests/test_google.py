"""'Continue with Google' OAuth flow + Gmail REST backend, against mocked Google servers."""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
from pathlib import Path

import httpx
import pytest

from aiva.connectors.gmail import GmailConnector
from aiva.connectors.google import GoogleAccount, GoogleAuthError, parse_client
from aiva.connectors.store import JsonStore

CLIENT = {"installed": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "GOCSPX-test"}}


def id_token(email: str) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{seg({'alg': 'RS256'})}.{seg({'email': email})}.sig"


class FakeGoogle:
    """Just enough of accounts.google.com + the Gmail API."""

    def __init__(self) -> None:
        self.token_calls: list[dict[str, str]] = []
        self.refresh_ok = True
        self.sent: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://oauth2.googleapis.com/token"):
            form = dict(urllib.parse.parse_qsl(request.content.decode()))
            self.token_calls.append(form)
            if form["grant_type"] == "refresh_token":
                if not self.refresh_ok:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={"access_token": "fresh-token", "expires_in": 3600})
            return httpx.Response(
                200,
                json={
                    "access_token": "first-token",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                    "scope": "openid email https://www.googleapis.com/auth/gmail.modify",
                    "id_token": id_token("me@gmail.com"),
                },
            )
        if url.startswith("https://oauth2.googleapis.com/revoke"):
            return httpx.Response(200)
        assert request.headers["Authorization"].startswith("Bearer ")
        if "/messages/send" in url:
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "sent-1"})
        if url.split("?")[0].endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1"}]})
        if "/messages/m1" in url:
            return httpx.Response(
                200,
                json={
                    "labelIds": ["INBOX", "UNREAD"],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Sharma Sir <sir@college.edu>"},
                            {"name": "Subject", "value": "Project demo tomorrow"},
                            {"name": "Date", "value": "Tue, 24 Nov 2026 10:00:00 +0530"},
                        ],
                        "mimeType": "text/plain",
                        "body": {"data": base64.urlsafe_b64encode(b"See you at 11 AM.").decode()},
                    },
                },
            )
        if url.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "me@gmail.com", "messagesTotal": 42})
        return httpx.Response(404)


@pytest.fixture
def google(tmp_path: Path) -> tuple[GoogleAccount, FakeGoogle]:
    fake = FakeGoogle()
    account = GoogleAccount(JsonStore(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    account.set_client(json.dumps(CLIENT))
    return account, fake


def test_parse_client_accepts_downloaded_json_and_rejects_junk() -> None:
    assert parse_client(CLIENT)["client_id"].endswith(".apps.googleusercontent.com")
    with pytest.raises(ValueError):
        parse_client({"client_id": "not-a-google-id", "client_secret": "x"})


async def test_sign_in_flow_with_pkce(google: tuple[GoogleAccount, FakeGoogle]) -> None:
    account, fake = google
    url = account.start("http://localhost:8000/")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert q["redirect_uri"] == "http://localhost:8000/" and q["code_challenge_method"] == "S256"
    assert "gmail.modify" in q["scope"] and q["access_type"] == "offline" and q["prompt"] == "consent"

    email = await account.finish(q["state"], "auth-code")
    assert email == "me@gmail.com" and account.connected
    form = fake.token_calls[0]
    assert form["grant_type"] == "authorization_code" and form["code"] == "auth-code"
    assert len(form["code_verifier"]) >= 43 and form["redirect_uri"] == "http://localhost:8000/"
    with pytest.raises(GoogleAuthError):
        await account.finish(q["state"], "auth-code")  # a state can only be used once


async def test_token_refresh_and_expiry(google: tuple[GoogleAccount, FakeGoogle]) -> None:
    account, fake = google
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(account.start("http://localhost:8000/")).query))
    await account.finish(q["state"], "code")
    assert await account.access_token() == "first-token"

    tokens = account.store.load("google_token")
    tokens["expires_at"] = time.time() - 1
    account.store.save("google_token", tokens)
    assert await account.access_token() == "fresh-token"

    tokens = account.store.load("google_token")
    tokens["expires_at"] = time.time() - 1
    account.store.save("google_token", tokens)
    fake.refresh_ok = False
    with pytest.raises(GoogleAuthError, match="expired"):
        await account.access_token()
    assert not account.connected


async def test_gmail_uses_the_google_api_when_signed_in(tmp_path: Path) -> None:
    fake = FakeGoogle()
    gmail = GmailConnector(JsonStore(tmp_path), httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    gmail.google.set_client(CLIENT)
    q = dict(
        urllib.parse.parse_qsl(urllib.parse.urlsplit(gmail.google.start("http://localhost:8000/")).query)
    )
    await gmail.google.finish(q["state"], "code")

    assert gmail.configured and gmail.status()["method"] == "google"
    assert "me@gmail.com" in await gmail.test()
    [mail] = await gmail.inbox()
    assert mail.subject == "Project demo tomorrow" and mail.unread
    assert (await gmail.read("m1"))["body"] == "See you at 11 AM."
    await gmail.send("sir@college.edu", "Thanks", "Thank you sir!")
    raw = base64.urlsafe_b64decode(fake.sent[0]["raw"]).decode()
    assert "To: sir@college.edu" in raw and "Thank you sir!" in raw

    await gmail.disconnect_google()
    assert not gmail.configured
