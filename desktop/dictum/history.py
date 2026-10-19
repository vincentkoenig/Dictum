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
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
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
    words      integer not null default 0,
    app        text,                   -- Programm, in das diktiert wurde (z. B. "Chrome")
    cost       real                    -- geschätzte Kosten in US-Dollar (siehe costs.py)
);
create index if not exists dictations_created on dictations (created_at desc);
"""


# Spalten, die erst später dazukamen: Ältere Datenbanken bekommen sie beim Öffnen nachgerüstet
MIGRATIONS = {"app": "text", "cost": "real"}


@dataclass
class Stats:
    """Alles, was der Reiter "Statistik" anzeigt."""

    dictations: int = 0
    words: int = 0
    speaking_seconds: float = 0.0
    wpm: float | None = None            # Wörter pro Minute gesprochen
    streak: int = 0                     # Tage in Folge mit mindestens einem Diktat
    best_streak: int = 0
    saved_minutes: float = 0.0          # gegenüber Tippen mit TYPING_WPM
    cost_usd: float = 0.0
    days: list[tuple[date, int]] = field(default_factory=list)          # letzte Tage: Wörter
    top_apps: list[tuple[str, int, int]] = field(default_factory=list)  # (Programm, Wörter, Diktate)


TYPING_WPM = 40  # durchschnittliche Tippgeschwindigkeit, Grundlage für "gesparte Zeit"


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
            have = {row["name"] for row in db.execute("pragma table_info(dictations)")}
            for column, kind in MIGRATIONS.items():
                if column not in have:
                    db.execute(f"alter table dictations add column {column} {kind}")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def add(self, raw: str, text: str, duration: float | None = None, engine: str = "",
            cleaned: bool = False, snippet: bool = False, app: str = "", cost: float | None = None) -> None:
        words = len(text.split())
        with closing(self._connect()) as db, db:  # "with db" = Transaktion, committet am Ende
            db.execute(
                "insert into dictations (created_at, raw, text, duration, engine, cleaned, snippet, words, app, cost) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), raw, text, duration, engine, int(cleaned), int(snippet), words, app or None, cost),
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

    def stats(self, days: int = 14, today: date | None = None) -> Stats:
        """Auswertung über den ganzen Verlauf. `today` gibt es für Tests."""
        today = today or datetime.now().astimezone().date()
        with closing(self._connect()) as db:
            rows = db.execute("select created_at, words, duration, app, cost from dictations").fetchall()

        stats = Stats()
        per_day: dict[date, int] = {}
        apps: dict[str, list[int]] = {}
        timed_words = 0
        for row in rows:
            day = _to_local(row["created_at"]).date()
            words = row["words"] or 0
            per_day[day] = per_day.get(day, 0) + words
            stats.dictations += 1
            stats.words += words
            stats.cost_usd += row["cost"] or 0.0
            if row["duration"]:
                stats.speaking_seconds += row["duration"]
                timed_words += words
            if row["app"]:
                entry = apps.setdefault(row["app"], [0, 0])
                entry[0] += words
                entry[1] += 1

        if stats.speaking_seconds > 0:
            stats.wpm = timed_words / (stats.speaking_seconds / 60)
        stats.saved_minutes = max(0.0, stats.words / TYPING_WPM - stats.speaking_seconds / 60)
        stats.streak, stats.best_streak = _streaks(set(per_day), today)
        stats.days = [(today - timedelta(days=n), per_day.get(today - timedelta(days=n), 0))
                      for n in range(days - 1, -1, -1)]
        stats.top_apps = sorted(((name, w, c) for name, (w, c) in apps.items()), key=lambda t: -t[1])[:8]
        return stats


def _streaks(days: set[date], today: date) -> tuple[int, int]:
    """(aktuelle Serie, längste Serie) in Tagen. Die aktuelle Serie bricht nicht ab, nur weil heute
    noch nicht diktiert wurde: Sie zählt dann ab gestern."""
    if not days:
        return 0, 0
    best = run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous is not None and (day - previous).days == 1 else 1
        best = max(best, run)
        previous = day
    start = today if today in days else today - timedelta(days=1)
    current = 0
    while start - timedelta(days=current) in days:
        current += 1
    return current, best
