"""Verbindet alle Bausteine zur fertigen App.

Wer läuft in welchem Thread?

    Hauptthread ......... Overlay (tkinter muss im Hauptthread laufen)
    pynput-Thread ....... hört auf die Tastatur → ruft _start/_stop/_cancel auf
    pystray-Thread ...... Tray-Symbol und Menü
    Lade-Thread ......... lädt einmalig das lokale Whisper-Modell
    Worker-Thread ....... transkribiert, bereinigt und fügt ein – eins nach dem anderen

Warum ein eigener Worker? Transkribieren + Bereinigen dauert 1–4 Sekunden. Würde das
im Tastatur-Thread passieren, wäre die Tastatur in dieser Zeit blockiert. Stattdessen
legen wir das Audio in eine Warteschlange und der Worker arbeitet sie ab.

Der Weg eines Diktats im Worker (`_process`):

    Audio ─► Spracherkennung (lokal oder OpenAI) ─► Rohtext
          ─► Snippet? ── ja ─► Snippet-Text einfügen
                     └─ nein ─► KI-Bereinigung (wenn an) ─► Text einfügen
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
import winsound

import numpy as np

from .audio import Recorder
from .cleanup import clean_text
from .cloud_transcriber import OpenAITranscriber
from .config import Settings
from .hotkey import HotkeyListener, HotkeyStateMachine, hotkey_label
from .inserter import insert_text
from .llm import LLMError, create_provider
from .overlay import Overlay
from .transcriber import LocalTranscriber
from .tray import Tray
from .vocabulary import (
    DICTIONARY_PATH,
    SNIPPETS_PATH,
    ensure_user_files,
    load_dictionary,
    load_snippets,
    match_snippet,
)

log = logging.getLogger(__name__)


class DictumApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        tr = settings.transcription
        self.recorder = Recorder()

        # Beide Spracherkennungen bereithalten: das lokale Modell dient auch als
        # Ersatz, falls die Cloud nicht erreichbar ist
        self.local = LocalTranscriber(tr.model, tr.language, tr.fallback_language)
        self.cloud = OpenAITranscriber(tr.openai_model, tr.language)
        self.engine = tr.engine

        self.cleanup_enabled = settings.cleanup.enabled
        self.provider = create_provider(settings.cleanup.provider, settings.cleanup)

        self.overlay = Overlay()
        self.machine = HotkeyStateMachine(
            on_start=self._start,
            on_stop=self._stop,
            on_cancel=self._cancel,
            mode=settings.hotkey.mode,
            hold_threshold=settings.hotkey.hold_threshold,
        )
        self.listener = HotkeyListener(settings.hotkey.keys, self.machine)
        self.tray = Tray(self, hotkey_label(settings.hotkey.keys))
        self._jobs: queue.Queue[np.ndarray | None] = queue.Queue()
        ensure_user_files()

    def run(self) -> None:
        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        self.listener.start()
        self.tray.start()
        log.info(
            "Dictum läuft. Spracherkennung: %s · KI-Bereinigung: %s (%s)",
            self.engine, "an" if self.cleanup_enabled else "aus", self.provider.name,
        )
        self.overlay.run()  # blockiert bis zum Beenden

    def quit(self) -> None:
        log.info("Beende Dictum …")
        self.listener.stop()
        self._jobs.put(None)  # Signal an den Worker: aufhören
        self.tray.stop()
        self.overlay.quit()

    # --- Einstellungen zur Laufzeit (vom Tray-Menü genutzt) ---------------------------

    def get(self, setting: str):
        return {
            "mode": lambda: self.machine.mode,
            "language": lambda: self.local.language,
            "engine": lambda: self.engine,
            "cleanup": lambda: self.cleanup_enabled,
            "provider": lambda: self.provider.name,
        }[setting]()

    def set(self, setting: str, value) -> None:
        if setting == "mode":
            self.machine.mode = value
        elif setting == "language":
            self.local.language = self.cloud.language = value
        elif setting == "engine":
            self.engine = value
        elif setting == "cleanup":
            self.cleanup_enabled = value
        elif setting == "provider":
            self.provider = create_provider(value, self.settings.cleanup)
        log.info("Einstellung geändert: %s = %s", setting, value)

    def open_dictionary(self) -> None:
        os.startfile(DICTIONARY_PATH)  # öffnet die Datei im Standard-Editor

    def open_snippets(self) -> None:
        os.startfile(SNIPPETS_PATH)

    # --- Hotkey-Ereignisse (laufen im pynput-Thread, müssen schnell sein) ------------

    def _start(self) -> None:
        try:
            self.recorder.start()
        except Exception:
            log.exception("Mikrofon konnte nicht geöffnet werden")
            self.overlay.flash("Kein Mikrofon gefunden")
            return
        self._beep(880)
        self.overlay.show("listening")

    def _stop(self) -> None:
        audio = self.recorder.stop()
        self._beep(660)
        ready = self.engine == "openai" or self.local.is_ready
        self.overlay.show("transcribing" if ready else "loading")
        self._jobs.put(audio)

    def _cancel(self) -> None:
        self.recorder.stop()
        self.overlay.hide()
        log.debug("Aufnahme verworfen (andere Tastenkombination)")

    # --- Hintergrund-Threads ---------------------------------------------------------

    def _load_model(self) -> None:
        try:
            self.local.load()
        except Exception:
            log.exception("Whisper-Modell konnte nicht geladen werden")
            self.overlay.flash("Modell-Fehler – siehe Konsole", seconds=5)

    def _worker(self) -> None:
        while True:
            audio = self._jobs.get()
            if audio is None:
                return
            try:
                self._process(audio)
            except Exception:
                log.exception("Fehler bei der Verarbeitung")
                self.overlay.flash("Fehler – siehe Konsole")

    def _process(self, audio: np.ndarray) -> None:
        # Wörterbuch und Snippets bei jedem Diktat frisch lesen – so wirken Änderungen
        # an den Dateien sofort, ohne Neustart (die Dateien sind winzig)
        dictionary = load_dictionary()
        snippets = load_snippets()

        t0 = time.perf_counter()
        raw = self._transcribe(audio, dictionary)
        t1 = time.perf_counter()
        if not raw:
            self.overlay.flash("Nichts erkannt")
            return

        snippet = match_snippet(raw, snippets)
        if snippet is not None:
            log.info("Snippet erkannt: %r", raw)
            text = snippet
        elif self.cleanup_enabled:
            self.overlay.show("polishing")
            text = clean_text(raw, self.provider, dictionary)
        else:
            text = raw
        t2 = time.perf_counter()

        log.info("Fertig: Erkennung %.1f s · Bereinigung %.1f s → %r", t1 - t0, t2 - t1, text)
        self.overlay.hide()
        insert_text(text)

    def _transcribe(self, audio: np.ndarray, dictionary: list[str]) -> str:
        self.local.vocabulary = self.cloud.vocabulary = dictionary
        if self.engine == "openai":
            try:
                return self.cloud.transcribe(audio)
            except LLMError as e:
                # Cloud nicht verfügbar → lokal weitermachen statt das Diktat zu verlieren
                log.warning("%s – nutze lokales Whisper", e)
                self.overlay.show("transcribing")
        return self.local.transcribe(audio)

    def _beep(self, frequency: int) -> None:
        if self.settings.feedback.sounds:
            # Beep blockiert für die Tondauer → in eigenem Thread
            threading.Thread(target=winsound.Beep, args=(frequency, 60), daemon=True).start()
