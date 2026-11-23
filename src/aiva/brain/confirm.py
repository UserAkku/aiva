"""Human-in-the-loop gate for irreversible tools (sending email, …).

A guarded tool first *creates* a pending action and the model reads the details
back. Only on a **later** turn, and only if the user's own words in that turn are
a clear yes, can the action be executed. The model can't talk itself into it.
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

_YES = re.compile(
    r"\b(yes|yeah|yep|yup|sure|ok|okay|confirm(ed)?|go ahead|do it|send( it)?|haan?|haanji|han|ji|hanji|"
    r"theek hai|thik hai|kar do|karo|bhej do|bhejo|done|absolutely)\b|हाँ|हां|जी|ठीक|भेज|कर दो",
    re.IGNORECASE,
)
_NO = re.compile(
    r"\b(no|nope|nah|don'?t|do not|cancel|stop|wait|nahi|nahin|na|mat|ruko|rehne do)\b|नहीं|मत|रुको|रहने दो",
    re.IGNORECASE,
)


def is_affirmative(text: str) -> bool:
    return bool(_YES.search(text)) and not _NO.search(text)


@dataclass
class PendingAction:
    id: str
    session_id: str
    kind: str
    summary: str
    payload: dict[str, Any]
    created_turn_id: str
    created_at: float = field(default_factory=time.time)


class ConfirmationGate:
    TTL_S = 10 * 60

    def __init__(self) -> None:
        self._actions: dict[str, PendingAction] = {}

    def create(
        self, session_id: str, kind: str, summary: str, payload: dict[str, Any], turn_id: str
    ) -> PendingAction:
        self._gc()
        action = PendingAction(secrets.token_hex(3), session_id, kind, summary, payload, turn_id)
        self._actions[action.id] = action
        return action

    def resolve(self, action_id: str, session_id: str, turn_id: str, user_text: str) -> PendingAction:
        """Return the action if the *current* user utterance confirms it, else raise ``PermissionError``."""
        self._gc()
        action = self._actions.get(action_id.strip())
        if action is None or action.session_id != session_id:
            raise PermissionError("unknown or expired confirmation id; ask the user again")
        if turn_id == action.created_turn_id:
            raise PermissionError("ask the user to confirm first; you cannot confirm in the same turn")
        if not is_affirmative(user_text):
            raise PermissionError("the user did not clearly say yes; do not send")
        del self._actions[action.id]
        return action

    def _gc(self) -> None:
        cutoff = time.time() - self.TTL_S
        for key in [k for k, a in self._actions.items() if a.created_at < cutoff]:
            del self._actions[key]
