"""Upload-Warteschlange auf der Festplatte – das PC-Gegenstück zu pwa/src/lib/queue.ts.

Jeder Schritt einer Meeting-Aufnahme wird ZUERST als Datei gespeichert und ERST DANN
hochgeladen:

    desktop/recordings/queue/
        00001760000000000-001.json      {"type": "create", "recording_id": …}
        00001760000000123-002.json      {"type": "chunk", "idx": 0, "audio": "…ogg"}
        00001760000000123-002.ogg       das Audio dazu
        00001760000300456-003.json      {"type": "finish", "chunk_count": …}

Vorteile:
- Kein Netz? Die Dateien warten, bis es wieder geht.
- Absturz oder PC aus? Beim nächsten Start geht es genau dort weiter.

Abgearbeitet wird in Dateinamen-Reihenfolge (= zeitliche Reihenfolge) und beim ersten
Fehler gestoppt – "finish" darf nie vor dem letzten Stück hochgeladen werden.
Alle Schritte sind idempotent: doppelt ausgeführt = kein Schaden.
"""

from __future__ import annotations

import itertools
import json
import logging
import threading
import time
from pathlib import Path
from typing import Protocol

from .config import DESKTOP_DIR

log = logging.getLogger(__name__)

QUEUE_DIR = DESKTOP_DIR / "recordings" / "queue"


class QueueBackend(Protocol):
    """Was die Warteschlange zum Hochladen braucht (in der App: DictumCloud)."""

    def create_recording(self, template: str, language: str, recording_id: str) -> str: ...
    def upload_chunk(self, recording_id: str, idx: int, audio: bytes, content_type: str,
                     duration_seconds: float | None) -> None: ...
    def transcribe_chunk(self, recording_id: str, idx: int) -> dict: ...
    def finish(self, recording_id: str, chunk_count: int, duration_seconds: float | None) -> dict: ...


class UploadQueue:
    def __init__(self, directory: Path = QUEUE_DIR) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self._counter = itertools.count(1)
        self._lock = threading.Lock()  # nie zwei Durchläufe gleichzeitig

    def _new_name(self) -> str:
        return f"{time.time_ns() // 1000:017d}-{next(self._counter) % 1000:03d}"

    # --- Einreihen ----------------------------------------------------------------------

    def add_create(self, recording_id: str, template: str, language: str = "de") -> None:
        self._write({"type": "create", "recording_id": recording_id, "template": template, "language": language})

    def add_chunk(self, recording_id: str, idx: int, audio: bytes, content_type: str,
                  duration_seconds: float) -> None:
        name = self._new_name()
        ext = {"audio/ogg": "ogg", "audio/wav": "wav"}.get(content_type, "bin")
        audio_file = f"{name}.{ext}"
        # Erst das Audio schreiben, dann die JSON-Datei – so gibt es nie einen Eintrag
        # ohne zugehöriges Audio (falls genau dazwischen der Strom ausfällt)
        (self.dir / audio_file).write_bytes(audio)
        self._write({"type": "chunk", "recording_id": recording_id, "idx": idx, "audio": audio_file,
                     "content_type": content_type, "duration_seconds": duration_seconds}, name)

    def add_finish(self, recording_id: str, chunk_count: int, duration_seconds: float) -> None:
        self._write({"type": "finish", "recording_id": recording_id, "chunk_count": chunk_count,
                     "duration_seconds": duration_seconds})

    def _write(self, item: dict, name: str | None = None) -> None:
        name = name or self._new_name()
        tmp = self.dir / f"{name}.json.tmp"
        tmp.write_text(json.dumps(item), encoding="utf-8")
        tmp.replace(self.dir / f"{name}.json")  # "atomar": die Datei ist ganz da oder gar nicht

    def pending(self) -> list[Path]:
        return sorted(self.dir.glob("*.json"))

    # --- Abarbeiten ---------------------------------------------------------------------

    def process(self, backend: QueueBackend) -> tuple[int, str | None]:
        """Lädt alles hoch, was geht. Rückgabe: (erledigt, Fehlermeldung oder None)."""
        if not self._lock.acquire(blocking=False):
            return 0, None  # läuft schon
        done = 0
        try:
            for path in self.pending():
                item = json.loads(path.read_text(encoding="utf-8"))
                self._run(item, backend)
                path.unlink()
                if item["type"] == "chunk":
                    (self.dir / item["audio"]).unlink(missing_ok=True)
                done += 1
            return done, None
        except Exception as e:
            log.warning("Upload unterbrochen (%s) – wird später wiederholt", e)
            return done, str(e)
        finally:
            self._lock.release()

    def _run(self, item: dict, backend: QueueBackend) -> None:
        rid = item["recording_id"]
        if item["type"] == "create":
            backend.create_recording(item["template"], item["language"], recording_id=rid)
        elif item["type"] == "chunk":
            audio = (self.dir / item["audio"]).read_bytes()
            backend.upload_chunk(rid, item["idx"], audio, item["content_type"], item["duration_seconds"])
            backend.transcribe_chunk(rid, item["idx"])
            log.info("Meeting-Stück %d hochgeladen und transkribiert", item["idx"])
        elif item["type"] == "finish":
            backend.finish(rid, item["chunk_count"], item["duration_seconds"])
            log.info("Meeting %s abgeschlossen – Zusammenfassung läuft", rid)
