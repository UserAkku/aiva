"""Gmail connector: App Password validation and human-readable login errors (no network)."""

from __future__ import annotations

import imaplib

import pytest

from aiva.connectors.gmail import GmailConnector


def test_app_password_format() -> None:
    assert GmailConnector.normalise_app_password("abcd efgh ijkl mnop") == "abcdefghijklmnop"
    assert GmailConnector.normalise_app_password("ABCD-EFGH-IJKL-MNOP") == "abcdefghijklmnop"
    for wrong in ("MyNormalPass@123", "abcd efgh ijkl", "abcd efgh ijkl mnop q", "abcd1234efgh5678"):
        with pytest.raises(ValueError):
            GmailConnector.normalise_app_password(wrong)


def test_imap_errors_are_explained() -> None:
    auth = imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
    assert "App Password" in GmailConnector.explain(auth)
    assert "b'" not in GmailConnector.explain(auth)
    assert "internet" in GmailConnector.explain(OSError("nodename nor servname provided"))
