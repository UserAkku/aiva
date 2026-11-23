"""Gmail over IMAP (read/search) and SMTP (send) using a Google App Password.

Setup (2 minutes): Google Account → Security → 2-Step Verification ON → App
passwords → create one named "AIVA" → paste the 16 letters in the dashboard.
"""

from __future__ import annotations

import asyncio
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

from .store import JsonStore

IMAP_HOST, SMTP_HOST = "imap.gmail.com", "smtp.gmail.com"


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


class GmailConnector:
    name = "gmail"

    def __init__(self, store: JsonStore) -> None:
        self.store = store
        cfg = store.load("gmail", {}) or {}
        self.address: str = cfg.get("address", "")
        self._password: str = cfg.get("app_password", "")
        self.last_error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.address and self._password)

    def configure(self, address: str, app_password: str) -> None:
        self.address = address.strip()
        self._password = re.sub(r"\s+", "", app_password)
        self.store.save("gmail", {"address": self.address, "app_password": self._password})

    def disconnect(self) -> None:
        self.address = self._password = ""
        self.store.delete("gmail")

    def status(self) -> dict[str, Any]:
        return {
            "name": "gmail",
            "configured": self.configured,
            "account": self.address,
            "error": self.last_error,
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
            return await asyncio.to_thread(self.test_sync)
        except Exception as exc:
            self.last_error = str(exc)
            raise

    async def inbox(self, unread_only: bool = True, limit: int = 5) -> list[MailSummary]:
        return await asyncio.to_thread(self.inbox_sync, unread_only, limit)

    async def search(self, query: str, limit: int = 5) -> list[MailSummary]:
        return await asyncio.to_thread(self.search_sync, query, limit)

    async def read(self, uid: str) -> dict[str, str]:
        return await asyncio.to_thread(self.read_sync, uid)

    async def send(self, to: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self.send_sync, to, subject, body)
