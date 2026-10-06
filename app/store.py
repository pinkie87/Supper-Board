"""Kleiner Dokumentenspeicher auf SQLite-Basis.

Daten liegen als JSON-Dokumente in Sammlungen ("meals/p20261012-01"), genau wie
im ursprünglichen Claude-Artifact. Jede Änderung wird an alle offenen
Browserfenster gemeldet, damit das Board live aktualisiert.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

COLLECTIONS = {
    "meals", "draft", "history", "notes", "ideas", "grocery",
    "staples", "freezer", "plan", "recipes", "imports",
}


class NotFound(Exception):
    pass


def split_path(path: str) -> tuple[str, str]:
    parts = path.strip("/").split("/")
    if len(parts) != 2 or not parts[1] or parts[0] not in COLLECTIONS:
        raise ValueError(f"Ungültiger Pfad: {path}")
    return parts[0], parts[1]


def merge(target: dict, src: dict) -> dict:
    """Wie Firestore-update: verschachtelte Objekte zusammenführen, {"__delete__": true} löscht ein Feld."""
    for key, value in src.items():
        if isinstance(value, dict) and value.get("__delete__") is True:
            target.pop(key, None)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = json.loads(json.dumps(value))
    return target


def new_id() -> str:
    return secrets.token_hex(6)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS docs (col TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,"
            " updated REAL NOT NULL, PRIMARY KEY (col, id))"
        )
        self._lock = threading.Lock()
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    # ---------- Änderungsmeldungen ----------
    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _publish(self, col: str, doc_id: str) -> None:
        event = {"col": col, "id": doc_id}

        def push() -> None:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

        if self._loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            push()
        else:
            self._loop.call_soon_threadsafe(push)

    # ---------- Lesen ----------
    def get(self, col: str, doc_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM docs WHERE col=? AND id=?", (col, doc_id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, col: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT id, data FROM docs WHERE col=? ORDER BY id", (col,)).fetchall()
        return [dict(json.loads(data), id=doc_id) for doc_id, data in rows]

    # ---------- Schreiben ----------
    def set(self, col: str, doc_id: str, data: dict[str, Any]) -> None:
        clean = {k: v for k, v in data.items() if k not in ("id", "_col")}
        with self._lock:
            self._db.execute(
                "INSERT INTO docs (col, id, data, updated) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(col, id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                (col, doc_id, json.dumps(clean, ensure_ascii=False), time.time()),
            )
        self._publish(col, doc_id)

    def add(self, col: str, data: dict[str, Any]) -> str:
        doc_id = new_id()
        self.set(col, doc_id, data)
        return doc_id

    def update(self, col: str, doc_id: str, data: dict[str, Any]) -> dict:
        with self._lock:
            row = self._db.execute("SELECT data FROM docs WHERE col=? AND id=?", (col, doc_id)).fetchone()
            if not row:
                raise NotFound(f"{col}/{doc_id}")
            merged = merge(json.loads(row[0]), data)
            self._db.execute(
                "UPDATE docs SET data=?, updated=? WHERE col=? AND id=?",
                (json.dumps(merged, ensure_ascii=False), time.time(), col, doc_id),
            )
        self._publish(col, doc_id)
        return merged

    def delete(self, col: str, doc_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM docs WHERE col=? AND id=?", (col, doc_id))
        self._publish(col, doc_id)

    def close(self) -> None:
        self._db.close()
