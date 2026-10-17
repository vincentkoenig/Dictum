"""Steuert Meetings am PC: Aufnahme, Warteschlange, Cloud, Benachrichtigungen.

    Tray "Meeting aufnehmen"
        → start(): Aufnahme-ID erzeugen, "create" in die Warteschlange, Aufnahme starten
    alle 5 Minuten
        → _on_chunk(): Stück als Opus speichern → Warteschlange
    Tray "Meeting beenden"
        → stop(): letztes Stück + "finish" in die Warteschlange
    Hintergrund-Thread (_worker)
        → Warteschlange hochladen, auf die fertige Zusammenfassung warten,
          Benachrichtigung zeigen, Wörterbuch/Snippets abgleichen

Die Aufnahme hängt nie vom Netz ab: alles landet erst auf der Festplatte.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
import webbrowser
from typing import Callable

import numpy as np

from .cloud import CloudError, DictumCloud
from .config import Settings
from .encoder import to_ogg_opus
from .meeting import MeetingRecorder
from .sync import sync_vocabulary
from .upload_queue import UploadQueue

log = logging.getLogger(__name__)

WORKER_INTERVAL = 30  # Sekunden zwischen zwei Upload-Versuchen ohne neuen Anlass


class MeetingController:
    def __init__(self, settings: Settings, notify: Callable[..., None],
                 on_change: Callable[[], None]) -> None:
        self.settings = settings
        self.notify = notify          # (Titel, Text, Klick-Aktion=None) → Windows-Benachrichtigung
        self.on_change = on_change    # Tray-Menü/Symbol aktualisieren
        self.queue = UploadQueue()
        self._recorder: MeetingRecorder | None = None
        self._recording_id = ""
        self._watch: set[str] = set()  # Aufnahmen, auf deren Zusammenfassung wir warten
        self.last_recording_id: str | None = None
        self._cloud: DictumCloud | None = None
        self._wake = threading.Event()
        self._last_sync = 0.0

    # --- Für Tray und App ------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._recorder is not None

    @property
    def elapsed(self) -> float:
        return self._recorder.elapsed if self._recorder else 0.0

    def start_worker(self) -> None:
        # Sofort einen ersten Durchlauf: Liegengebliebenes vom letzten Mal hochladen
        # und Wörterbuch/Snippets abgleichen – nicht erst nach 30 Sekunden
        self._wake.set()
        threading.Thread(target=self._worker, daemon=True).start()

    def start(self, template: str) -> None:
        if self._recorder:
            return
        self._recording_id = str(uuid.uuid4())
        m = self.settings.meeting
        recorder = MeetingRecorder(
            on_chunk=self._on_chunk,
            chunk_seconds=m.chunk_minutes * 60,
            include_system_audio=m.include_system_audio,
            mic_gain=m.mic_gain,
            system_gain=m.system_gain,
        )
        try:
            recorder.start()
        except Exception as e:
            log.exception("Meeting-Aufnahme konnte nicht starten")
            self.notify("Meeting nicht gestartet", str(e))
            return
        self.queue.add_create(self._recording_id, template)
        self._recorder = recorder
        self.notify(
            "Meeting-Aufnahme läuft",
            "Bitte nur mit Einwilligung aller Beteiligten aufnehmen (§ 201 StGB).",
        )
        self.on_change()
        self._wake.set()

    def stop(self) -> None:
        recorder, self._recorder = self._recorder, None
        if recorder is None:
            return
        duration = recorder.elapsed
        count = recorder.stop()  # liefert das letzte Stück noch an _on_chunk
        rid = self._recording_id
        if count == 0:
            self.notify("Meeting verworfen", "Die Aufnahme war zu kurz.")
            self._discard(rid)
        else:
            self.queue.add_finish(rid, count, round(duration))
            self._watch.add(rid)
            self.notify("Meeting beendet", f"{count} Teil(e) – Transkript und Zusammenfassung werden erstellt.")
        self.on_change()
        self._wake.set()

    def open_last(self) -> None:
        if self.last_recording_id:
            webbrowser.open(f"{self.settings.meeting.web_url}#/r/{self.last_recording_id}")

    def open_web(self) -> None:
        webbrowser.open(self.settings.meeting.web_url)

    def sync_now(self) -> None:
        self._last_sync = 0  # erzwingt Abgleich beim nächsten Worker-Durchlauf
        self._wake.set()

    # --- Intern ----------------------------------------------------------------------

    def _on_chunk(self, idx: int, audio: np.ndarray, duration: float) -> None:
        # Läuft im Misch-Thread der Aufnahme
        self.queue.add_chunk(self._recording_id, idx, to_ogg_opus(audio), "audio/ogg", round(duration, 1))
        self._wake.set()

    def _discard(self, rid: str) -> None:
        """Leere Aufnahme: "create" noch nicht hochgeladen → einfach aus der Schlange
        löschen; sonst später in der Cloud löschen."""
        for path in self.queue.pending():
            if rid in path.read_text(encoding="utf-8"):
                path.unlink()
                return
        try:
            self._get_cloud().delete_recording(rid)
        except Exception:
            log.warning("Leere Aufnahme %s konnte nicht gelöscht werden", rid)

    def _get_cloud(self) -> DictumCloud:
        if self._cloud is None:
            email, password = os.environ.get("DICTUM_EMAIL"), os.environ.get("DICTUM_PASSWORD")
            if not email or not password:
                raise CloudError("DICTUM_EMAIL/DICTUM_PASSWORD fehlen in der .env")
            cloud = DictumCloud(self.settings.cloud.url, self.settings.cloud.publishable_key)
            cloud.sign_in(email, password)
            self._cloud = cloud
        return self._cloud

    def _worker(self) -> None:
        while True:
            self._wake.wait(timeout=WORKER_INTERVAL)
            self._wake.clear()
            try:
                self._tick()
            except CloudError as e:
                log.warning("Cloud nicht erreichbar: %s", e)
                self._cloud = None  # beim nächsten Mal neu einloggen
            except Exception:
                log.exception("Fehler im Meeting-Hintergrundprozess")

    def _tick(self) -> None:
        if self.queue.pending():
            done, error = self.queue.process(self._get_cloud())
            if error:
                return  # später nochmal – nichts geht verloren
        self._check_finished()
        m = self.settings.meeting
        interval = m.sync_minutes * 60 if m.sync_minutes > 0 else float("inf")
        if self._last_sync == 0 or time.monotonic() - self._last_sync > interval:
            sync_vocabulary(self._get_cloud())
            self._last_sync = time.monotonic()

    def _check_finished(self) -> None:
        """Ist eine beobachtete Aufnahme fertig? Dann Bescheid geben."""
        pending_text = "".join(p.read_text(encoding="utf-8") for p in self.queue.pending())
        for rid in list(self._watch):
            if rid in pending_text:
                continue  # noch nicht alles hochgeladen
            rec = self._get_cloud().get_recording(rid)
            if rec["status"] == "done":
                self._watch.discard(rid)
                self.last_recording_id = rid
                self.notify("Zusammenfassung fertig", rec.get("title") or "Meeting", self.open_last)
                self.on_change()
            elif rec["status"] == "error":
                self._watch.discard(rid)
                self.last_recording_id = rid
                self.notify("Meeting: Fehler", rec.get("error") or "Unbekannter Fehler", self.open_last)
                self.on_change()
            else:
                # Wartet noch auf die Zusammenfassung → bald wieder nachsehen
                threading.Timer(5, self._wake.set).start()
