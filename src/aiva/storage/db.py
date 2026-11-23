"""SQLite persistence (WAL mode). Queries are tiny, so they run inline behind a lock."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    done_at REAL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'reminder',
    fired INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_daily (
    day TEXT NOT NULL,
    deployment TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, deployment)
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_text TEXT NOT NULL,
    reply_text TEXT NOT NULL,
    model TEXT,
    tools TEXT,
    timings TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO kv(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
            )

    # ── low level ────────────────────────────────────────────────────────────
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── long-term memory ─────────────────────────────────────────────────────
    def add_fact(self, text: str) -> int:
        cur = self.execute("INSERT INTO facts(text, created_at) VALUES (?, ?)", (text.strip(), time.time()))
        return int(cur.lastrowid or 0)

    def facts(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM facts ORDER BY id DESC LIMIT ?", (limit,))

    def delete_fact(self, fact_id: int) -> bool:
        return self.execute("DELETE FROM facts WHERE id = ?", (fact_id,)).rowcount > 0

    def forget_facts_matching(self, needle: str) -> int:
        return self.execute("DELETE FROM facts WHERE text LIKE ?", (f"%{needle}%",)).rowcount

    # ── notes & todos ────────────────────────────────────────────────────────
    def add_note(self, text: str) -> int:
        cur = self.execute("INSERT INTO notes(text, created_at) VALUES (?, ?)", (text.strip(), time.time()))
        return int(cur.lastrowid or 0)

    def notes(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,))

    def delete_note(self, note_id: int) -> bool:
        return self.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0

    def add_todo(self, text: str) -> int:
        cur = self.execute("INSERT INTO todos(text, created_at) VALUES (?, ?)", (text.strip(), time.time()))
        return int(cur.lastrowid or 0)

    def todos(self, include_done: bool = False) -> list[dict[str, Any]]:
        where = "" if include_done else "WHERE done = 0"
        return self.query(f"SELECT * FROM todos {where} ORDER BY done, id")

    def complete_todo(self, todo_id: int) -> bool:
        cur = self.execute("UPDATE todos SET done = 1, done_at = ? WHERE id = ?", (time.time(), todo_id))
        return cur.rowcount > 0

    def delete_todo(self, todo_id: int) -> bool:
        return self.execute("DELETE FROM todos WHERE id = ?", (todo_id,)).rowcount > 0

    # ── timers & reminders ───────────────────────────────────────────────────
    def add_reminder(self, text: str, due_at: float, kind: str = "reminder") -> int:
        cur = self.execute(
            "INSERT INTO reminders(text, due_at, kind, created_at) VALUES (?, ?, ?, ?)",
            (text.strip(), due_at, kind, time.time()),
        )
        return int(cur.lastrowid or 0)

    def pending_reminders(self) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM reminders WHERE fired = 0 ORDER BY due_at")

    def mark_reminder_fired(self, reminder_id: int) -> None:
        self.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))

    def cancel_reminder(self, reminder_id: int) -> bool:
        return self.execute("DELETE FROM reminders WHERE id = ? AND fired = 0", (reminder_id,)).rowcount > 0

    # ── LLM usage (local accounting that backs the quota guard) ──────────────
    def add_usage(self, day: str, deployment: str, requests: int, inp: int, out: int, errors: int) -> None:
        self.execute(
            """INSERT INTO usage_daily(day, deployment, requests, input_tokens, output_tokens, errors)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(day, deployment) DO UPDATE SET
                 requests = requests + excluded.requests,
                 input_tokens = input_tokens + excluded.input_tokens,
                 output_tokens = output_tokens + excluded.output_tokens,
                 errors = errors + excluded.errors""",
            (day, deployment, requests, inp, out, errors),
        )

    def usage_for_day(self, day: str) -> dict[str, dict[str, int]]:
        rows = self.query("SELECT * FROM usage_daily WHERE day = ?", (day,))
        return {r["deployment"]: r for r in rows}

    def usage_history(self, days: int = 7) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM usage_daily WHERE day IN "
            "(SELECT DISTINCT day FROM usage_daily ORDER BY day DESC LIMIT ?) ORDER BY day",
            (days,),
        )

    # ── conversation log ─────────────────────────────────────────────────────
    def log_turn(
        self,
        session_id: str,
        user_text: str,
        reply_text: str,
        model: str | None,
        tools: list[str],
        timings: dict[str, float],
    ) -> None:
        self.execute(
            "INSERT INTO turns(session_id, user_text, reply_text, model, tools, timings, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_text, reply_text, model, json.dumps(tools), json.dumps(timings), time.time()),
        )

    def recent_turns(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM turns ORDER BY id DESC LIMIT ?", (limit,))
        for row in rows:
            row["tools"] = json.loads(row["tools"] or "[]")
            row["timings"] = json.loads(row["timings"] or "{}")
        return rows

    # ── key/value ────────────────────────────────────────────────────────────
    def get_kv(self, key: str, default: str | None = None) -> str | None:
        rows = self.query("SELECT value FROM kv WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set_kv(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
