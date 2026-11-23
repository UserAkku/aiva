"""Gmail skills. Sending is protected by the confirmation gate (needs the user's spoken yes)."""

from __future__ import annotations

import re

from pydantic_ai import RunContext

from ..brain.deps import AgentDeps
from ..brain.toolsets import ToolRegistry

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _gmail(ctx: RunContext[AgentDeps]):
    gmail = ctx.deps.services.connectors.gmail
    if not gmail.configured:
        raise RuntimeError(
            "Gmail isn't connected yet. Tell the user to connect it on the dashboard Connectors page."
        )
    return gmail


def register(reg: ToolRegistry) -> None:
    @reg.tool("gmail")
    async def check_inbox(ctx: RunContext[AgentDeps], unread_only: bool = True, limit: int = 5) -> str:
        """List the latest emails in the Gmail inbox.

        Args:
            unread_only: Only unread emails.
            limit: How many (1-10).
        """
        try:
            mails = await _gmail(ctx).inbox(unread_only, max(1, min(limit, 10)))
        except Exception as exc:
            return f"Gmail error: {exc}"
        if not mails:
            return "No unread emails." if unread_only else "Inbox is empty."
        return "\n".join(f"[id {m.uid}] {m.date} — {m.sender}: {m.subject}" for m in mails)

    @reg.tool("gmail")
    async def search_email(ctx: RunContext[AgentDeps], query: str, limit: int = 5) -> str:
        """Search Gmail with Gmail search syntax, e.g. 'from:amazon', 'subject:exam newer_than:7d'.

        Args:
            query: Gmail search query.
            limit: How many results (1-10).
        """
        try:
            mails = await _gmail(ctx).search(query, max(1, min(limit, 10)))
        except Exception as exc:
            return f"Gmail error: {exc}"
        return "\n".join(f"[id {m.uid}] {m.date} — {m.sender}: {m.subject}" for m in mails) or "No matches."

    @reg.tool("gmail")
    async def read_email(ctx: RunContext[AgentDeps], email_id: str) -> str:
        """Read one email's full text (use an id from check_inbox/search_email).

        Args:
            email_id: The id number.
        """
        try:
            mail = await _gmail(ctx).read(email_id.strip())
        except Exception as exc:
            return f"Gmail error: {exc}"
        body = mail["body"]
        return (
            f"From: {mail['from']}\nSubject: {mail['subject']}\nDate: {mail['date']}\n\n"
            + body[:2500]
            + (" …" if len(body) > 2500 else "")
        )

    @reg.tool("gmail", confirm=True)
    async def send_email(
        ctx: RunContext[AgentDeps], to: str, subject: str, body: str, confirmation_id: str = ""
    ) -> str:
        """Send an email from the user's Gmail. Two steps: call without confirmation_id to prepare it and
        read it back; only after the user clearly says yes in their NEXT message, call again with the id.

        Args:
            to: Recipient email address.
            subject: Subject line.
            body: Plain-text message body.
            confirmation_id: Id returned by the first call, after the user said yes.
        """
        services = ctx.deps.services
        if not confirmation_id:
            if not _EMAIL.match(to.strip()):
                return f"'{to}' is not a valid email address; ask the user to spell it."
            action = services.confirmations.create(
                ctx.deps.session_id,
                "send_email",
                f"to {to}, subject '{subject}'",
                {"to": to.strip(), "subject": subject, "body": body},
                ctx.deps.turn_id,
            )
            return (
                f"PREPARED, NOT SENT. confirmation_id={action.id}. Read back briefly: to {to}, subject "
                f"'{subject}', and the gist of the message. Ask if you should send it."
            )
        try:
            action = services.confirmations.resolve(
                confirmation_id, ctx.deps.session_id, ctx.deps.turn_id, ctx.deps.user_text
            )
        except PermissionError as exc:
            return f"NOT SENT: {exc}"
        try:
            await _gmail(ctx).send(**action.payload)
        except Exception as exc:
            return f"Sending failed: {exc}"
        services.bus.publish("gmail.sent", to=action.payload["to"], subject=action.payload["subject"])
        return f"Sent to {action.payload['to']}."
