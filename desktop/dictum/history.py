"""Lokaler Verlauf der Diktate (SQLite).

Wozu? Wispr Flow merkt sich, was du diktiert hast: Ging ein Text im falschen Fenster
verloren, holt man ihn aus dem Verlauf zurück. Dasselbe machen wir – aber **nur lokal**.
Der Verlauf liegt in `desktop/data/history.db` (in .gitignore), verlässt den PC nie und
taucht auch nicht in der Handy-App auf.

SQLite ist eine Datenbank in einer einzigen Datei, die Python von Haus aus mitbringt
(`sqlite3`) – kein Server nötig. Wir öffnen für jeden Zugriff eine kurze Verbindung:
Das ist billig und vermeidet Probleme, wenn mehrere Threads (Worker, Fenster) zugreifen.

Datenschutz: In settings.toml lässt sich der Verlauf abschalten ([history] enabled = false)
und die Aufbewahrung begrenzen (keep_days). Ältere Einträge löscht `purge()` beim Start.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DESKTOP_DIR

DB_PATH = DESKTOP_DIR / "data" / "history.db"

SCHEMA = """
create table if not exists dictations (
    id         integer primary key autoincrement,
    created_at text not null,          -- UTC, ISO-Format: sortierbar und eindeutig
    raw        text not null,          -- so hat Whisper es verstanden
    text       text not null,          -- so wurde es eingefügt
    duration   real,                   -- Sekunden Audio
    engine     text,                   -- local / openai
    cleaned    integer not null default 0,   -- KI-Bereinigung benutzt?
    snippet    integer not null default 0,   -- war es ein Snippet?
    words      integer not null default 0
);
create index if not exists dictations_created on dictations (created_at desc);
"""


@dataclass
class Entry:
    id: int
    created_at: datetime  # lokale Zeit
    raw: str
    text: str
    duration: float | None
    words: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone()


class History:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def add(self, raw: str, text: str, duration: float | None = None, engine: str = "",
            cleaned: bool = False, snippet: bool = False) -> None:
        words = len(text.split())
        with closing(self._connect()) as db, db:  # "with db" = Transaktion, committet am Ende
            db.execute(
                "insert into dictations (created_at, raw, text, duration, engine, cleaned, snippet, words) "
                "values (?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), raw, text, duration, engine, int(cleaned), int(snippet), words),
            )

    def recent(self, limit: int = 200, query: str = "") -> list[Entry]:
        sql = "select id, created_at, raw, text, duration, words from dictations"
        params: list = []
        if query.strip():
            # % und _ sind in LIKE Platzhalter – mit \ entwerten, damit sie wörtlich gesucht werden
            escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += " where text like ? escape '\\' or raw like ? escape '\\'"
            params += [f"%{escaped}%"] * 2
        sql += " order by created_at desc, id desc limit ?"
        params.append(limit)
        with closing(self._connect()) as db:
            rows = db.execute(sql, params).fetchall()
        return [Entry(r["id"], _to_local(r["created_at"]), r["raw"], r["text"], r["duration"], r["words"])
                for r in rows]

    def delete_all(self) -> int:
        with closing(self._connect()) as db, db:
            return db.execute("delete from dictations").rowcount

    def purge(self, keep_days: int) -> int:
        """Löscht Einträge, die älter als `keep_days` sind. 0 = nie löschen."""
        if keep_days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat(timespec="seconds")
        with closing(self._connect()) as db, db:
            return db.execute("delete from dictations where created_at < ?", (cutoff,)).rowcount

    def today(self) -> tuple[int, int]:
        """(Anzahl Diktate, Anzahl Wörter) seit Mitternacht lokaler Zeit."""
        midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        since = midnight.astimezone(timezone.utc).isoformat(timespec="seconds")
        with closing(self._connect()) as db:
            row = db.execute(
                "select count(*), coalesce(sum(words), 0) from dictations where created_at >= ?", (since,)
            ).fetchone()
        return row[0], row[1]
