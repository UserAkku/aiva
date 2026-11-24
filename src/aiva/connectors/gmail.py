"""Gmail for AIVA, two ways:

* **Continue with Google** (recommended): OAuth sign-in (see ``google.py``) + the Gmail
  REST API. One click once the app is registered.
* **App Password** (fallback): IMAP (read/search) and SMTP (send) with a 16-letter
  Google App Password.

Whichever is connected is used; Google sign-in wins if both are.
"""

from __future__ import annotations

import asyncio
import base64
import email
import imaplib
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

import httpx

from .google import GoogleAccount
from .store import JsonStore

IMAP_HOST, SMTP_HOST = "imap.gmail.com", "smtp.gmail.com"
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(slots=True)
class MailSummary:
    uid: str
    sender: str
    subject: str
    date: str
    unread: bool


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _plain_text(msg: email.message.Message) -> str:
    """Best-effort readable body: prefer text/plain, else strip tags from text/html."""
    parts = msg.walk() if msg.is_multipart() else [msg]
    html_body = ""
    for part in parts:
        ctype = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/plain":
            return text.strip()
        if ctype == "text/html" and not html_body:
            html_body = text
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_body)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def _header(headers: list[dict[str, str]], name: str) -> str:
    return next((h.get("value", "") for h in headers if h.get("name", "").lower() == name.lower()), "")


def _decode_part(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _api_body(payload: dict[str, Any]) -> str:
    """Prefer text/plain anywhere in the MIME tree, else strip the first text/html."""
    html_body = ""
    stack = [payload]
    while stack:
        part = stack.pop(0)
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            return _decode_part(data).strip()
        if data and mime == "text/html" and not html_body:
            html_body = _decode_part(data)
        stack.extend(part.get("parts") or [])
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_body)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


class GmailAPI:
    """Minimal Gmail REST client on top of the Google sign-in."""

    def __init__(self, account: GoogleAccount) -> None:
        self.account = account

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        token = await self.account.access_token()
        resp = await self.account.http.get(
            f"{GMAIL_API}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Gmail API {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def profile(self) -> str:
        data = await self._get("/profile")
        return (
            f"Connected with Google as {data.get('emailAddress')} — {data.get('messagesTotal', '?')} emails."
        )

    async def _summaries(self, query: str, limit: int) -> list[MailSummary]:
        listing = await self._get("/messages", q=query, maxResults=limit)
        out: list[MailSummary] = []
        for item in listing.get("messages", [])[:limit]:
            msg = await self._get(
                f"/messages/{item['id']}", format="metadata", metadataHeaders=["From", "Subject", "Date"]
            )
            headers = (msg.get("payload") or {}).get("headers", [])
            try:
                date = parsedate_to_datetime(_header(headers, "Date")).strftime("%d %b %H:%M")
            except Exception:
                date = _header(headers, "Date")
            out.append(
                MailSummary(
                    uid=item["id"],
                    sender=_header(headers, "From"),
                    subject=_header(headers, "Subject") or "(no subject)",
                    date=date,
                    unread="UNREAD" in msg.get("labelIds", []),
                )
            )
        return out

    async def inbox(self, unread_only: bool, limit: int) -> list[MailSummary]:
        return await self._summaries("in:inbox is:unread" if unread_only else "in:inbox", limit)

    async def search(self, query: str, limit: int) -> list[MailSummary]:
        return await self._summaries(query, limit)

    async def read(self, uid: str) -> dict[str, str]:
        msg = await self._get(f"/messages/{uid}", format="full")
        headers = (msg.get("payload") or {}).get("headers", [])
        return {
            "from": _header(headers, "From"),
            "to": _header(headers, "To"),
            "subject": _header(headers, "Subject"),
            "date": _header(headers, "Date"),
            "body": _api_body(msg.get("payload") or {}),
        }

    async def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        if self.account.email:
            msg["From"] = self.account.email
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        token = await self.account.access_token()
        resp = await self.account.http.post(
            f"{GMAIL_API}/messages/send", json={"raw": raw}, headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Gmail API {resp.status_code}: {resp.text[:200]}")


class GmailConnector:
    name = "gmail"

    def __init__(self, store: JsonStore, http: httpx.AsyncClient | None = None) -> None:
        self.store = store
        cfg = store.load("gmail", {}) or {}
        self.address: str = cfg.get("address", "")
        self._password: str = cfg.get("app_password", "")
        self.last_error: str | None = None
        self.google = GoogleAccount(store, http)
        self.api = GmailAPI(self.google)

    @property
    def via_google(self) -> bool:
        return self.google.connected

    @property
    def configured(self) -> bool:
        return self.via_google or bool(self.address and self._password)

    def configure(self, address: str, app_password: str) -> None:
        self.address = address.strip()
        self._password = re.sub(r"\s+", "", app_password)
        self.store.save("gmail", {"address": self.address, "app_password": self._password})

    @staticmethod
    def normalise_app_password(raw: str) -> str:
        """Google App Passwords are exactly 16 letters (shown as 4 groups of 4)."""
        password = re.sub(r"[\s\-]+", "", raw)
        if not re.fullmatch(r"[A-Za-z]{16}", password):
            raise ValueError(
                "That doesn't look like a Google App Password (it must be exactly 16 letters, like "
                "'abcd efgh ijkl mnop'). Your normal Gmail password will not work here."
            )
        return password.lower()

    @staticmethod
    def explain(exc: BaseException) -> str:
        """Turn imaplib/socket errors into advice a person can act on."""
        text = (
            exc.args[0].decode(errors="replace") if exc.args and isinstance(exc.args[0], bytes) else str(exc)
        )
        lowered = text.lower()
        if "authenticationfailed" in lowered or "invalid credentials" in lowered:
            return (
                "Google rejected the login. Create a NEW App Password while signed in to this same Gmail "
                "account (2-Step Verification must be ON) and paste exactly those 16 letters."
            )
        if "application-specific password" in lowered:
            return "This account requires an App Password — your normal password won't work."
        if "web browser" in lowered or "webalert" in lowered:
            return "Google blocked the sign-in. Open Gmail once in your browser, approve any security prompt, then retry."
        if isinstance(exc, OSError | TimeoutError):
            return f"Couldn't reach Gmail ({text}). Check the internet connection."
        return text

    async def try_connect(self, address: str, app_password: str) -> str:
        """Test new credentials first; save them only if Gmail accepts them (old ones stay otherwise)."""
        address = address.strip()
        if not _EMAIL_RE.fullmatch(address):
            raise ValueError("Please enter a full Gmail address, e.g. name@gmail.com.")
        password = self.normalise_app_password(app_password)
        previous = (self.address, self._password)
        self.address, self._password = address, password
        try:
            message = await self.test()
        except Exception:
            self.address, self._password = previous
            raise
        self.store.save("gmail", {"address": self.address, "app_password": self._password})
        self.last_error = None
        return message

    def disconnect(self) -> None:
        """Forget the App Password connection (Google sign-in is separate: see disconnect_google)."""
        self.address = self._password = ""
        self.store.delete("gmail")

    async def disconnect_google(self) -> None:
        await self.google.disconnect()

    def status(self) -> dict[str, Any]:
        return {
            "name": "gmail",
            "configured": self.configured,
            "method": "google"
            if self.via_google
            else ("app_password" if self.address and self._password else None),
            "account": self.google.email if self.via_google else self.address,
            "error": self.last_error,
            "google": self.google.status(),
        }

    # ── IMAP helpers (blocking; call through asyncio.to_thread) ──────────────
    def _imap(self) -> imaplib.IMAP4_SSL:
        if not self.configured:
            raise RuntimeError("Gmail is not connected. Connect it on the dashboard's Connectors page.")
        conn = imaplib.IMAP4_SSL(IMAP_HOST, ssl_context=ssl.create_default_context(), timeout=20)
        conn.login(self.address, self._password)
        return conn

    @staticmethod
    def _all_mail_folder(conn: imaplib.IMAP4_SSL) -> str:
        _, folders = conn.list()
        for raw in folders or []:
            line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
            if "\\All" in line:
                return line.rsplit(' "/" ', 1)[-1].strip()
        return '"[Gmail]/All Mail"'

    def _fetch_summaries(self, conn: imaplib.IMAP4_SSL, uids: list[bytes]) -> list[MailSummary]:
        out: list[MailSummary] = []
        for uid in reversed(uids):
            _, data = conn.uid("fetch", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if not data or not isinstance(data[0], tuple):
                continue
            flags = data[0][0].decode(errors="replace")
            header = email.message_from_bytes(data[0][1])
            try:
                date = parsedate_to_datetime(header["Date"]).strftime("%d %b %H:%M")
            except Exception:
                date = header.get("Date", "")
            out.append(
                MailSummary(
                    uid=uid.decode(),
                    sender=_decode(header.get("From")),
                    subject=_decode(header.get("Subject")) or "(no subject)",
                    date=date,
                    unread="\\Seen" not in flags,
                )
            )
        return out

    def test_sync(self) -> str:
        conn = self._imap()
        try:
            conn.select("INBOX", readonly=True)
            _, data = conn.uid("search", None, "UNSEEN")
            unread = len(data[0].split()) if data and data[0] else 0
        finally:
            conn.logout()
        self.last_error = None
        return f"Connected as {self.address} — {unread} unread in Inbox."

    def inbox_sync(self, unread_only: bool, limit: int) -> list[MailSummary]:
        conn = self._imap()
        try:
            conn.select("INBOX", readonly=True)
            _, data = conn.uid("search", None, "UNSEEN" if unread_only else "ALL")
            uids = (data[0].split() if data and data[0] else [])[-limit:]
            return self._fetch_summaries(conn, uids)
        finally:
            conn.logout()

    def search_sync(self, query: str, limit: int) -> list[MailSummary]:
        conn = self._imap()
        try:
            conn.select(self._all_mail_folder(conn), readonly=True)
            safe = query.replace("\\", " ").replace('"', " ")
            _, data = conn.uid("search", None, "X-GM-RAW", f'"{safe}"')
            uids = (data[0].split() if data and data[0] else [])[-limit:]
            return self._fetch_summaries(conn, uids)
        finally:
            conn.logout()

    def read_sync(self, uid: str) -> dict[str, str]:
        conn = self._imap()
        try:
            conn.select(self._all_mail_folder(conn), readonly=True)
            _, data = conn.uid("fetch", uid.encode(), "(BODY.PEEK[])")
            if not data or not isinstance(data[0], tuple):
                conn.select("INBOX", readonly=True)
                _, data = conn.uid("fetch", uid.encode(), "(BODY.PEEK[])")
            if not data or not isinstance(data[0], tuple):
                raise RuntimeError(f"no email with id {uid}")
            msg = email.message_from_bytes(data[0][1])
            return {
                "from": _decode(msg.get("From")),
                "to": _decode(msg.get("To")),
                "subject": _decode(msg.get("Subject")),
                "date": msg.get("Date", ""),
                "body": _plain_text(msg),
            }
        finally:
            conn.logout()

    def send_sync(self, to: str, subject: str, body: str) -> None:
        if not self.configured:
            raise RuntimeError("Gmail is not connected.")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.address, to, subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(SMTP_HOST, 465, context=ssl.create_default_context(), timeout=20) as smtp:
            smtp.login(self.address, self._password)
            smtp.send_message(msg)

    # ── async facade ─────────────────────────────────────────────────────────
    async def test(self) -> str:
        try:
            if self.via_google:
                return await self.api.profile()
            return await asyncio.to_thread(self.test_sync)
        except Exception as exc:
            self.last_error = self.explain(exc)
            raise

    async def inbox(self, unread_only: bool = True, limit: int = 5) -> list[MailSummary]:
        if self.via_google:
            return await self.api.inbox(unread_only, limit)
        return await asyncio.to_thread(self.inbox_sync, unread_only, limit)

    async def search(self, query: str, limit: int = 5) -> list[MailSummary]:
        if self.via_google:
            return await self.api.search(query, limit)
        return await asyncio.to_thread(self.search_sync, query, limit)

    async def read(self, uid: str) -> dict[str, str]:
        if self.via_google:
            return await self.api.read(uid)
        return await asyncio.to_thread(self.read_sync, uid)

    async def send(self, to: str, subject: str, body: str) -> None:
        if self.via_google:
            await self.api.send(to, subject, body)
            return
        await asyncio.to_thread(self.send_sync, to, subject, body)
